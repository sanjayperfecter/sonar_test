# AI Code Review Agent

An intelligent code review automation system that integrates SonarQube static analysis with AI-powered code review using Claude Sonnet 4.5 or GPT-4.

## 🚀 Features

- **Automated Code Analysis**: Triggers on every pull request
- **SonarQube Integration**: Static analysis with quality gate enforcement
- **AI-Powered Review**: Claude Sonnet 4.5 for semantic code analysis
- **Suggested Changes**: One-click code fixes directly in PR comments
- **Security Focus**: Identifies vulnerabilities, SQL injection, XSS, auth issues
- **Cost Efficient**: ~$10-50/month for LLM API costs
- **Zero Infrastructure**: Runs entirely on GitHub Actions

## 📋 Prerequisites

- GitHub repository with Actions enabled
- SonarCloud account (free tier available)
- Azure OpenAI or Anthropic API access
- Python 3.11+ (handled by GitHub Actions)

## 🛠️ Quick Setup (15 minutes)

### Step 1: Fork/Clone Repository

```bash
git clone <your-repo-url>
cd ai-code-review-agent
```

### Step 2: Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `SONAR_TOKEN` | SonarCloud authentication token | ✅ |
| `SONAR_PROJECT_KEY` | Your SonarCloud project key | ✅ |
| `SONAR_ORGANIZATION` | Your SonarCloud organization | ✅ |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | ⚠️ |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key | ⚠️ |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | ⚠️ |

⚠️ = At least one LLM provider required (Azure OpenAI OR Anthropic)

### Step 3: Configure SonarCloud

1. Go to [sonarcloud.io](https://sonarcloud.io)
2. Import your GitHub repository
3. Copy your project key and organization
4. Add secrets to GitHub (from Step 2)

### Step 4: Enable Workflows

1. Go to **Actions** tab in your repository
2. Enable workflows if prompted
3. Workflows will trigger automatically on next PR

### Step 5: Configure Branch Protection

Go to **Settings → Rules → Rulesets → New ruleset**:

- ✅ Require pull request before merging (≥1 approval)
- ✅ Required status checks: `SonarCloud Scan`, `AI Code Review`
- ✅ Dismiss stale approvals when new commits pushed

## 🎯 How It Works

```
Developer pushes code to branch
          ↓
GitHub webhook triggers workflow
          ↓
SonarQube analyzes code (static analysis)
          ↓
AI Agent fetches SonarQube results
          ↓
AI Agent analyzes code with Claude/GPT-4
          ↓
AI Agent posts review with suggestions
          ↓
Developer applies suggestions with one click
```

## 📁 Project Structure

```
ai-code-review-agent/
├── .github/
│   ├── workflows/
│   │   ├── sonarqube.yml          # SonarCloud analysis
│   │   └── ai-review.yml          # AI code review
│   └── ai-review-config.yaml      # Review configuration
├── scripts/
│   ├── review.py                  # Main review orchestrator
│   ├── github_api.py              # GitHub API client
│   ├── sonar_api.py               # SonarQube API client
│   ├── llm_client.py              # LLM integration
│   └── requirements.txt           # Python dependencies
├── config/
│   └── review-prompts.yaml        # Customizable prompts
├── tests/
│   └── test_review.py             # Unit tests
└── docs/
    ├── SETUP.md                   # Detailed setup guide
    └── ARCHITECTURE.md            # System architecture
```

## 🔧 Configuration

Edit `.github/ai-review-config.yaml` to customize:

```yaml
review:
  enabled: true
  exclude_patterns:
    - "*.lock"
    - "*.json"
    - "test/**"

llm:
  primary_model: "claude-sonnet-4.5"
  fallback_model: "gpt-4"
  max_tokens: 4096

sonarqube:
  enforce_quality_gate: true
  block_on_critical: true
```

## 💡 Usage

### Automatic Reviews

Reviews trigger automatically on:
- New pull requests
- New commits to existing PRs
- PR reopened or marked ready for review

### Manual Commands

Comment on PR to trigger actions:
- `/review` - Re-run AI review
- `/review-full` - Full file analysis (not just diff)

### Applying Suggestions

When AI posts suggested changes:
1. Click **"Commit suggestion"** button
2. Change applies directly to your branch
3. No manual editing needed!

## 📊 Cost Estimates

Based on 20 PRs/day (~440/month):

| Component | Monthly Cost |
|-----------|--------------|
| GitHub Actions | Free (within limits) |
| SonarCloud | Free (up to 50K LOC) |
| Claude Sonnet 4.5 API | ~$10-15 |
| Azure OpenAI GPT-4 | ~$6-10 |
| **Total** | **~$15-25/month** |

## 🔒 Security

- Code never leaves GitHub/Azure infrastructure
- Secrets stored in GitHub encrypted secrets
- Branch protection enforced via rulesets
- AI cannot approve its own changes
- All changes require human review

## 🐛 Troubleshooting

### Workflow not triggering
- Check if Actions are enabled in repository settings
- Verify workflow files are in `.github/workflows/`
- Check branch protection rules aren't blocking

### SonarCloud failing
- Verify `SONAR_TOKEN` is valid
- Check project key and organization match
- Ensure repository is imported in SonarCloud

### AI review errors
- Check LLM API keys are valid and have credits
- Verify endpoint URLs are correct
- Check Actions logs for detailed error messages

### Rate limits
- GitHub: 5,000 requests/hour with `GITHUB_TOKEN`
- SonarCloud: Generous limits on free tier
- LLM APIs: Set up billing alerts

## 📚 Documentation

- [Detailed Setup Guide](docs/SETUP.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Contributing Guidelines](CONTRIBUTING.md)

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## 📄 License

MIT License - see [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- Based on architecture analysis from strategic implementation guide
- Powered by Anthropic Claude and OpenAI GPT-4
- SonarQube integration for static analysis
- GitHub Actions for CI/CD automation

## 📞 Support

- **Issues**: Open a GitHub issue
- **Discussions**: Use GitHub Discussions
- **Email**: support@your-company.com

---

Built with ❤️ for better code quality
