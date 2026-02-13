"""
LLM Client for AI Code Review
Supports Claude (Anthropic) and GPT-4 (Azure OpenAI)

This module centralizes Azure OpenAI configuration and exposes both
SDK-based and LangChain-based interfaces for use throughout the codebase.
It also contains logic to safely handle very large PR diffs by chunking
and prioritizing them before calling the LLM.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from langchain_openai import AzureChatOpenAI


# ---------------------------------------------------------------------------
# Pydantic models for structured review output
# ---------------------------------------------------------------------------

class InlineSuggestion(BaseModel):
    """A single inline suggestion to post on a specific line in the PR diff."""
    file_path: str = Field(
        description="Relative file path exactly as shown in the diff header (e.g. 'src/app/main.py')"
    )
    line: int = Field(
        description=(
            "Line number in the NEW version of the file (from the #L marker in the annotated diff). "
            "For multi-line suggestions this is the END line of the range."
        )
    )
    end_line: Optional[int] = Field(
        default=None,
        description=(
            "Start line for multi-line suggestions. If the issue spans lines 22-24, "
            "set end_line=22 and line=24. Leave null for single-line suggestions."
        ),
    )
    message: str = Field(
        description="Clear explanation of what is wrong and why it should be changed"
    )
    suggested_code: Optional[str] = Field(
        default=None,
        description=(
            "The replacement code for the target line(s). MUST contain ONLY valid "
            "source code — never explanatory text or natural language. When applied, "
            "this value directly replaces the line(s) in the source file. "
            "Use empty string '' to delete the line(s). "
            "Use null ONLY when no concrete fix is possible (informational comment only)."
        ),
    )


class ReviewWithSuggestions(BaseModel):
    """Structured output containing both the review summary and inline suggestions."""
    summary: str = Field(
        description=(
            "The full code review text in markdown, including Summary, "
            "Critical Issues, Improvements, and Positive Aspects sections."
        )
    )
    inline_suggestions: List[InlineSuggestion] = Field(
        default_factory=list,
        description=(
            "List of inline suggestions to post as review comments on specific "
            "lines in the PR diff. Each suggestion targets a specific file and line."
        ),
    )


# ---------------------------------------------------------------------------
# Diff annotation helper
# ---------------------------------------------------------------------------

def annotate_diff_with_line_numbers(diff: str) -> str:
    """Annotate added/context lines in a unified diff with their new-file line numbers.

    For every ``+`` (added) line and `` `` (context) line inside a hunk, this
    appends a ``  # L{n}`` marker so the LLM can reference exact line numbers
    when producing inline suggestions.

    Hunk headers (``@@ ... @@``), removed lines (``-``), and file-level
    metadata lines are left untouched.

    The function also handles the custom diff format used by ``get_pr_diff``
    in ``github_api.py`` which uses ``=====`` separators and ``File: path``
    headers instead of ``diff --git`` markers.
    """
    if not diff:
        return diff

    annotated_lines: List[str] = []
    new_line_number: int = 0  # tracks current line in new file
    current_file: Optional[str] = None

    for raw_line in diff.splitlines(keepends=True):
        line = raw_line.rstrip("\n\r")

        # Detect file header in custom format: "File: path/to/file.py"
        if line.startswith("File: "):
            current_file = line[6:].strip()
            new_line_number = 0
            annotated_lines.append(raw_line)
            continue

        # Standard git diff header
        if line.startswith("diff --git "):
            current_file = None
            new_line_number = 0
            annotated_lines.append(raw_line)
            continue

        # +++ header – extract file path
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current_file = path
            annotated_lines.append(raw_line)
            continue

        # --- header
        if line.startswith("--- "):
            annotated_lines.append(raw_line)
            continue

        # Hunk header: @@ -a,b +c,d @@
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk_match:
            new_line_number = int(hunk_match.group(1))
            annotated_lines.append(raw_line)
            continue

        # Added line
        if line.startswith("+"):
            annotated_lines.append(f"{line}  # L{new_line_number}\n")
            new_line_number += 1
            continue

        # Removed line – does not affect new-file line numbering
        if line.startswith("-"):
            annotated_lines.append(raw_line)
            continue

        # Context line (unchanged)
        if current_file and new_line_number > 0:
            annotated_lines.append(f"{line}  # L{new_line_number}\n")
            new_line_number += 1
        else:
            annotated_lines.append(raw_line)

    return "".join(annotated_lines)


class LLMClient:
    """Client for interacting with LLM providers"""

    def __init__(self):
        # Load optional configuration (e.g., temperature, max_tokens, diff limits)
        self.llm_config: Dict[str, Any] = self._load_llm_config()
        llm_section = self.llm_config.get("llm", {}) if isinstance(self.llm_config, dict) else {}

        # Limits for handling large diffs (characters are used as a cheap proxy for tokens)
        self.max_diff_chars_per_call: int = self._safe_int(
            llm_section.get("max_diff_chars_per_call"), default=20_000
        )
        self.max_total_diff_chars: int = self._safe_int(
            llm_section.get("max_total_diff_chars"), default=200_000
        )
        # Approximate token threshold at which we switch to chunked processing
        self.max_tokens_per_diff: int = self._safe_int(
            llm_section.get("max_tokens_per_diff"), default=6_000
        )

        # Anthropic Claude
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')

        # Azure OpenAI
        self.azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.azure_key = os.getenv('AZURE_OPENAI_KEY')
        # Keep existing env var name for backwards compatibility
        self.azure_deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4.1-min')
        self.azure_api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2025-01-01-preview')

        # Initialize clients
        self.anthropic = None
        self.azure = None

        # Shared LangChain chat model and review chain for Azure
        self.azure_langchain: Optional[AzureChatOpenAI] = None
        self.review_prompt: Optional[ChatPromptTemplate] = None
        self.review_chain = None

        # Dedicated LangChain chat model for structured review (higher max_tokens)
        self.azure_langchain_structured: Optional[AzureChatOpenAI] = None

        # Structured review chain (returns ReviewWithSuggestions)
        self.structured_review_prompt: Optional[ChatPromptTemplate] = None
        self.structured_review_chain = None
        self.structured_parser = PydanticOutputParser(
            pydantic_object=ReviewWithSuggestions
        )

        if self.anthropic_key:
            try:
                from anthropic import Anthropic
                self.anthropic = Anthropic(api_key=self.anthropic_key)
                print("✅ Anthropic Claude initialized")
            except ImportError:
                print("⚠️  anthropic package not installed")

        if self.azure_endpoint and self.azure_key:
            try:
                from openai import AzureOpenAI
                self.azure = AzureOpenAI(
                    azure_endpoint=self.azure_endpoint,
                    api_key=self.azure_key,
                    api_version=self.azure_api_version,
                )
                print("✅ Azure OpenAI SDK client initialized")
            except ImportError:
                print("⚠️  openai package not installed")

            # Initialize shared LangChain chat model for Azure
            try:
                temperature = (
                    self.llm_config.get("llm", {}).get("temperature", 0.3)
                )
                max_tokens = (
                    self.llm_config.get("llm", {}).get("max_tokens", 4096)
                )

                self.azure_langchain = AzureChatOpenAI(
                    azure_endpoint=self.azure_endpoint,
                    api_key=self.azure_key,
                    api_version=self.azure_api_version,
                    deployment_name=self.azure_deployment,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                print("✅ Azure OpenAI LangChain chat model initialized")

                # Dedicated instance for structured review with higher
                # max_tokens so the JSON output (summary + all inline
                # suggestions) does not get truncated.
                max_tokens_structured = self._safe_int(
                    llm_section.get("max_tokens_structured"),
                    default=max(max_tokens * 2, 8192),
                )
                self.azure_langchain_structured = AzureChatOpenAI(
                    azure_endpoint=self.azure_endpoint,
                    api_key=self.azure_key,
                    api_version=self.azure_api_version,
                    deployment_name=self.azure_deployment,
                    temperature=temperature,
                    max_tokens=max_tokens_structured,
                    model_kwargs={"response_format": {"type": "json_object"}},
                )
                print(f"✅ Azure OpenAI LangChain structured model initialized "
                      f"(max_tokens={max_tokens_structured}, JSON mode enabled)")

                # Build the reusable LangChain review chains
                self._init_review_chain()
                self._init_structured_review_chain()
            except Exception as e:
                # Don't fail initialization entirely if LangChain wiring has issues;
                # the SDK client can still be used as a fallback.
                print(f"⚠️  Failed to initialize Azure OpenAI LangChain model: {e}")

        if not self.anthropic and not self.azure_langchain and not self.azure:
            raise ValueError(
                "No LLM provider configured. Set ANTHROPIC_API_KEY or AZURE_OPENAI_* variables"
            )

    def _load_llm_config(self) -> Dict[str, Any]:
        """
        Load LLM configuration from the shared ai-review-config.yaml file.

        This allows central management of parameters like temperature and
        max_tokens while keeping environment variables as the primary source
        of provider credentials.
        """
        # Assume project layout with this file in scripts/, config in .github/
        root_dir = Path(__file__).resolve().parent.parent
        config_path = root_dir / ".github" / "ai-review-config.yaml"

        if not config_path.exists():
            return {}

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    return {}
                return data
        except Exception as e:
            print(f"⚠️  Failed to load LLM config from {config_path}: {e}")
            return {}

    def _safe_int(self, value: Any, default: int) -> int:
        """Convert a config value to int, falling back to default on error."""
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _init_review_chain(self) -> None:
        """Initialize the LangChain prompt and chain for Azure-based reviews."""
        if not self.azure_langchain:
            return

        system_prompt = self._build_system_prompt()

        # The user prompt mirrors _build_user_prompt but uses template variables
        self.review_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "user",
                    """# Pull Request Review Request

## PR Information
- **Title:** {title}
- **Author:** {author}
- **Base Branch:** {base_branch}
- **Files Changed:** {changed_files}
- **Lines Changed:** {lines_changed} (+{additions} -{deletions})

## PR Description
{description}

---

## Code Changes (Git Diff)
```diff
{diff}
```

---

## SonarQube Static Analysis
{sonar_context}

---

{file_context}

## Your Task
Perform a comprehensive code review focusing on security, quality, and best practices.
Provide actionable feedback structured according to the guidelines.
""",
                ),
            ]
        )

        self.review_chain = self.review_prompt | self.azure_langchain | StrOutputParser()

    def _init_structured_review_chain(self) -> None:
        """Initialize the LangChain chain that returns structured output
        (ReviewWithSuggestions) for inline suggestions.

        Uses the dedicated ``azure_langchain_structured`` model which has a
        higher ``max_tokens`` limit so the full JSON (summary + ALL inline
        suggestions) is not truncated.
        """
        # Prefer the dedicated structured model; fall back to the shared one
        llm_for_structured = self.azure_langchain_structured or self.azure_langchain
        if not llm_for_structured:
            return

        system_prompt = self._build_structured_system_prompt()

        self.structured_review_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "user",
                    """# Pull Request Review Request

## PR Information
- **Title:** {title}
- **Author:** {author}
- **Base Branch:** {base_branch}
- **Files Changed:** {changed_files}
- **Lines Changed:** {lines_changed} (+{additions} -{deletions})

## PR Description
{description}

---

## Full File Content (for summary context)
Below is the COMPLETE source code of each changed file, with line numbers.
Use this for context when writing the summary. The summary should cover issues found anywhere in the file.

{file_context}

---

## Code Changes (Annotated Diff with Line Numbers)
This shows ONLY the lines that were changed in this PR. Each added or context
line is annotated with ``# L<number>``. Inline suggestions MUST use these
exact ``# L`` line numbers, because GitHub can only display comments on lines
that appear in the diff.

```diff
{diff}
```

---

## SonarQube Static Analysis
{sonar_context}

---

## Your Task
1. Scan the diff for issues to create inline suggestions. Use the full file content to write a comprehensive summary.
2. Return your response as valid JSON matching the schema above.
   - ``inline_suggestions``: one entry for EVERY issue found in the annotated diff (has a ``# L`` marker). Use the exact ``# L`` number. Do NOT create inline suggestions for code that only appears in the full file content.
   - ``summary``: report ALL issues found anywhere in the file (including lines NOT in the diff). Be concise (3-8 sentences).
3. If an issue exists in the file but its line does NOT appear in the diff, mention it in the ``summary`` only — do NOT create an inline_suggestion for it (GitHub cannot display it).
4. ALWAYS provide ``suggested_code`` with valid source code (not natural language). Use ``""`` to delete lines. Use multi-line via ``end_line`` for consecutive problematic lines.

IMPORTANT: Inline suggestions are ONLY for issues in the diff. The summary covers the entire file.
IMPORTANT: ``suggested_code`` is applied DIRECTLY to the source file. It must be valid code, never explanatory text.

{format_instructions}
""",
                ),
            ]
        )

        # Create chain with custom output parser that handles JSON extraction
        from langchain_core.output_parsers import StrOutputParser
        
        self.structured_review_chain = (
            self.structured_review_prompt 
            | llm_for_structured 
            | StrOutputParser()
            | self._extract_and_parse_json
        )

    @staticmethod
    def _looks_like_natural_language(text: str) -> bool:
        """Return True if *text* appears to be natural language rather than code.

        Uses simple heuristics:
        - Starts with a common English verb/phrase (case-insensitive)
        - Contains no typical code characters (=, (, ), {, }, ;, :, [, ])
        """
        if not text or not text.strip():
            return False

        stripped = text.strip()

        # Common natural-language openers that are NOT valid code
        nl_prefixes = (
            "remove ", "delete ", "this ", "should ", "replace ",
            "consider ", "avoid ", "do not ", "don't ", "please ",
            "you should ", "it is ", "the ", "make sure ",
        )
        lower = stripped.lower()
        if any(lower.startswith(p) for p in nl_prefixes):
            return True

        # If the string has no typical code characters at all, it is likely prose
        code_chars = set("=(){}[];:+-*/<>@#!&|%^~\\")
        if not any(ch in code_chars for ch in stripped):
            # Pure alphabetic / space text is almost certainly natural language
            if all(ch.isalpha() or ch.isspace() or ch == ',' or ch == '.' for ch in stripped):
                return True

        return False

    def _extract_and_parse_json(self, text: str) -> ReviewWithSuggestions:
        """Extract JSON from LLM response and parse it into ReviewWithSuggestions.
        
        Handles cases where:
        - JSON is wrapped in markdown code blocks (```json ... ```)
        - Extra text appears before or after the JSON
        - Response contains explanations alongside JSON
        - ``suggested_code`` accidentally contains natural language (sanitized)
        """
        import json
        import re
        
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r'\{.*"summary".*"inline_suggestions".*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # If no JSON found, try the entire text
                json_str = text.strip()
        
        try:
            # Parse the JSON
            data = json.loads(json_str)
            
            # Validate and construct ReviewWithSuggestions
            summary = data.get("summary", "")
            inline_suggestions_data = data.get("inline_suggestions", [])
            
            # Parse inline suggestions
            inline_suggestions = []
            for suggestion_data in inline_suggestions_data:
                try:
                    raw_end_line = suggestion_data.get("end_line")
                    suggestion = InlineSuggestion(
                        file_path=suggestion_data.get("file_path", ""),
                        line=int(suggestion_data.get("line", 0)),
                        end_line=int(raw_end_line) if raw_end_line is not None else None,
                        message=suggestion_data.get("message", ""),
                        suggested_code=suggestion_data.get("suggested_code"),
                    )

                    # Sanitize: if suggested_code looks like natural language
                    # rather than source code, discard it to avoid corrupting
                    # the file when a user clicks "Apply suggestion".
                    if (suggestion.suggested_code is not None
                            and self._looks_like_natural_language(suggestion.suggested_code)):
                        print(f"⚠️  suggested_code looks like natural language, "
                              f"resetting to None: {suggestion.suggested_code!r}")
                        suggestion.suggested_code = None

                    inline_suggestions.append(suggestion)
                except Exception as e:
                    print(f"⚠️  Failed to parse inline suggestion: {e}")
                    print(f"    Suggestion data: {suggestion_data}")
                    continue
            
            return ReviewWithSuggestions(
                summary=summary,
                inline_suggestions=inline_suggestions
            )
            
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse JSON from LLM response: {e}")
            print(f"    Attempted to parse: {json_str[:500]}...")
            # Return empty response instead of failing
            return ReviewWithSuggestions(
                summary="Failed to parse structured review response.",
                inline_suggestions=[]
            )

    def _build_structured_system_prompt(self) -> str:
        """Build the system prompt used by the structured review chain."""
        return """You are an expert code reviewer. You will receive TWO inputs for each changed file:

1. **Full File Content** -- the complete source code with line numbers. Use this ONLY for writing the summary.
2. **Annotated Diff** -- only the changed lines, annotated with ``# L<number>`` markers. Scan this for issues to create inline suggestions.

Your job is to scan the diff for issues to create inline suggestions, and use the full file content to write a comprehensive summary.

## What to look for

**Security (Highest Priority)**
- SQL injection, XSS, CSRF vulnerabilities
- Authentication and authorization flaws
- Sensitive data exposure (API keys, passwords, tokens, hardcoded credentials)
- Insecure dependencies
- Input validation and sanitization
- Plaintext password storage

**Code Quality**
- Logic errors and edge cases
- Error handling and exception management
- Null/None checks missing
- Code duplication (DRY principle)
- Naming conventions and readability

**Performance**
- Database query optimization (N+1 queries, repeated queries)
- Memory leaks and resource management
- Unnecessary computations

**Best Practices**
- SOLID principles
- Separation of concerns
- Type hints and documentation

## Output Format

You MUST return ONLY a valid JSON object. Do NOT include any markdown code blocks, explanations, or text outside the JSON. The response must be parseable by json.loads().

The JSON must have exactly two fields:

### 1. ``inline_suggestions`` (array) - MOST IMPORTANT

Scan the annotated diff for issues. Create one entry for EVERY issue you find in the diff. Do NOT skip issues. Do NOT combine multiple issues into one entry. Each issue gets its own entry.

Only analyze and create suggestions for issues found in the annotated diff lines (those with ``# L`` markers). Do NOT create inline suggestions for code that is only visible in the full file content.

For each entry in the array, provide:
- ``file_path`` (string): the exact relative path from the diff ``File:`` header or ``+++`` header (e.g. ``src/app.py``)
- ``line`` (number): for single-line suggestions, the line number from ``# L``. For multi-line suggestions, the LAST (end) line of the range.
- ``end_line`` (number or null): for multi-line suggestions, the FIRST (start) line of the range. Must be less than ``line``. Use null for single-line suggestions.
- ``message`` (string): clear explanation of what is wrong, why it matters, and how to fix it
- ``suggested_code`` (string or null): the replacement code that will DIRECTLY replace the target line(s) in the source file when applied.

#### CRITICAL rules for ``suggested_code``

``suggested_code`` is inserted directly into the source file, replacing the target line(s). It must follow these rules:

1. **MUST be valid source code ONLY.** Never put natural language, explanations, or instructions in this field.
   - BAD: ``"Remove this line or replace with a comment"`` (this is natural language, NOT code)
   - BAD: ``"This should be deleted"`` (natural language)
   - GOOD: ``""`` (empty string — deletes the line)
   - GOOD: ``"    return app"`` (actual replacement code)
   - GOOD: ``"# TODO: fix SQL injection here"`` (a code comment IS valid code)

2. **To DELETE a line:** use an empty string ``""``. Do NOT use null for deletions.

3. **Use null ONLY** when you genuinely cannot suggest any concrete fix (purely informational comment).

4. **ALWAYS prefer providing a concrete fix** over null. Most issues have a fix — provide it.

5. **No diff markers or line numbers.** Only the raw replacement source code, preserving correct indentation.

6. **For multi-line suggestions:** ``suggested_code`` replaces ALL lines from ``end_line`` to ``line`` (inclusive). Include the full replacement for the entire range, with newlines between lines.

#### Rules for ``line`` and ``end_line``

- ONLY use line numbers from ``# L`` markers in the annotated diff section
- ONLY create suggestions for issues found in the diff lines
- Use the exact ``file_path`` as shown in the diff header
- Do NOT invent line numbers. Only use numbers from ``# L`` markers
- For a single problematic line: set ``line`` to the ``# L`` number, ``end_line`` to null
- For consecutive problematic lines (e.g. a multi-line statement): set ``end_line`` to the first ``# L`` number and ``line`` to the last ``# L`` number
- Maximum 25 suggestions. If more than 25 issues exist, prioritize by severity
- If NO issues are found in the diff, return an empty array: []

### 2. ``summary`` (string)

Use the full file content to write a comprehensive overview (3-8 sentences). Include:
- Overall assessment of the entire file
- ALL issues found anywhere in the file, including those on lines NOT in the diff
- For issues outside the diff, briefly describe them here since they cannot have inline comments
- Counts of issues by category
- Recommendation

## Example output structure

{{
  "summary": "This file has 3 issues in the diff: a debug print statement (lines 22-23), unreachable code due to bare return (line 24), and an existing SQL injection on line 45 outside the diff that should also be addressed.",
  "inline_suggestions": [
    {{
      "file_path": "src/app.py",
      "line": 23,
      "end_line": 22,
      "message": "Debug print statement with excessive brackets and unclear content. Remove before production to avoid cluttering logs and leaking internal information.",
      "suggested_code": ""
    }},
    {{
      "file_path": "src/app.py",
      "line": 24,
      "end_line": null,
      "message": "Bare `return` exits the function without returning the FastAPI app instance, causing `create_app()` to return None. This breaks application initialization.",
      "suggested_code": "    return app"
    }},
    {{
      "file_path": "src/app.py",
      "line": 17,
      "end_line": null,
      "message": "SQL injection: user input is interpolated directly into the query string. Use parameterized queries.",
      "suggested_code": "    query = \\"SELECT * FROM users WHERE id = %s\\""
    }}
  ]
}}

CRITICAL: Return ONLY the JSON object above. No code blocks, no markdown, no explanations.
"""

    def get_azure_langchain_model(self) -> Optional[AzureChatOpenAI]:
        """
        Expose the shared Azure LangChain chat model so other components
        (e.g. ReviewEventAnalyzer) can reuse the centralized configuration.
        """
        return self.azure_langchain

    # ------------------------------------------------------------------
    # Large diff handling helpers
    # ------------------------------------------------------------------

    def _estimate_token_count(self, text: str) -> int:
        """
        Rough token count estimate using character length.

        This avoids a heavyweight tokenizer while giving a good enough
        signal to decide when to switch to chunked processing.
        """
        if not text:
            return 0
        # Typical English text averages ~3–4 chars per token.
        return max(1, len(text) // 4)

    def _log_token_usage(
        self,
        label: str,
        input_text: str,
        output_text: str,
        real_usage: Optional[Any] = None,
    ) -> None:
        """Log token usage. Uses real API usage when provided, else estimate."""
        if real_usage is not None:
            # Anthropic: input_tokens, output_tokens
            # Azure: prompt_tokens, completion_tokens
            # Support both dict and object with attributes
            def _get(obj, *keys):
                for k in keys:
                    v = obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)
                    if v is not None:
                        return v
                return 0

            inp = _get(real_usage, "input_tokens", "prompt_tokens")
            out = _get(real_usage, "output_tokens", "completion_tokens")
            total = inp + out
            print(f"  Token usage ({label}): input={inp}, output={out}, total={total}")
        else:
            inp = self._estimate_token_count(input_text)
            out = self._estimate_token_count(output_text)
            print(f"  Token usage ({label}, est): input={inp}, output={out}, total={inp + out}")

    @staticmethod
    def _usage_from_ai_message(msg) -> Optional[dict]:
        """Extract token usage from LangChain AIMessage. Returns dict or None."""
        if msg is None:
            return None
        # usage_metadata (LangChain standard)
        um = getattr(msg, "usage_metadata", None)
        if um and (um.get("input_tokens") or um.get("output_tokens")):
            return um
        # response_metadata.token_usage (OpenAI/Azure)
        rm = getattr(msg, "response_metadata", None) or {}
        tu = rm.get("token_usage") or rm.get("usage")
        if tu:
            return tu
        return None

    def _split_unified_diff(self, diff: str) -> List[Dict[str, str]]:
        """
        Split a unified diff into per-file segments.

        The parsing is intentionally tolerant; it relies on common git diff
        markers but will still return best-effort segments if the diff is
        slightly malformed.
        """
        if not diff:
            return []

        files: List[Dict[str, str]] = []
        current_header: List[str] = []
        current_body: List[str] = []
        current_file_path: Optional[str] = None

        lines = diff.splitlines(keepends=True)

        def flush_current() -> None:
            if current_file_path is not None:
                files.append(
                    {
                        "file_path": current_file_path,
                        "header": "".join(current_header),
                        "body": "".join(current_body),
                    }
                )

        for line in lines:
            if line.startswith("diff --git "):
                # Start of a new file section
                flush_current()
                current_header = [line]
                current_body = []
                current_file_path = None
                continue

            if current_file_path is None:
                # Still in header for the current file
                current_header.append(line)
                if line.startswith("+++ "):
                    # Example: "+++ b/path/to/file.py"
                    path = line[4:].strip()
                    if path.startswith("a/") or path.startswith("b/"):
                        path = path[2:]
                    current_file_path = path or "<unknown>"
            else:
                # In body (hunks) for the current file
                current_body.append(line)

        flush_current()

        # If we didn't detect any file markers, treat the whole diff as one block
        if not files:
            files.append(
                {
                    "file_path": "<all>",
                    "header": "",
                    "body": diff,
                }
            )

        return files

    def _chunk_file_diff(self, file_diff: Dict[str, str], max_chars: int) -> List[Dict[str, Any]]:
        """
        Chunk a single file's diff body into smaller pieces, aiming to keep
        each chunk under `max_chars` once combined with the header.

        Chunks are aligned to hunk boundaries (lines starting with '@@')
        where possible to preserve local context.
        """
        header = file_diff.get("header", "")
        body = file_diff.get("body", "")
        file_path = file_diff.get("file_path", "<unknown>")

        if not body or len(header) + len(body) <= max_chars:
            return [
                {
                    "file_path": file_path,
                    "chunk_index": 1,
                    "total_chunks": 1,
                    "diff_snippet": f"{header}{body}",
                }
            ]

        hunks: List[str] = []
        current_hunk: List[str] = []

        for line in body.splitlines(keepends=True):
            if line.startswith("@@ ") and current_hunk:
                hunks.append("".join(current_hunk))
                current_hunk = [line]
            else:
                current_hunk.append(line)

        if current_hunk:
            hunks.append("".join(current_hunk))

        chunks: List[str] = []
        current_chunk_lines: List[str] = []
        current_size = len(header)

        for hunk in hunks:
            hunk_len = len(hunk)
            if current_chunk_lines and current_size + hunk_len > max_chars:
                chunks.append("".join(current_chunk_lines))
                current_chunk_lines = [hunk]
                current_size = len(header) + hunk_len
            else:
                current_chunk_lines.append(hunk)
                current_size += hunk_len

        if current_chunk_lines:
            chunks.append("".join(current_chunk_lines))

        total_chunks = len(chunks)
        result: List[Dict[str, Any]] = []
        for idx, chunk_body in enumerate(chunks, start=1):
            result.append(
                {
                    "file_path": file_path,
                    "chunk_index": idx,
                    "total_chunks": total_chunks,
                    "diff_snippet": f"{header}{chunk_body}",
                }
            )

        return result

    def _prioritize_file_diffs(self, file_diffs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Simple heuristic-based prioritization for file diffs.

        Code files (e.g., .py, .js, .ts, etc.) are processed first, and other
        files come later. This helps when we need to cut off processing after
        reaching a global budget.
        """
        priority_exts = {
            ".py": 0,
            ".js": 0,
            ".ts": 0,
            ".jsx": 0,
            ".tsx": 0,
            ".java": 0,
            ".go": 0,
            ".cpp": 0,
            ".c": 0,
            ".cs": 0,
            ".php": 0,
            ".rb": 0,
            ".swift": 0,
            ".kt": 0,
        }

        def sort_key(fd: Dict[str, str]) -> int:
            path = fd.get("file_path", "")
            for ext, prio in priority_exts.items():
                if path.endswith(ext):
                    return prio
            return 10

        return sorted(file_diffs, key=sort_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def review_with_claude(self, system_prompt: str, user_content: str) -> str:
        """Call Claude Sonnet 4.5 for code review"""
        if not self.anthropic:
            raise ValueError("Anthropic client not initialized")

        print("🤖 Calling Claude Sonnet 4.5...")

        response = self.anthropic.messages.create(
            model="claude-sonnet-4-20250514",  # Claude Sonnet 4.5
            max_tokens=4096,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_content}
            ]
        )

        output_text = response.content[0].text
        self._log_token_usage(
            "Claude",
            system_prompt + user_content,
            output_text,
            getattr(response, "usage", None),
        )
        return output_text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def review_with_azure_openai(self, system_prompt: str, user_content: str) -> str:
        """Call Azure OpenAI GPT-4 for code review"""
        if not self.azure:
            raise ValueError("Azure OpenAI client not initialized")

        print(f"🤖 Calling Azure OpenAI ({self.azure_deployment})...")

        response = self.azure.chat.completions.create(
            model=self.azure_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=4096,
            temperature=0.3
        )

        output_text = response.choices[0].message.content
        self._log_token_usage(
            "Azure",
            system_prompt + user_content,
            output_text,
            getattr(response, "usage", None),
        )
        return output_text

    def _aggregate_chunk_reviews(self, chunk_reviews: List[str], truncated: bool) -> str:
        """
        Combine per-chunk reviews into a single markdown review string.

        The individual chunk reviews already follow the expected response
        format, so we mostly need to join them and optionally add a short
        preamble when truncation occurs.
        """
        if not chunk_reviews:
            return "No review could be generated for the provided diff."

        combined = "\n\n".join(chunk_reviews)

        if truncated:
            notice = (
                "⚠️ **Note:** The pull request diff is very large. "
                "Only a subset of files/chunks were reviewed due to size limits. "
                "Prioritized files with likely higher impact were analyzed first.\n\n"
            )
            return f"{notice}{combined}"

        return combined

    def _review_large_diff_with_claude(
        self,
        diff: str,
        sonar_context: str,
        pr_info: dict,
        file_context: str = "",
    ) -> str:
        """
        Handle very large diffs by chunking them and calling Claude on each
        chunk separately, then aggregating the results.
        """
        if not self.anthropic:
            raise ValueError("Anthropic client not initialized")

        system_prompt = self._build_system_prompt()

        file_diffs = self._split_unified_diff(diff)
        file_diffs = self._prioritize_file_diffs(file_diffs)

        remaining_budget = self.max_total_diff_chars
        chunk_reviews: List[str] = []
        truncated = False

        for file_diff in file_diffs:
            if remaining_budget <= 0:
                truncated = True
                break

            chunks = self._chunk_file_diff(file_diff, self.max_diff_chars_per_call)
            for chunk in chunks:
                snippet = chunk["diff_snippet"]
                snippet_len = len(snippet)
                if snippet_len > remaining_budget:
                    truncated = True
                    break

                # Build a prompt for this specific chunk
                user_content = self._build_user_prompt(
                    diff=snippet,
                    sonar_context=sonar_context,
                    pr_info=pr_info,
                    file_context=file_context,
                )

                review = self.review_with_claude(system_prompt, user_content)
                prefix = (
                    f"### File: {chunk['file_path']} "
                    f"(chunk {chunk['chunk_index']}/{chunk['total_chunks']})\n\n"
                )
                chunk_reviews.append(f"{prefix}{review}")
                remaining_budget -= snippet_len

            if remaining_budget <= 0:
                truncated = True
                break

        return self._aggregate_chunk_reviews(chunk_reviews, truncated)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def review_with_azure_langchain(
        self,
        diff: str,
        sonar_context: str,
        pr_info: dict,
        file_context: str = "",
    ) -> str:
        """Call Azure OpenAI via the shared LangChain chain for code review."""
        if not self.azure_langchain or not self.review_chain:
            raise ValueError("Azure LangChain review chain not initialized")

        print(f"🤖 Calling Azure OpenAI via LangChain ({self.azure_deployment})...")

        # Safely extract PR info with defaults to avoid KeyError
        additions = pr_info.get("additions", 0) if pr_info.get("additions") is not None else 0
        deletions = pr_info.get("deletions", 0) if pr_info.get("deletions") is not None else 0
        lines_changed = additions + deletions

        variables = {
            "title": str(pr_info.get("title") or "N/A"),
            "author": str(pr_info.get("author") or "Unknown"),
            "base_branch": str(pr_info.get("base_branch") or "unknown"),
            "changed_files": int(pr_info.get("changed_files") or 0),
            "lines_changed": int(lines_changed),
            "additions": int(additions),
            "deletions": int(deletions),
            "description": str(pr_info.get("description") or "No description provided"),
            "diff": str(diff),
            "sonar_context": str(sonar_context or "No SonarQube analysis available"),
            "file_context": str(file_context or ""),
        }

        # Invoke up to LLM to capture AIMessage (with usage)
        ai_message = (self.review_prompt | self.azure_langchain).invoke(variables)
        usage = self._usage_from_ai_message(ai_message)
        result = StrOutputParser().invoke(ai_message)
        input_text = (
            str(variables.get("diff", ""))
            + str(variables.get("sonar_context", ""))
            + str(variables.get("file_context", ""))
        )
        self._log_token_usage("Azure LangChain", input_text, result, usage)
        return result

    def _review_large_diff_with_azure_langchain(
        self,
        diff: str,
        sonar_context: str,
        pr_info: dict,
        file_context: str = "",
    ) -> str:
        """
        Handle very large diffs by chunking them and calling the Azure
        LangChain review chain on each chunk separately, then aggregating
        the results.
        """
        if not self.azure_langchain or not self.review_chain:
            raise ValueError("Azure LangChain review chain not initialized")

        file_diffs = self._split_unified_diff(diff)
        file_diffs = self._prioritize_file_diffs(file_diffs)

        remaining_budget = self.max_total_diff_chars
        chunk_reviews: List[str] = []
        truncated = False

        # Safely extract PR info with defaults to avoid KeyError
        additions = pr_info.get("additions", 0) if pr_info.get("additions") is not None else 0
        deletions = pr_info.get("deletions", 0) if pr_info.get("deletions") is not None else 0
        lines_changed = additions + deletions

        for file_diff in file_diffs:
            if remaining_budget <= 0:
                truncated = True
                break

            chunks = self._chunk_file_diff(file_diff, self.max_diff_chars_per_call)
            for chunk in chunks:
                snippet = chunk["diff_snippet"]
                snippet_len = len(snippet)
                if snippet_len > remaining_budget:
                    truncated = True
                    break

                variables = {
                    "title": str(pr_info.get("title") or "N/A"),
                    "author": str(pr_info.get("author") or "Unknown"),
                    "base_branch": str(pr_info.get("base_branch") or "unknown"),
                    "changed_files": int(pr_info.get("changed_files") or 0),
                    "lines_changed": int(lines_changed),
                    "additions": int(additions),
                    "deletions": int(deletions),
                    "description": str(pr_info.get("description") or "No description provided"),
                    "diff": str(snippet),
                    "sonar_context": str(sonar_context or "No SonarQube analysis available"),
                    "file_context": str(file_context or ""),
                }

                ai_message = (self.review_prompt | self.azure_langchain).invoke(variables)
                usage = self._usage_from_ai_message(ai_message)
                review = StrOutputParser().invoke(ai_message)
                input_text = (
                    str(variables.get("diff", ""))
                    + str(variables.get("sonar_context", ""))
                    + str(variables.get("file_context", ""))
                )
                self._log_token_usage(
                    f"Azure LangChain chunk {chunk['chunk_index']}/{chunk['total_chunks']}",
                    input_text,
                    review,
                    usage,
                )
                prefix = (
                    f"### File: {chunk['file_path']} "
                    f"(chunk {chunk['chunk_index']}/{chunk['total_chunks']})\n\n"
                )
                chunk_reviews.append(f"{prefix}{review}")
                remaining_budget -= snippet_len

            if remaining_budget <= 0:
                truncated = True
                break

        return self._aggregate_chunk_reviews(chunk_reviews, truncated)

    def review_code(self, diff: str, sonar_context: str, 
                   pr_info: dict, file_context: str = "") -> str:
        """Main review method with fallback logic

        Args:
            diff: Git diff of changes
            sonar_context: SonarQube analysis results
            pr_info: PR metadata (title, description, etc.)
            file_context: Additional file context if needed

        Returns:
            AI-generated review text
        """

        approx_tokens = self._estimate_token_count(diff)
        is_large_diff = approx_tokens > self.max_tokens_per_diff

        # Try Claude first (recommended from strategic doc)
        if self.anthropic:
            try:
                if is_large_diff:
                    print("ℹ️ Detected large diff; using chunked processing with Claude.")
                    return self._review_large_diff_with_claude(
                        diff=diff,
                        sonar_context=sonar_context,
                        pr_info=pr_info,
                        file_context=file_context,
                    )
                else:
                    system_prompt = self._build_system_prompt()
                    user_content = self._build_user_prompt(
                        diff, sonar_context, pr_info, file_context
                    )
                    return self.review_with_claude(system_prompt, user_content)
            except Exception as e:
                print(f"❌ Claude failed: {e}")
                if self.azure or self.azure_langchain:
                    print("⚠️  Falling back to Azure OpenAI...")
                else:
                    raise

        # Prefer the centralized LangChain-based Azure path when available
        if self.azure_langchain and self.review_chain is not None:
            try:
                if is_large_diff:
                    print("ℹ️ Detected large diff; using chunked processing with Azure LangChain.")
                    return self._review_large_diff_with_azure_langchain(
                        diff=diff,
                        sonar_context=sonar_context,
                        pr_info=pr_info,
                        file_context=file_context,
                    )
                else:
                    return self.review_with_azure_langchain(
                        diff=diff,
                        sonar_context=sonar_context,
                        pr_info=pr_info,
                        file_context=file_context,
                    )
            except Exception as e:
                print(f"❌ Azure OpenAI via LangChain failed: {e}")
                if self.azure:
                    print("⚠️  Falling back to Azure OpenAI SDK client...")
                else:
                    raise

        # Fallback to Azure OpenAI SDK client
        if self.azure:
            try:
                system_prompt = self._build_system_prompt()
                if is_large_diff:
                    print("ℹ️ Detected large diff; using chunked processing with Azure SDK client.")
                    # Reuse the Claude large-diff logic pattern but with SDK calls per chunk
                    file_diffs = self._split_unified_diff(diff)
                    file_diffs = self._prioritize_file_diffs(file_diffs)

                    remaining_budget = self.max_total_diff_chars
                    chunk_reviews: List[str] = []
                    truncated = False

                    for file_diff in file_diffs:
                        if remaining_budget <= 0:
                            truncated = True
                            break

                        chunks = self._chunk_file_diff(file_diff, self.max_diff_chars_per_call)
                        for chunk in chunks:
                            snippet = chunk["diff_snippet"]
                            snippet_len = len(snippet)
                            if snippet_len > remaining_budget:
                                truncated = True
                                break

                            user_content = self._build_user_prompt(
                                diff=snippet,
                                sonar_context=sonar_context,
                                pr_info=pr_info,
                                file_context=file_context,
                            )
                            review = self.review_with_azure_openai(system_prompt, user_content)
                            prefix = (
                                f"### File: {chunk['file_path']} "
                                f"(chunk {chunk['chunk_index']}/{chunk['total_chunks']})\n\n"
                            )
                            chunk_reviews.append(f"{prefix}{review}")
                            remaining_budget -= snippet_len

                        if remaining_budget <= 0:
                            truncated = True
                            break

                    return self._aggregate_chunk_reviews(chunk_reviews, truncated)
                else:
                    user_content = self._build_user_prompt(
                        diff, sonar_context, pr_info, file_context
                    )
                    return self.review_with_azure_openai(system_prompt, user_content)
            except Exception as e:
                print(f"❌ Azure OpenAI SDK client failed: {e}")
                raise

        raise Exception("All LLM providers failed")

    def review_code_structured(
        self,
        diff: str,
        sonar_context: str,
        pr_info: dict,
        file_context: str = "",
    ) -> ReviewWithSuggestions:
        """Review code and return structured output with inline suggestions.

        This annotates the diff with line numbers, then calls the structured
        LangChain chain to get a ``ReviewWithSuggestions`` object containing
        both the review summary and a list of inline suggestions.

        For large diffs the method falls back to the plain-text review
        (``review_code``) wrapped in a ``ReviewWithSuggestions`` with an
        empty ``inline_suggestions`` list.

        Args:
            diff: Git diff of changes
            sonar_context: SonarQube analysis results
            pr_info: PR metadata
            file_context: Additional file context if needed

        Returns:
            ReviewWithSuggestions with summary and inline_suggestions
        """
        approx_tokens = self._estimate_token_count(diff)
        is_large_diff = approx_tokens > self.max_tokens_per_diff

        # For large diffs, fall back to plain summary only (no inline suggestions)
        if is_large_diff:
            print("ℹ️  Large diff detected; using plain review (no inline suggestions).")
            plain_review = self.review_code(
                diff=diff,
                sonar_context=sonar_context,
                pr_info=pr_info,
                file_context=file_context,
            )
            return ReviewWithSuggestions(
                summary=plain_review,
                inline_suggestions=[],
            )

        # Annotate diff with line numbers for the LLM
        annotated_diff = annotate_diff_with_line_numbers(diff)

        # Try structured chain (Azure LangChain – dedicated or shared model)
        if (self.azure_langchain_structured or self.azure_langchain) and self.structured_review_chain is not None:
            try:
                return self._invoke_structured_review(
                    annotated_diff, sonar_context, pr_info, file_context
                )
            except KeyError as e:
                print(f"⚠️  Structured review failed due to missing key: {e}")
                print(f"    PR info keys: {list(pr_info.keys())}")
                print("⚠️  Falling back to plain review...")
            except Exception as e:
                print(f"⚠️  Structured review via LangChain failed: {e}")
                import traceback
                print(f"    Full traceback: {traceback.format_exc()}")
                print("⚠️  Falling back to plain review...")

        # Fallback: plain review wrapped in ReviewWithSuggestions
        plain_review = self.review_code(
            diff=diff,
            sonar_context=sonar_context,
            pr_info=pr_info,
            file_context=file_context,
        )
        return ReviewWithSuggestions(
            summary=plain_review,
            inline_suggestions=[],
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _invoke_structured_review(
        self,
        annotated_diff: str,
        sonar_context: str,
        pr_info: dict,
        file_context: str = "",
    ) -> ReviewWithSuggestions:
        """Invoke the structured review chain and return parsed output."""
        if not self.structured_review_chain:
            raise ValueError("Structured review chain not initialized")

        print(f"🤖 Calling Azure OpenAI via LangChain for structured review "
              f"({self.azure_deployment})...")

        # Safely extract PR info with defaults to avoid KeyError
        additions = pr_info.get("additions", 0) if pr_info.get("additions") is not None else 0
        deletions = pr_info.get("deletions", 0) if pr_info.get("deletions") is not None else 0
        lines_changed = additions + deletions

        variables = {
            "title": str(pr_info.get("title") or "N/A"),
            "author": str(pr_info.get("author") or "Unknown"),
            "base_branch": str(pr_info.get("base_branch") or "unknown"),
            "changed_files": int(pr_info.get("changed_files") or 0),
            "lines_changed": int(lines_changed),
            "additions": int(additions),
            "deletions": int(deletions),
            "description": str(pr_info.get("description") or "No description provided"),
            "diff": str(annotated_diff),
            "sonar_context": str(sonar_context or "No SonarQube analysis available"),
            "file_context": str(file_context or ""),
            "format_instructions": str(self.structured_parser.get_format_instructions()),
        }

        # Invoke up to LLM to capture AIMessage (with usage)
        llm_for_structured = self.azure_langchain_structured or self.azure_langchain
        ai_message = (self.structured_review_prompt | llm_for_structured).invoke(variables)
        usage = self._usage_from_ai_message(ai_message)
        raw_text = StrOutputParser().invoke(ai_message)
        result = self._extract_and_parse_json(raw_text)
        input_text = (
            str(annotated_diff)
            + str(sonar_context or "")
            + str(file_context or "")
        )
        output_text = result.summary if hasattr(result, "summary") else str(result)
        self._log_token_usage("Structured review", input_text, output_text, usage)
        return result

    def _build_system_prompt(self) -> str:
        """Build system prompt for code review"""
        return """You are an expert code reviewer with deep knowledge of:
- Software engineering best practices and design patterns
- Security vulnerabilities (OWASP Top 10, CWE)
- Performance optimization
- Code maintainability and readability
- Testing strategies

Your role is to analyze code changes critically AND provide precise, line-level fixes.

## Review Guidelines

**Security (Highest Priority)**
- SQL injection, XSS, CSRF vulnerabilities
- Authentication and authorization flaws
- Sensitive data exposure (API keys, passwords, tokens)
- Insecure dependencies
- Input validation and sanitization

**Code Quality**
- Logic errors and edge cases
- Error handling and exception management
- Code complexity (cyclomatic complexity)
- Code duplication (DRY principle)
- Naming conventions and readability
- Function/method length and single responsibility

**Performance**
- Algorithmic complexity (O(n) analysis)
- Database query optimization (N+1 queries)
- Memory leaks and resource management
- Unnecessary computations in loops
- Caching opportunities

**Best Practices**
- SOLID principles
- Design patterns appropriate usage
- Separation of concerns
- Dependency injection
- Configuration management

## Mandatory Fix Instructions

For EVERY issue found:
- Specify the exact file name
- Specify the exact line number(s)
- Clearly explain what is wrong
- Provide the corrected code snippet
- Show the suggested replacement inside a proper code block
- Ensure suggested code is production-ready and complete

When possible, show:
- "Before" (problematic code)
- "After" (fixed code)

## Response Format

Structure your review as:

### 🔍 Summary
[1-2 sentence overall assessment]

### 🚨 Critical Issues
[Issues that MUST be fixed before merge - security, bugs]

For each issue:
- **File:** <filename>
- **Line:** <line number or range>
- **Problem:** Clear explanation
- **Suggested Fix:**
```code
# corrected replacement code
"""

    def _build_user_prompt(self, diff: str, sonar_context: str, 
                          pr_info: dict, file_context: str) -> str:
        """Build user prompt with all context"""

        lines_changed = pr_info.get('additions', 0) + pr_info.get('deletions', 0)

        prompt = f"""# Pull Request Review Request

## PR Information
- **Title:** {pr_info.get('title', 'N/A')}
- **Author:** {pr_info.get('author', 'Unknown')}
- **Base Branch:** {pr_info.get('base_branch', 'unknown')}
- **Files Changed:** {pr_info.get('changed_files', 0)}
- **Lines Changed:** {lines_changed} (+{pr_info.get('additions', 0)} -{pr_info.get('deletions', 0)})

## PR Description
{pr_info.get('description', 'No description provided')}

---

## Code Changes (Git Diff)
```diff
{diff}
```

---

## SonarQube Static Analysis
{sonar_context}

---

{file_context if file_context else ''}

## Your Task
Perform a comprehensive code review focusing on security, quality, and best practices.
Provide actionable feedback structured according to the guidelines.
"""

        return prompt