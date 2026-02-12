"""
GitHub API Client for Code Review Agent
Handles all interactions with GitHub API
"""

import os
import yaml
from typing import List, Dict, Optional
from github import Github, GithubException
from pathlib import Path


class GitHubClient:
    """Client for interacting with GitHub API"""

    def __init__(self):
        self.token = os.getenv('GITHUB_TOKEN')
        if not self.token:
            raise ValueError("GITHUB_TOKEN environment variable not set")

        self.repo_name = os.getenv('REPO_NAME')
        if not self.repo_name:
            raise ValueError("REPO_NAME environment variable not set")

        pr_number = os.getenv('PR_NUMBER')
        if not pr_number:
            raise ValueError("PR_NUMBER environment variable not set")
        self.pr_number = int(pr_number)

        self.client = Github(self.token)
        self.repo = self.client.get_repo(self.repo_name)
        self.pr = self.repo.get_pull(self.pr_number)
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load configuration from yaml file"""
        config_path = Path(".github/ai-review-config.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        return self._default_config()

    def _default_config(self) -> Dict:
        """Default configuration if no config file exists"""
        return {
            'review': {
                'exclude_patterns': ['*.lock', '*.json', '*.md'],
                'include_extensions': ['.py', '.js', '.ts', '.java', '.go']
            }
        }

    def get_pr_info(self) -> Dict:
        """Get PR metadata"""
        return {
            'number': self.pr.number,
            'title': self.pr.title,
            'description': self.pr.body or '',
            'author': self.pr.user.login,
            'base_branch': self.pr.base.ref,
            'head_branch': self.pr.head.ref,
            'changed_files': self.pr.changed_files,
            'additions': self.pr.additions,
            'deletions': self.pr.deletions,
        }

    def get_pr_diff(self) -> str:
        """Fetch PR diff using GitHub API"""
        files = self.pr.get_files()
        diff_text = ""
        file_count = 0

        for file in files:
            # Skip files based on configuration
            if self.should_skip_file(file.filename):
                continue

            file_count += 1
            diff_text += f"\n{'='*80}\n"
            diff_text += f"File: {file.filename}\n"
            diff_text += f"Status: {file.status}\n"
            diff_text += f"Changes: +{file.additions} -{file.deletions}\n"
            diff_text += f"{'='*80}\n"

            if file.patch:
                diff_text += file.patch + "\n"

        if file_count == 0:
            return ""

        return diff_text

    def get_changed_files(self) -> List[Dict]:
        """Get list of changed files with metadata"""
        files = self.pr.get_files()
        changed_files = []

        for file in files:
            if self.should_skip_file(file.filename):
                continue

            changed_files.append({
                'filename': file.filename,
                'status': file.status,
                'additions': file.additions,
                'deletions': file.deletions,
                'changes': file.changes,
                'patch': file.patch
            })

        return changed_files

    def should_skip_file(self, filename: str) -> bool:
        """Determine if file should be skipped based on configuration"""
        exclude_patterns = self.config.get('review', {}).get('exclude_patterns', [])
        include_extensions = self.config.get('review', {}).get('include_extensions', [])

        # Check exclude patterns
        for pattern in exclude_patterns:
            if pattern.startswith('*'):
                # Extension pattern
                if filename.endswith(pattern[1:]):
                    return True
            elif pattern.endswith('**'):
                # Directory pattern
                if filename.startswith(pattern[:-2]):
                    return True
            elif pattern in filename:
                return True

        # Check include extensions
        if include_extensions:
            file_ext = Path(filename).suffix
            if file_ext not in include_extensions:
                return True

        return False

    def get_file_content(self, filename: str, ref: Optional[str] = None) -> str:
        """Get full file content for context"""
        try:
            content = self.repo.get_contents(filename, ref=ref or self.pr.head.sha)
            if isinstance(content, list):
                return "Directory listing not supported"
            return content.decoded_content.decode('utf-8')
        except GithubException as e:
            return f"Error fetching file: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def post_review_comment(self, body: str, path: str, line: int):
        """Post inline review comment on specific line"""
        try:
            commit = self.pr.get_commits().reversed[0]
            self.pr.create_review_comment(
                body=body,
                commit=commit,
                path=path,
                line=line
            )
            print(f"✅ Posted comment on {path}:{line}")
        except GithubException as e:
            print(f"❌ Error posting comment on {path}:{line}: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

    def post_review_summary(self, body: str, event: str = "COMMENT"):
        """Post overall PR review summary

        Args:
            body: Review comment body
            event: One of APPROVE, REQUEST_CHANGES, COMMENT
        """
        try:
            # Validate event type
            valid_events = ["APPROVE", "REQUEST_CHANGES", "COMMENT"]
            if event not in valid_events:
                event = "COMMENT"

            self.pr.create_review(body=body, event=event)
            print(f"✅ Posted review summary with event: {event}")
        except GithubException as e:
            print(f"❌ Error posting review: {e}")
            # Fallback to regular comment
            try:
                self.pr.create_issue_comment(body)
                print("✅ Posted as regular comment instead")
            except:
                pass

    def post_review_with_comments(self, body: str, event: str = "COMMENT",
                                  comments: Optional[List[Dict]] = None):
        """Post PR review with summary body AND inline comments on specific lines.

        This submits a single review that includes the summary as the review
        body (same as post_review_summary) plus inline comments attached to
        specific lines in the diff.

        Args:
            body: Review comment body (the summary)
            event: One of APPROVE, REQUEST_CHANGES, COMMENT
            comments: List of inline comment dicts, each with:
                - path (str): relative file path
                - line (int): line number in the new file
                - side (str): "RIGHT" for additions/context, "LEFT" for deletions
                - body (str): comment text (may include ```suggestion``` blocks)
        """
        # Validate event type
        valid_events = ["APPROVE", "REQUEST_CHANGES", "COMMENT"]
        if event not in valid_events:
            event = "COMMENT"

        # If no inline comments, fall back to summary-only review
        if not comments:
            self.post_review_summary(body, event)
            return

        try:
            # PyGithub's create_review accepts comments as a list of
            # ReviewComment-like dicts with path, body, line, side etc.
            review_comments = []
            for c in comments:
                comment_dict = {
                    "path": c["path"],
                    "body": c["body"],
                    "line": c["line"],
                    "side": c.get("side", "RIGHT"),
                }
                # Include start_line for multi-line comments if provided
                if "start_line" in c:
                    comment_dict["start_line"] = c["start_line"]
                    comment_dict["start_side"] = c.get("start_side", "RIGHT")
                review_comments.append(comment_dict)

            self.pr.create_review(
                body=body,
                event=event,
                comments=review_comments,
            )
            print(f"✅ Posted review with {len(review_comments)} inline "
                  f"comment(s) and event: {event}")
        except GithubException as e:
            print(f"❌ Error posting review with inline comments: {e}")
            # Fallback: post summary only, then try individual comments
            print("⚠️  Falling back to summary-only review + individual comments...")
            self.post_review_summary(body, event)
            for c in (comments or []):
                try:
                    self.post_review_comment(
                        body=c["body"],
                        path=c["path"],
                        line=c["line"],
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"❌ Unexpected error posting review with comments: {e}")
            self.post_review_summary(body, event)

    def create_suggested_change(self, path: str, line: int, 
                                old_code: str, new_code: str, 
                                explanation: str):
        """Post suggested change that can be committed with one click"""
        suggestion_body = f"""{explanation}

```suggestion
{new_code}
```
"""
        self.post_review_comment(suggestion_body, path, line)

    def post_comment(self, body: str):
        """Post a regular comment on the PR"""
        try:
            self.pr.create_issue_comment(body)
            print("✅ Posted comment")
        except Exception as e:
            print(f"❌ Error posting comment: {e}")

    def set_status(self, state: str, description: str, context: str = "ai-code-review"):
        """Set commit status

        Args:
            state: One of error, failure, pending, success
            description: Short description
            context: Status context identifier
        """
        try:
            commit = self.pr.head.sha
            self.repo.get_commit(commit).create_status(
                state=state,
                description=description,
                context=context
            )
            print(f"✅ Set status: {state} - {description}")
        except Exception as e:
            print(f"❌ Error setting status: {e}")
