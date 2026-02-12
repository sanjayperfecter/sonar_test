"""
Unit Tests for AI Code Review Agent
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


class TestGitHubClient:
    """Tests for GitHub API client"""

    @patch('github_api.Github')
    @patch.dict('os.environ', {
        'GITHUB_TOKEN': 'test_token',
        'REPO_NAME': 'owner/repo',
        'PR_NUMBER': '123'
    })
    def test_initialization(self, mock_github):
        """Test client initialization"""
        from github_api import GitHubClient

        client = GitHubClient()
        assert client.token == 'test_token'
        assert client.repo_name == 'owner/repo'
        assert client.pr_number == 123

    def test_should_skip_file(self):
        """Test file filtering logic"""
        # This would need proper mocking of GitHub API
        # Placeholder for actual implementation
        pass


class TestSonarClient:
    """Tests for SonarQube API client"""

    @patch.dict('os.environ', {
        'SONAR_TOKEN': 'test_token',
        'SONAR_PROJECT_KEY': 'test_project',
        'SONAR_ORGANIZATION': 'test_org'
    })
    def test_initialization(self):
        """Test client initialization"""
        from sonar_api import SonarClient

        client = SonarClient()
        assert client.token == 'test_token'
        assert client.project_key == 'test_project'
        assert client.enabled is True

    def test_format_issues(self):
        """Test issue formatting"""
        from sonar_api import SonarClient

        client = SonarClient()
        issues = [
            {
                'severity': 'CRITICAL',
                'message': 'SQL injection vulnerability',
                'component': 'src/database.py',
                'line': 42,
                'type': 'VULNERABILITY',
                'rule': 'python:S2077'
            }
        ]

        formatted = client.format_issues_for_context(issues)
        assert 'CRITICAL' in formatted
        assert 'SQL injection' in formatted


class TestLLMClient:
    """Tests for LLM client"""

    @patch.dict('os.environ', {
        'ANTHROPIC_API_KEY': 'test_key'
    })
    def test_initialization_anthropic(self):
        """Test initialization with Anthropic"""
        # Would need to mock anthropic import
        pass

    @patch.dict('os.environ', {
        'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com',
        'AZURE_OPENAI_KEY': 'test_key'
    })
    def test_initialization_azure(self):
        """Test initialization with Azure OpenAI"""
        # Would need to mock openai import
        pass


class TestReviewWorkflow:
    """Integration tests for review workflow"""

    def test_determine_review_event_critical(self):
        """Test review event determination with critical issues"""
        from review import determine_review_event

        review_text = "Critical security vulnerability found: SQL injection"
        event = determine_review_event(review_text, [], {})
        assert event == "REQUEST_CHANGES"

    def test_determine_review_event_approve(self):
        """Test review event determination for approval"""
        from review import determine_review_event

        review_text = "Looks good! No issues found. Great work."
        event = determine_review_event(review_text, [], {})
        assert event in ["APPROVE", "COMMENT"]

    def test_format_review_summary(self):
        """Test review summary formatting"""
        from review import format_review_summary

        pr_info = {
            'changed_files': 3,
            'additions': 50,
            'deletions': 20
        }

        summary = format_review_summary(
            "Test review",
            "✅ Quality Gate: PASSED",
            0,
            pr_info,
            "APPROVE"
        )


        assert "Test review" in summary
        assert "Files Changed: 3" in summary
        assert "+50" in summary


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
