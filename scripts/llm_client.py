"""
LLM Client for AI Code Review
Supports Claude (Anthropic) and GPT-4 (Azure OpenAI)
"""

import os
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMClient:
    """Client for interacting with LLM providers"""

    def __init__(self):
        # Anthropic Claude
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')

        # Azure OpenAI
        self.azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.azure_key = os.getenv('AZURE_OPENAI_KEY')
        self.azure_deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4.1-min')

        # Initialize clients
        self.anthropic = None
        self.azure = None

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
                    api_version="2025-01-01-preview"
                )
                print("✅ Azure OpenAI initialized")
            except ImportError:
                print("⚠️  openai package not installed")

        if not self.anthropic and not self.azure:
            raise ValueError("No LLM provider configured. Set ANTHROPIC_API_KEY or AZURE_OPENAI_* variables")

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

        # Fallback to Azure OpenAI
        if self.azure:
            try:
                return self.review_with_azure_openai(system_prompt, user_content)
            except Exception as e:
                print(f"❌ Azure OpenAI failed: {e}")
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

Your role is to analyze code changes critically but constructively.

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

## Response Format

Structure your review as:

### 🔍 Summary
[1-2 sentence overall assessment]

### 🚨 Critical Issues
[Issues that MUST be fixed before merge - security, bugs]
- Use clear, actionable language
- Reference specific line numbers when possible
- Provide concrete examples

### ⚠️ Important Suggestions
[Issues that SHOULD be addressed - quality, performance]
- Explain the impact
- Suggest specific improvements
- Consider trade-offs

### 💡 Minor Improvements
[Nice-to-have improvements - style, readability]
- Be concise
- Focus on high-impact items

### ✅ Positive Feedback
[What was done well - reinforce good practices]

### 📊 SonarQube Integration
[Analysis of static analysis findings, additional semantic context]

## Communication Style
- Be specific and actionable
- Reference line numbers and file names
- Provide code examples for suggestions
- Balance criticism with constructive feedback
- Acknowledge good practices
- Prioritize issues clearly (Critical > Important > Minor)
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
