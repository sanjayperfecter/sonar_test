#!/usr/bin/env python3
"""
AI Code Review Agent - Main Script
Orchestrates the complete review workflow with LangChain integration
"""

import os
import sys
from pathlib import Path
from typing import Literal

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from github_api import GitHubClient
from sonar_api import SonarClient
from llm_client import LLMClient

# LangChain imports
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


class ReviewDecision(BaseModel):
    """Structured output for review decision"""
    event_type: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"] = Field(
        description="The GitHub review event type to use"
    )
    reasoning: str = Field(
        description="Clear explanation of why this decision was made"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence level in this decision (0.0 to 1.0)"
    )
    critical_issues_found: bool = Field(
        description="Whether critical issues were identified"
    )


class ReviewEventAnalyzer:
    """LangChain-based analyzer for determining review event type"""

    def __init__(self, llm):
        """Initialize the LangChain analyzer with an injected LLM instance.

        The LLM should be a LangChain-compatible chat model, typically the
        shared AzureChatOpenAI instance provided by LLMClient.
        """
        if llm is None:
            raise ValueError(
                "Azure LangChain LLM is not configured. "
                "Ensure Azure OpenAI is set up before initializing ReviewEventAnalyzer."
            )

        self.llm = llm

        # Setup output parser
        self.parser = PydanticOutputParser(pydantic_object=ReviewDecision)
        
        # Create the analysis prompt
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert code review decision analyzer. Your job is to analyze a code review 
and determine the appropriate GitHub review action.

Review Event Types:
- APPROVE: Code is excellent with no issues or only minor suggestions. Quality gate passed.
- REQUEST_CHANGES: Critical issues, security vulnerabilities, or quality gate failures that must be fixed.
- COMMENT: Moderate issues or suggestions that don't block merging but should be addressed.

Decision Criteria:

REQUEST_CHANGES when:
- Security vulnerabilities (SQL injection, XSS, authentication issues, data exposure)
- Critical bugs or logic errors that will cause failures
- SonarQube quality gate status is ERROR/FAILED
- Blocker or Critical severity issues from SonarQube
- Code introduces breaking changes without proper handling
- Performance issues that will cause system degradation
- Data corruption or loss risks

APPROVE when:
- No critical or important issues identified
- Only minor suggestions or style improvements
- SonarQube quality gate passed (OK/SUCCESS)
- No security concerns
- Code follows best practices
- Review text is explicitly positive

COMMENT when:
- Moderate issues that should be addressed but don't block merge
- Suggestions for improvement that aren't critical
- Code smells or maintainability concerns
- Minor performance optimizations
- Documentation improvements needed
- Unclear about severity (default to COMMENT when uncertain)

{format_instructions}"""),
            ("user", """Analyze this code review and determine the appropriate GitHub review event.

AI Review Text:
{review_text}

SonarQube Analysis:
- Quality Gate Status: {quality_gate_status}
- Total Issues: {issue_count}
- Blocker Issues: {blocker_count}
- Critical Issues: {critical_count}
- Major Issues: {major_count}

SonarQube Issue Details:
{sonar_issues_summary}

Based on this information, determine the review event type with reasoning.""")
        ])
        
        # Create the chain
        self.chain = self.prompt | self.llm | self.parser
    
    def analyze(self, review_text: str, sonar_issues: list, 
                quality_gate: dict) -> ReviewDecision:
        """
        Analyze review and determine event type using LangChain
        
        Args:
            review_text: The AI-generated review text
            sonar_issues: List of SonarQube issues
            quality_gate: SonarQube quality gate status
            
        Returns:
            ReviewDecision with event type and reasoning
        """
        # Count issues by severity
        blocker_count = sum(1 for issue in sonar_issues 
                           if issue.get('severity') == 'BLOCKER')
        critical_count = sum(1 for issue in sonar_issues 
                            if issue.get('severity') == 'CRITICAL')
        major_count = sum(1 for issue in sonar_issues 
                         if issue.get('severity') == 'MAJOR')
        
        # Format SonarQube issues summary
        sonar_summary = self._format_sonar_summary(sonar_issues)
        
        # Invoke the chain
        try:
            decision = self.chain.invoke({
                "review_text": review_text,
                "quality_gate_status": quality_gate.get('status', 'UNKNOWN'),
                "issue_count": len(sonar_issues),
                "blocker_count": blocker_count,
                "critical_count": critical_count,
                "major_count": major_count,
                "sonar_issues_summary": sonar_summary,
                "format_instructions": self.parser.get_format_instructions()
            })
            
            return decision
            
        except Exception as e:
            print(f"⚠️  Error in LangChain analysis: {e}")
            # Fallback to conservative decision
            return ReviewDecision(
                event_type="COMMENT",
                reasoning=f"Error during analysis, defaulting to COMMENT: {str(e)}",
                confidence=0.5,
                critical_issues_found=blocker_count > 0 or critical_count > 0
            )
    
    def _format_sonar_summary(self, sonar_issues: list) -> str:
        """Format SonarQube issues for context"""
        if not sonar_issues:
            return "No SonarQube issues found."
        
        summary_lines = []
        for issue in sonar_issues[:10]:  # Limit to first 10 issues
            severity = issue.get('severity', 'UNKNOWN')
            message = issue.get('message', 'No message')
            rule = issue.get('rule', 'Unknown rule')
            summary_lines.append(f"- [{severity}] {message} (Rule: {rule})")
        
        if len(sonar_issues) > 10:
            summary_lines.append(f"... and {len(sonar_issues) - 10} more issues")
        
        return "\n".join(summary_lines)


def _filter_diff_excluded_paths(diff: str) -> str:
    """
    Remove diff sections for files we don't want to process.

    Specifically, skip:
    - Any file under a `scripts/` folder
    - Any file whose name contains the word 'script' (case-insensitive)
    """
    if not diff:
        return diff

    lines = diff.splitlines(keepends=True)

    blocks = []
    current_lines = []
    current_file_path = None

    def flush_block():
        nonlocal current_lines, current_file_path
        if current_lines:
            blocks.append((current_file_path, "".join(current_lines)))
        current_lines = []
        current_file_path = None

    for line in lines:
        if line.startswith("diff --git "):
            flush_block()
            current_lines = [line]
            current_file_path = None
            continue

        current_lines.append(line)

        if current_file_path is None and line.startswith("+++ "):
            # Example: "+++ b/path/to/file.py"
            path = line[4:].strip()
            if path.startswith("a/") or path.startswith("b/"):
                path = path[2:]
            current_file_path = path or "<unknown>"

    flush_block()

    def is_excluded(path: str | None) -> bool:
        if not path or path == "<unknown>":
            return False

        normalized = path.lower()

        # Skip anything under a scripts/ folder
        if normalized.startswith("scripts/") or "/scripts/" in normalized:
            return True

        # Skip any file whose name contains 'script'
        filename = os.path.basename(normalized)
        if "script" in filename:
            return True

        return False

    kept_blocks = [block for file_path, block in blocks if not is_excluded(file_path)]
    return "".join(kept_blocks)


def print_banner():
    """Print startup banner"""
    print("=" * 80)
    print("🤖 AI Code Review Agent (LangChain Enhanced)")
    print("=" * 80)


def main():
    """Main review workflow"""
    print_banner()
    
    try:
       
        # Initialize clients
        print("\n📦 Initializing clients...")
        github = GitHubClient()
        sonar = SonarClient()
        llm = LLMClient()

        # Initialize LangChain analyzer using the shared Azure LLM
        print("  🔗 Initializing LangChain analyzer...")
        azure_llm = llm.get_azure_langchain_model()
        if not azure_llm:
            raise RuntimeError(
                "Azure LangChain model is not configured; "
                "cannot perform LangChain-based review decision analysis."
            )
        review_analyzer = ReviewEventAnalyzer(azure_llm)

        # Get PR information
        print("\n📋 Fetching PR information...")
        pr_info = github.get_pr_info()
        print(f"  PR #{pr_info['number']}: {pr_info['title']}")
        print(f"  Author: {pr_info['author']}")
        print(f"  Changes: {pr_info['changed_files']} files, "
              f"+{pr_info['additions']} -{pr_info['deletions']} lines")

        # Get PR diff
        print("\n📥 Fetching code changes...")
        diff = github.get_pr_diff()

        # Filter out script-related files that should not be processed
        diff = _filter_diff_excluded_paths(diff)

        if not diff.strip():
            print("⚠️  No reviewable code changes detected")
            github.post_comment(
                "ℹ️ **AI Code Review Skipped**\n\n"
                "No reviewable code changes found in this PR. "
                "This might be due to:\n"
                "- Only documentation/config file changes\n"
                "- Files excluded by configuration\n"
                "- No changes in supported file types"
            )
            github.set_status("success", "No code changes to review", "ai-code-review")
            return 0

        print(f"  ✅ Found code changes to review")

        # Get SonarQube analysis
        print("\n🔍 Fetching SonarQube analysis...")
        pr_number = pr_info['number']
        sonar_issues = sonar.get_issues_for_pr(pr_number)
        quality_gate = sonar.get_quality_gate_status(pr_number)

        # Format SonarQube context
        sonar_context = sonar.format_issues_for_context(sonar_issues)
        quality_gate_text = sonar.format_quality_gate(quality_gate)

        print(f"  {quality_gate_text}")
        print(f"  Found {len(sonar_issues)} issues")

        # Perform AI review (structured: summary + inline suggestions)
        print("\n🤖 Running AI code review...")
        github.set_status("pending", "AI review in progress...", "ai-code-review")

        try:
            structured_review = llm.review_code_structured(
                diff=diff,
                sonar_context=sonar_context,
                pr_info=pr_info,
                file_context=""
            )
            review_result = structured_review.summary
            inline_suggestions = structured_review.inline_suggestions
            print(f"  ✅ AI review completed "
                  f"({len(inline_suggestions)} inline suggestion(s))")

        except Exception as e:
            print(f"\n❌ AI review failed: {e}")
            github.post_comment(
                f"❌ **AI Code Review Failed**\n\n"
                f"An error occurred during AI analysis:\n"
                f"```\n{str(e)}\n```\n\n"
                f"Please check the workflow logs for details."
            )
            return 1

        # Determine review event using LangChain
        print("\n🎯 Analyzing review decision with LangChain...")
        decision = review_analyzer.analyze(review_result, sonar_issues, quality_gate)
        
        print(f"  Event Type: {decision.event_type}")
        print(f"  Confidence: {decision.confidence:.2%}")
        print(f"  Critical Issues: {decision.critical_issues_found}")
        print(f"  Reasoning: {decision.reasoning}")

        # Build inline comments for GitHub from LLM suggestions
        inline_comments = _build_inline_comments(inline_suggestions, pr_info)

        # Post review summary + inline comments
        print("\n📝 Posting review...")
        summary = format_review_summary(
            review_result, 
            quality_gate_text, 
            len(sonar_issues),
            pr_info,
            decision
        )

        if inline_comments:
            print(f"  📌 Including {len(inline_comments)} inline comment(s)")
            github.post_review_with_comments(
                summary, decision.event_type, inline_comments
            )
        else:
            github.post_review_summary(summary, decision.event_type)

        # Set final status
        if decision.event_type == "APPROVE":
            github.set_status("success", "✅ AI review: Approved", "ai-code-review")
        elif decision.event_type == "REQUEST_CHANGES":
            github.set_status("failure", "❌ AI review: Changes requested", "ai-code-review")
        else:
            github.set_status("success", "✅ AI review: Comments posted", "ai-code-review")

        print("\n✅ Review completed successfully!")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

        try:
            github = GitHubClient()
        except:
            pass

        return 1


MAX_INLINE_COMMENTS = 25  # Cap to avoid spamming the PR


def _build_inline_comments(
    inline_suggestions: list,
    pr_info: dict,
) -> list:
    """Convert LLM inline suggestions into GitHub review comment dicts.

    Each returned dict has the keys expected by
    ``GitHubClient.post_review_with_comments``: ``path``, ``line``,
    ``side``, and ``body``.

    Suggestions without a valid ``line`` or ``file_path`` are silently
    skipped. The list is capped at ``MAX_INLINE_COMMENTS``.
    """
    comments = []

    for suggestion in inline_suggestions:
        file_path = getattr(suggestion, "file_path", None) or ""
        line = getattr(suggestion, "line", None)
        message = getattr(suggestion, "message", None) or ""
        suggested_code = getattr(suggestion, "suggested_code", None)

        # Skip invalid entries
        if not file_path or not line or line < 1:
            continue

        # Build the comment body
        if suggested_code:
            # Use GitHub's suggestion block for one-click apply
            body = f"{message}\n\n```suggestion\n{suggested_code}\n```"
        else:
            body = message

        comments.append({
            "path": file_path,
            "line": int(line),
            "side": "RIGHT",
            "body": body,
        })

        if len(comments) >= MAX_INLINE_COMMENTS:
            break

    return comments


def format_review_summary(review_text: str, quality_gate_text: str,
                         issue_count: int, pr_info: dict, 
                         decision: ReviewDecision) -> str:
    """Format the final review summary with decision reasoning"""

    summary = f"""# 🤖 AI Code Review

{review_text}

---

## 🎯 Review Decision

**Action:** {decision.event_type}  
**Confidence:** {decision.confidence:.0%}  
**Reasoning:** {decision.reasoning}

---

## 📊 Static Analysis Summary

{quality_gate_text}

**SonarQube Issues:** {issue_count}
{f"**Critical Issues Found:** {'Yes' if decision.critical_issues_found else 'No'}" if decision.critical_issues_found else ""}

---

## 📈 PR Statistics
- **Files Changed:** {pr_info.get('changed_files', 0)}
- **Lines Added:** +{pr_info.get('additions', 0)}
- **Lines Removed:** -{pr_info.get('deletions', 0)}

---

<sub>🤖 Automated review powered by Claude Sonnet 4.5 via Azure Foundry + LangChain | 
[Configure](.github/ai-review-config.yaml) | 
[Documentation](docs/SETUP.md)</sub>
"""

    return summary

def determine_review_event(review_text, issues, pr_info):
    review_text_lower = review_text.lower()

    if "critical" in review_text_lower or "vulnerability" in review_text_lower:
        return "REQUEST_CHANGES"

    if "looks good" in review_text_lower or "no issues" in review_text_lower:
        return "APPROVE"

    return "COMMENT"



if __name__ == "__main__":
    sys.exit(main())
