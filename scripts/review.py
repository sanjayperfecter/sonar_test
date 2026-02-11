# #!/usr/bin/env python3
# """
# AI Code Review Agent - Main Script
# Orchestrates the complete review workflow
# """

# import os
# import sys
# from pathlib import Path

# # Add scripts directory to path
# sys.path.insert(0, str(Path(__file__).parent))

# from github_api import GitHubClient
# from sonar_api import SonarClient
# from llm_client import LLMClient


# def print_banner():
#     """Print startup banner"""
#     print("=" * 80)
#     print("🤖 AI Code Review Agent")
#     print("=" * 80)


# def main():
#     """Main review workflow"""
#     print_banner()
    

#     try:
#         # return 0
#         # 1. Initialize clients
#         print("\n📦 Initializing clients...")
#         github = GitHubClient()
#         sonar = SonarClient()
#         llm = LLMClient()

#         # 2. Get PR information
#         print("\n📋 Fetching PR information...")
#         pr_info = github.get_pr_info()
#         print(f"  PR #{pr_info['number']}: {pr_info['title']}")
#         print(f"  Author: {pr_info['author']}")
#         print(f"  Changes: {pr_info['changed_files']} files, "
#               f"+{pr_info['additions']} -{pr_info['deletions']} lines")

#         # 3. Get PR diff
#         print("\n📥 Fetching code changes...")
#         diff = github.get_pr_diff()

#         if not diff.strip():
#             print("⚠️  No reviewable code changes detected")
#             github.post_comment(
#                 "ℹ️ **AI Code Review Skipped**\n\n"
#                 "No reviewable code changes found in this PR. "
#                 "This might be due to:\n"
#                 "- Only documentation/config file changes\n"
#                 "- Files excluded by configuration\n"
#                 "- No changes in supported file types"
#             )
#             github.set_status("success", "No code changes to review", "ai-code-review")
#             return 0

#         print(f"  ✅ Found code changes to review")

#         # 4. Get SonarQube analysis
#         print("\n🔍 Fetching SonarQube analysis...")
#         pr_number = pr_info['number']
#         sonar_issues = sonar.get_issues_for_pr(pr_number)
#         quality_gate = sonar.get_quality_gate_status(pr_number)

#         # Format SonarQube context
#         sonar_context = sonar.format_issues_for_context(sonar_issues)
#         quality_gate_text = sonar.format_quality_gate(quality_gate)

#         print(f"  {quality_gate_text}")
#         print(f"  Found {len(sonar_issues)} issues")

#         # 5. Check if should block on critical issues
#         if sonar.has_critical_issues(sonar_issues):
#             print("\n⚠️  Critical SonarQube issues detected")
#             # AI review will still run but will likely REQUEST_CHANGES

#         # 6. Perform AI review
#         print("\n🤖 Running AI code review...")
#         github.set_status("pending", "AI review in progress...", "ai-code-review")

#         try:
#             review_result = llm.review_code(
#                 diff=diff,
#                 sonar_context=sonar_context,
#                 pr_info=pr_info,
#                 file_context=""  # Can be extended for full file context
#             )
#             print("  ✅ AI review completed")

#         except Exception as e:
#             print(f"\n❌ AI review failed: {e}")
#             github.post_comment(
#                 f"❌ **AI Code Review Failed**\n\n"
#                 f"An error occurred during AI analysis:\n"
#                 f"```\n{str(e)}\n```\n\n"
#                 f"Please check the workflow logs for details."
#             )
#             # github.set_status("error", "AI review failed", "ai-code-review")
#             return 1

#         # 7. Determine review event type
#         print("\n🎯 Determining review action...")
#         event = determine_review_event(review_result, sonar_issues, quality_gate)
#         print(f"  Review event: {event}")

#         # 8. Post review summary
#         print("\n📝 Posting review...")
#         summary = format_review_summary(
#             review_result, 
#             quality_gate_text, 
#             len(sonar_issues),
#             pr_info
#         )

#         github.post_review_summary(summary, event)

#         # 9. Set final status
#         if event == "APPROVE":
#             github.set_status("success", "✅ AI review: Approved", "ai-code-review")
#         elif event == "REQUEST_CHANGES":
#             github.set_status("failure", "❌ AI review: Changes requested", "ai-code-review")
#         else:
#             github.set_status("success", "✅ AI review: Comments posted", "ai-code-review")

#         print("\n✅ Review completed successfully!")
#         print("=" * 80)

#         return 0

#     except Exception as e:
#         print(f"\n❌ Fatal error: {e}")
#         import traceback
#         traceback.print_exc()

#         try:
#             github = GitHubClient()
#             # github.set_status("error", "AI review encountered an error", "ai-code-review")
#         except:
#             pass

#         return 1


# def determine_review_event(review_text: str, sonar_issues: list, 
#                            quality_gate: dict) -> str:
#     """Determine appropriate review event based on findings

#     Returns:
#         One of: APPROVE, REQUEST_CHANGES, COMMENT
#     """
#     review_lower = review_text.lower()

#     # Check for critical issues in review
#     critical_keywords = [
#         'critical', 'security vulnerability', 'must fix', 'blocker',
#         'sql injection', 'xss', 'authentication', 'authorization',
#         'data exposure', 'memory leak'
#     ]

#     has_critical = any(keyword in review_lower for keyword in critical_keywords)

#     # Check SonarQube quality gate
#     quality_gate_failed = quality_gate.get('status') == 'ERROR'

#     # Check for blocker/critical SonarQube issues
#     has_critical_sonar = any(
#         issue.get('severity') in ['BLOCKER', 'CRITICAL']
#         for issue in sonar_issues
#     )

#     # Decision logic
#     if has_critical or quality_gate_failed or has_critical_sonar:
#         return "REQUEST_CHANGES"

#     # Check if review is very positive
#     positive_keywords = [
#         'looks good', 'well done', 'excellent', 'no issues',
#         'great work', 'approved'
#     ]

#     is_positive = any(keyword in review_lower for keyword in positive_keywords)
#     has_no_suggestions = '## 🚨 critical issues' not in review_lower and                         '## ⚠️ important suggestions' not in review_lower

#     if is_positive and has_no_suggestions and not sonar_issues:
#         return "APPROVE"

#     # Default to comment for everything else
#     return "COMMENT"


# def format_review_summary(review_text: str, quality_gate_text: str,
#                          issue_count: int, pr_info: dict) -> str:
#     """Format the final review summary"""

#     summary = f"""# 🤖 AI Code Review

# {review_text}

# ---

# ## 📊 Static Analysis Summary

# {quality_gate_text}

# **SonarQube Issues:** {issue_count}

# ---

# ## 📈 PR Statistics
# - **Files Changed:** {pr_info.get('changed_files', 0)}
# - **Lines Added:** +{pr_info.get('additions', 0)}
# - **Lines Removed:** -{pr_info.get('deletions', 0)}

# ---

# <sub>🤖 Automated review powered by Claude Sonnet 4.5 via Azure Foundry | 
# [Configure](.github/ai-review-config.yaml) | 
# [Documentation](docs/SETUP.md)</sub>
# """

#     return summary


# if __name__ == "__main__":
#     sys.exit(main())




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
from langchain_openai import AzureChatOpenAI
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
    
    def __init__(self):
        """Initialize the LangChain analyzer"""
        # Initialize Azure OpenAI via LangChain
        self.llm = AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            temperature=0.1,  # Low temperature for consistent decisions
            model_kwargs={"top_p": 0.95}
        )
        
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
        
        # Initialize LangChain analyzer
        print("  🔗 Initializing LangChain analyzer...")
        review_analyzer = ReviewEventAnalyzer()

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

        # Perform AI review
        print("\n🤖 Running AI code review...")
        github.set_status("pending", "AI review in progress...", "ai-code-review")

        try:
            review_result = llm.review_code(
                diff=diff,
                sonar_context=sonar_context,
                pr_info=pr_info,
                file_context=""
            )
            print("  ✅ AI review completed")

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

        # Post review summary
        print("\n📝 Posting review...")
        summary = format_review_summary(
            review_result, 
            quality_gate_text, 
            len(sonar_issues),
            pr_info,
            decision
        )

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


if __name__ == "__main__":
    sys.exit(main())
