# Detailed Setup Guide

This guide walks you through setting up the AI Code Review Agent from scratch.

## Prerequisites

- GitHub repository with Actions enabled
- Admin access to repository settings
- SonarCloud account (free tier available)
- Either:
  - Azure OpenAI subscription with GPT-4 deployment, OR
  - Anthropic API key for Claude access

## Step-by-Step Setup

### 1. SonarCloud Configuration

#### 1.1 Create SonarCloud Account

1. Go to [sonarcloud.io](https://sonarcloud.io)
2. Click "Log in" and choose "GitHub"
3. Authorize SonarCloud to access your GitHub account

#### 1.2 Import Repository

1. Click "+" → "Analyze new project"
2. Select your GitHub organization
3. Choose the repository to analyze
4. Click "Set Up"

#### 1.3 Configure Analysis

1. Choose "GitHub Actions" as the analysis method
2. Copy your:
   - **SONAR_TOKEN** (keep this secure!)
   - **SONAR_PROJECT_KEY** (format: `org_repo`)
   - **SONAR_ORGANIZATION** (your organization key)

### 2. Azure OpenAI Setup (Option A)

#### 2.1 Create Azure OpenAI Resource

1. Go to [Azure Portal](https://portal.azure.com)
2. Search for "Azure OpenAI"
3. Click "Create" → Fill in details:
   - Resource group: Create new or use existing
   - Region: Choose available region
   - Name: `your-company-openai`
   - Pricing tier: Standard S0

#### 2.2 Deploy GPT-4 Model

1. In your Azure OpenAI resource, go to "Model deployments"
2. Click "Create new deployment"
3. Select:
   - Model: `gpt-4` or `gpt-4-turbo`
   - Deployment name: `gpt-4` (remember this!)
4. Click "Create"

#### 2.3 Get Credentials

1. Go to "Keys and Endpoint"
2. Copy:
   - **Endpoint** (e.g., `https://your-resource.openai.azure.com/`)
   - **Key 1** (keep secure!)
   - **Deployment name** from previous step

### 3. Anthropic API Setup (Option B)

#### 3.1 Get API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Go to "API Keys"
4. Click "Create Key"
5. Copy the **API Key** (keep secure!)

### 4. GitHub Repository Setup

#### 4.1 Add Workflow Files

1. Clone this repository or copy the files
2. Ensure these files are in your repo:
   ```
   .github/workflows/sonarqube.yml
   .github/workflows/ai-review.yml
   .github/ai-review-config.yaml
   scripts/review.py
   scripts/github_api.py
   scripts/sonar_api.py
   scripts/llm_client.py
   scripts/requirements.txt
   ```

#### 4.2 Configure GitHub Secrets

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click "New repository secret" for each:

**Required Secrets:**

| Secret Name | Value | Where to Get |
|-------------|-------|--------------|
| `SONAR_TOKEN` | Your SonarCloud token | SonarCloud account settings |
| `SONAR_PROJECT_KEY` | Your project key | SonarCloud project settings |
| `SONAR_ORGANIZATION` | Your organization key | SonarCloud organization |

**LLM Provider (Choose ONE):**

**For Azure OpenAI:**
| Secret Name | Value |
|-------------|-------|
| `AZURE_OPENAI_ENDPOINT` | Your Azure endpoint URL |
| `AZURE_OPENAI_KEY` | Your Azure API key |
| `AZURE_OPENAI_DEPLOYMENT` | Your deployment name (e.g., `gpt-4`) |

**For Anthropic Claude:**
| Secret Name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

#### 4.3 Enable GitHub Actions

1. Go to **Actions** tab
2. If prompted, click "I understand my workflows, go ahead and enable them"
3. Verify workflows appear in the list

#### 4.4 Configure Branch Protection

1. Go to **Settings** → **Rules** → **Rulesets**
2. Click "New ruleset" → "New branch ruleset"
3. Configure:
   - **Ruleset Name:** `Main Branch Protection`
   - **Enforcement status:** Active
   - **Target branches:** `main` (or your default branch)

4. Add rules:
   - ✅ **Require a pull request before merging**
     - Required approvals: 1
     - Dismiss stale pull request approvals when new commits are pushed
     - Require approval of the most recent reviewable push

   - ✅ **Require status checks to pass**
     - Add: `SonarCloud Scan`
     - Add: `AI Code Review`
     - Require branches to be up to date before merging

   - ✅ **Block force pushes**

5. Click "Create"

### 5. Test the Setup

#### 5.1 Create Test Branch

```bash
git checkout -b test-ai-review
```

#### 5.2 Make a Test Change

Create a simple file with an intentional issue:

```python
# test_file.py
def calculate_total(items):
    total = 0
    for item in items:
        total = total + item['price']  # No error handling
    return total

# SQL injection vulnerability example
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"  # Vulnerable!
    return query
```

#### 5.3 Commit and Push

```bash
git add test_file.py
git commit -m "Test: Add file for AI review testing"
git push origin test-ai-review
```

#### 5.4 Create Pull Request

1. Go to your repository on GitHub
2. Click "Compare & pull request"
3. Fill in title and description
4. Click "Create pull request"

#### 5.5 Verify Workflows

1. Go to **Actions** tab
2. You should see:
   - "SonarQube Analysis" workflow running
   - "AI Code Review" workflow waiting then running

3. Check the PR for:
   - ✅ SonarQube quality gate comment
   - ✅ AI review comment with findings
   - ✅ Status checks appearing

Expected AI review should identify:
- Missing error handling in `calculate_total`
- SQL injection vulnerability in `get_user`
- Suggestions for improvements

### 6. Customize Configuration

Edit `.github/ai-review-config.yaml` to customize:

```yaml
review:
  # Exclude additional file patterns
  exclude_patterns:
    - "*.lock"
    - "vendor/**"
    - "migrations/**"

  # Adjust sensitivity
  min_severity: "MAJOR"  # Only report MAJOR, CRITICAL, BLOCKER

llm:
  # Switch primary model if needed
  primary_model: "gpt-4"  # or "claude-sonnet-4.5"

  # Adjust creativity vs consistency
  temperature: 0.2  # Lower = more consistent

sonarqube:
  # Block merges on critical issues
  block_on_critical: true
```

Commit and push changes to update configuration.

## Troubleshooting

### Workflow Not Triggering

**Problem:** Workflows don't run on new PRs

**Solutions:**
1. Check if Actions are enabled: Settings → Actions → General
2. Verify workflow files are in `.github/workflows/`
3. Check workflow syntax with [action-validator](https://rhysd.github.io/actionlint/)
4. Look for errors in Actions tab

### SonarCloud Authentication Failed

**Problem:** `401 Unauthorized` from SonarCloud

**Solutions:**
1. Regenerate SonarCloud token:
   - Go to SonarCloud → Account → Security
   - Generate new token
   - Update `SONAR_TOKEN` secret in GitHub
2. Verify project key matches exactly (case-sensitive)
3. Check organization key is correct

### LLM API Errors

**Problem:** AI review fails with API errors

**Solutions:**

**Azure OpenAI:**
1. Verify endpoint URL format: `https://[name].openai.azure.com/`
2. Check deployment name matches your actual deployment
3. Ensure you have quota remaining
4. Verify API version is supported (currently `2024-02-15-preview`)

**Anthropic Claude:**
1. Check API key is valid
2. Verify you have credits remaining
3. Check for rate limits (tier-based)

### No Code Changes Detected

**Problem:** AI review says "No code changes"

**Solutions:**
1. Check if files are excluded in config
2. Verify file extensions are in `include_extensions`
3. Review may skip if only docs/config files changed
4. Check if PR has actual diff (not just merge commit)

### Review Quality Issues

**Problem:** AI review is too verbose / not catching issues

**Solutions:**
1. Adjust `temperature` in config (lower = more focused)
2. Try different LLM model
3. Customize system prompt in `llm_client.py`
4. Add specific focus areas in config
5. Provide more context in PR description

## Cost Monitoring

### GitHub Actions

- **Free tier:** 2,000 minutes/month (private repos)
- **Team plan:** 3,000 minutes/month
- **Overage:** $0.006/minute

**Expected usage:** ~4 minutes per review × 20 PRs/day = ~2,400 minutes/month

### SonarCloud

- **Free tier:** Up to 50,000 lines of code
- **Team plan:** €30/month for 500K LOC

### LLM API Costs

**Claude Sonnet 4.5:**
- Input: $3/million tokens
- Output: $15/million tokens
- **Est:** ~$0.024 per PR → ~$10-15/month

**Azure OpenAI GPT-4:**
- Input: $0.03/1K tokens
- Output: $0.06/1K tokens
- **Est:** ~$0.014 per PR → ~$6-10/month

**Total estimated cost:** $15-50/month for 20 PRs/day

## Security Best Practices

1. **Never commit secrets** - Always use GitHub encrypted secrets
2. **Rotate tokens regularly** - Update API keys every 90 days
3. **Use least privilege** - Give tokens minimum required permissions
4. **Monitor usage** - Set up billing alerts
5. **Review logs** - Check Actions logs for sensitive data leaks
6. **Enable 2FA** - On GitHub, SonarCloud, and LLM provider accounts

## Next Steps

- [ ] Set up cost alerts in Azure/Anthropic console
- [ ] Create custom review prompts for your tech stack
- [ ] Add team-specific coding standards to config
- [ ] Set up notifications for failed reviews
- [ ] Create dashboard for tracking review metrics
- [ ] Document team workflows for using AI reviews

## Support

- **GitHub Issues:** [Report bugs or request features]
- **Documentation:** [docs/ARCHITECTURE.md]
- **Community:** [GitHub Discussions]

---

**Setup complete! 🎉**

Your AI code review agent is now ready to improve code quality automatically.
