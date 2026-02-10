"""
SonarQube/SonarCloud API Client
Fetches static analysis results from SonarQube
"""

import os
import requests
from typing import Dict, List, Optional


class SonarClient:
    """Client for interacting with SonarQube/SonarCloud API"""

    def __init__(self):
        self.token = os.getenv('SONAR_TOKEN')
        self.project_key = os.getenv('SONAR_PROJECT_KEY')
        self.organization = os.getenv('SONAR_ORGANIZATION')

        # Default to SonarCloud, can be overridden for self-hosted
        self.base_url = os.getenv('SONAR_URL', 'https://sonarcloud.io/api')

        self.headers = {
            'Authorization': f'Bearer {self.token}' if self.token else None
        }

        self.enabled = bool(self.token and self.project_key)

    def get_issues_for_pr(self, pr_number: int) -> List[Dict]:
        """Fetch SonarQube issues for specific PR"""
        if not self.enabled:
            print("⚠️  SonarQube not configured, skipping")
            return []

        try:
            url = f"{self.base_url}/issues/search"
            params = {
                'componentKeys': self.project_key,
                'pullRequest': str(pr_number),
                'resolved': 'false',
                'ps': 500  # Page size
            }

            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                issues = data.get('issues', [])
                print(f"✅ Found {len(issues)} SonarQube issues")
                return issues
            else:
                print(f"⚠️  SonarQube API returned status {response.status_code}")
                return []

        except requests.exceptions.Timeout:
            print("⚠️  SonarQube API timeout")
            return []
        except Exception as e:
            print(f"⚠️  Error fetching SonarQube issues: {e}")
            return []

    def get_quality_gate_status(self, pr_number: int) -> Dict:
        """Get quality gate status for PR"""
        if not self.enabled:
            return {'status': 'UNKNOWN'}

        try:
            url = f"{self.base_url}/qualitygates/project_status"
            params = {
                'projectKey': self.project_key,
                'pullRequest': str(pr_number)
            }

            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                status = data.get('projectStatus', {})
                print(f"✅ Quality Gate Status: {status.get('status', 'UNKNOWN')}")
                return status
            else:
                print(f"⚠️  Quality Gate API returned status {response.status_code}")
                return {'status': 'UNKNOWN'}

        except Exception as e:
            print(f"⚠️  Error fetching quality gate: {e}")
            return {'status': 'ERROR'}

    def get_metrics(self, pr_number: int) -> Dict:
        """Get code metrics for PR"""
        if not self.enabled:
            return {}

        try:
            url = f"{self.base_url}/measures/component"
            params = {
                'component': self.project_key,
                'pullRequest': str(pr_number),
                'metricKeys': 'bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density'
            }

            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                measures = data.get('component', {}).get('measures', [])
                metrics = {m['metric']: m['value'] for m in measures}
                print(f"✅ Fetched {len(metrics)} metrics")
                return metrics
            else:
                return {}

        except Exception as e:
            print(f"⚠️  Error fetching metrics: {e}")
            return {}

    def format_issues_for_context(self, issues: List[Dict]) -> str:
        """Format SonarQube findings for LLM context"""
        if not issues:
            return "✅ No SonarQube issues found - code passes static analysis."

        # Group by severity
        by_severity = {
            'BLOCKER': [],
            'CRITICAL': [],
            'MAJOR': [],
            'MINOR': [],
            'INFO': []
        }

        for issue in issues:
            severity = issue.get('severity', 'INFO')
            by_severity[severity].append(issue)

        formatted = "## SonarQube Static Analysis Results\n\n"

        total = len(issues)
        formatted += f"**Total Issues:** {total}\n\n"

        for severity in ['BLOCKER', 'CRITICAL', 'MAJOR', 'MINOR', 'INFO']:
            issues_list = by_severity[severity]
            if not issues_list:
                continue

            emoji = self._severity_emoji(severity)
            formatted += f"### {emoji} {severity} ({len(issues_list)})\n\n"

            for issue in issues_list[:10]:  # Limit to first 10 per severity
                formatted += f"- **{issue.get('message', 'No message')}**\n"
                formatted += f"  - File: `{issue.get('component', 'Unknown').split(':')[-1]}`\n"
                formatted += f"  - Line: {issue.get('line', 'N/A')}\n"
                formatted += f"  - Type: {issue.get('type', 'Unknown')}\n"
                formatted += f"  - Rule: {issue.get('rule', 'Unknown')}\n\n"

            if len(issues_list) > 10:
                formatted += f"  ... and {len(issues_list) - 10} more {severity} issues\n\n"

        return formatted

    def _severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level"""
        emoji_map = {
            'BLOCKER': '🚫',
            'CRITICAL': '🔴',
            'MAJOR': '🟠',
            'MINOR': '🟡',
            'INFO': 'ℹ️'
        }
        return emoji_map.get(severity, '•')

    def format_quality_gate(self, quality_gate: Dict) -> str:
        """Format quality gate status"""
        status = quality_gate.get('status', 'UNKNOWN')

        if status == 'OK':
            return "✅ **Quality Gate: PASSED**"
        elif status == 'ERROR':
            return "❌ **Quality Gate: FAILED**"
        elif status == 'WARN':
            return "⚠️  **Quality Gate: WARNING**"
        else:
            return "❓ **Quality Gate: UNKNOWN**"

    def has_critical_issues(self, issues: List[Dict]) -> bool:
        """Check if there are blocker or critical issues"""
        return any(
            issue.get('severity') in ['BLOCKER', 'CRITICAL']
            for issue in issues
        )
