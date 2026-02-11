"""
LLM Client for AI Code Review
Supports Claude (Anthropic) and GPT-4 (Azure OpenAI)

This module centralizes Azure OpenAI configuration and exposes both
SDK-based and LangChain-based interfaces for use throughout the codebase.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import AzureChatOpenAI


class LLMClient:
    """Client for interacting with LLM providers"""

    def __init__(self):
        # Load optional configuration (e.g., temperature, max_tokens)
        self.llm_config: Dict[str, Any] = self._load_llm_config()

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

                # Build the reusable LangChain review chain
                self._init_review_chain()
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

    def get_azure_langchain_model(self) -> Optional[AzureChatOpenAI]:
        """
        Expose the shared Azure LangChain chat model so other components
        (e.g. ReviewEventAnalyzer) can reuse the centralized configuration.
        """
        return self.azure_langchain

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

        return response.content[0].text

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

        return response.choices[0].message.content

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

        additions = pr_info.get("additions", 0)
        deletions = pr_info.get("deletions", 0)
        lines_changed = additions + deletions

        variables = {
            "title": pr_info.get("title", "N/A"),
            "author": pr_info.get("author", "Unknown"),
            "base_branch": pr_info.get("base_branch", "unknown"),
            "changed_files": pr_info.get("changed_files", 0),
            "lines_changed": lines_changed,
            "additions": additions,
            "deletions": deletions,
            "description": pr_info.get("description", "No description provided"),
            "diff": diff,
            "sonar_context": sonar_context,
            "file_context": file_context or "",
        }

        return self.review_chain.invoke(variables)

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

        system_prompt = self._build_system_prompt()
        user_content = self._build_user_prompt(diff, sonar_context, pr_info, file_context)

        # Try Claude first (recommended from strategic doc)
        if self.anthropic:
            try:
                return self.review_with_claude(system_prompt, user_content)
            except Exception as e:
                print(f"❌ Claude failed: {e}")
                if self.azure:
                    print("⚠️  Falling back to Azure OpenAI...")
                else:
                    raise

        # Prefer the centralized LangChain-based Azure path when available
        if self.azure_langchain and self.review_chain is not None:
            try:
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
                return self.review_with_azure_openai(system_prompt, user_content)
            except Exception as e:
                print(f"❌ Azure OpenAI SDK client failed: {e}")
                raise

        raise Exception("All LLM providers failed")

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
