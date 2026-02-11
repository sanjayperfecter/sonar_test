#!/usr/bin/env python3
"""
AI Code Review Agent - Main Script
Orchestrates the complete review workflow
"""

import os
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from github_api import GitHubClient
from sonar_api import SonarClient
from llm_client import LLMClient


def print_banner():
    """Print startup banner"""
    print("=" * 80)
    print("🤖 AI Code Review Agent")
    print("=" * 80)


def main():
    """Main review workflow"""
    print_banner()
    

    try:
        return 0
        # 1. Initialize clients
        print("\n📦 Initializing clients...")
        github = GitHubClient()
        sonar = SonarClient()
        llm = LLMClient()

        # 2. Get PR information
        print("\n📋 Fetching PR information...")
        pr_info = github.get_pr_info()
        print(f"  PR #{pr_info['number']}: {pr_info['title']}")
        print(f"  Author: {pr_info['author']}")
        print(f"  Changes: {pr_info['changed_files']} files, "
              f"+{pr_info['additions']} -{pr_info['deletions']} lines")

        # 3. Get PR diff
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

        # 4. Get SonarQube analysis
        print("\n🔍 Fetching SonarQube analysis...")
        pr_number = pr_info['number']
        sonar_issues = sonar.get_issues_for_pr(pr_number)
        quality_gate = sonar.get_quality_gate_status(pr_number)

        # Format SonarQube context
        sonar_context = sonar.format_issues_for_context(sonar_issues)
        quality_gate_text = sonar.format_quality_gate(quality_gate)

        print(f"  {quality_gate_text}")
        print(f"  Found {len(sonar_issues)} issues")

        # 5. Check if should block on critical issues
        if sonar.has_critical_issues(sonar_issues):
            print("\n⚠️  Critical SonarQube issues detected")
            # AI review will still run but will likely REQUEST_CHANGES

        # 6. Perform AI review
        print("\n🤖 Running AI code review...")
        github.set_status("pending", "AI review in progress...", "ai-code-review")

        try:
            review_result = llm.review_code(
                diff=diff,
                sonar_context=sonar_context,
                pr_info=pr_info,
                file_context=""  # Can be extended for full file context
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
            # github.set_status("error", "AI review failed", "ai-code-review")
            return 1

        # 7. Determine review event type
        print("\n🎯 Determining review action...")
        event = determine_review_event(review_result, sonar_issues, quality_gate)
        print(f"  Review event: {event}")

        # 8. Post review summary
        print("\n📝 Posting review...")
        summary = format_review_summary(
            review_result, 
            quality_gate_text, 
            len(sonar_issues),
            pr_info
        )

        github.post_review_summary(summary, event)

        # 9. Set final status
        if event == "APPROVE":
            github.set_status("success", "✅ AI review: Approved", "ai-code-review")
        elif event == "REQUEST_CHANGES":
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
            # github.set_status("error", "AI review encountered an error", "ai-code-review")
        except:
            pass

        return 1


def determine_review_event(review_text: str, sonar_issues: list, 
                           quality_gate: dict) -> str:
    """Determine appropriate review event based on findings

    Returns:
        One of: APPROVE, REQUEST_CHANGES, COMMENT
    """
    review_lower = review_text.lower()

    # Check for critical issues in review
    critical_keywords = [
        'critical', 'security vulnerability', 'must fix', 'blocker',
        'sql injection', 'xss', 'authentication', 'authorization',
        'data exposure', 'memory leak'
    ]

    has_critical = any(keyword in review_lower for keyword in critical_keywords)

    # Check SonarQube quality gate
    quality_gate_failed = quality_gate.get('status') == 'ERROR'

    # Check for blocker/critical SonarQube issues
    has_critical_sonar = any(
        issue.get('severity') in ['BLOCKER', 'CRITICAL']
        for issue in sonar_issues
    )

    # Decision logic
    if has_critical or quality_gate_failed or has_critical_sonar:
        return "REQUEST_CHANGES"

    # Check if review is very positive
    positive_keywords = [
        'looks good', 'well done', 'excellent', 'no issues',
        'great work', 'approved'
    ]

    is_positive = any(keyword in review_lower for keyword in positive_keywords)
    has_no_suggestions = '## 🚨 critical issues' not in review_lower and                         '## ⚠️ important suggestions' not in review_lower

    if is_positive and has_no_suggestions and not sonar_issues:
        return "APPROVE"

    # Default to comment for everything else
    return "COMMENT"


def format_review_summary(review_text: str, quality_gate_text: str,
                         issue_count: int, pr_info: dict) -> str:
    """Format the final review summary"""

    summary = f"""# 🤖 AI Code Review

{review_text}

---

## 📊 Static Analysis Summary

{quality_gate_text}

**SonarQube Issues:** {issue_count}

---

## 📈 PR Statistics
- **Files Changed:** {pr_info.get('changed_files', 0)}
- **Lines Added:** +{pr_info.get('additions', 0)}
- **Lines Removed:** -{pr_info.get('deletions', 0)}

---

<sub>🤖 Automated review powered by Claude Sonnet 4.5 via Azure Foundry | 
[Configure](.github/ai-review-config.yaml) | 
[Documentation](docs/SETUP.md)</sub>
"""

    return summary


if __name__ == "__main__":
    sys.exit(main())
