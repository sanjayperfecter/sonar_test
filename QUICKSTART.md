# Quick Start Guide

Get your AI Code Review Agent running in 15 minutes!

## Prerequisites Checklist

- [ ] GitHub repository with Actions enabled
- [ ] Admin access to repository
- [ ] One of:
  - [ ] Azure OpenAI subscription with GPT-4, OR
  - [ ] Anthropic API key for Claude
- [ ] 15 minutes of time

## Fastest Setup Path

### 1. SonarCloud Setup (5 minutes)

1. Go to [sonarcloud.io](https://sonarcloud.io) → Log in with GitHub
2. Click "+" → "Analyze new project"
3. Select your repository → "Set Up"
4. Choose "With GitHub Actions"
5. Copy these three values (save them!):
   - `SONAR_TOKEN`
   - `SONAR_PROJECT_KEY` 
   - `SONAR_ORGANIZATION`

### 2. Add to GitHub (5 minutes)

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click "New repository secret" and add:
   ```
   SONAR_TOKEN = [paste from step 1]
   SONAR_PROJECT_KEY = [paste from step 1]
   SONAR_ORGANIZATION = [paste from step 1]
   ```

3. Add your LLM provider:

   **For Anthropic Claude:**
   ```
   ANTHROPIC_API_KEY = sk-ant-xxxxx
   ```

   **OR for Azure OpenAI:**
   ```
   AZURE_OPENAI_ENDPOINT = https://your-name.openai.azure.com/
   AZURE_OPENAI_KEY = xxxxx
   AZURE_OPENAI_DEPLOYMENT = gpt-4
   ```

### 3. Add Workflow Files (3 minutes)

Copy these files to your repository:

```bash
# Download/clone this repo
git clone <this-repo-url>

# Copy files to your project
cp -r ai-code-review-agent/.github your-repo/
cp -r ai-code-review-agent/scripts your-repo/
cp ai-code-review-agent/sonar-project.properties your-repo/

# Commit and push
cd your-repo
git add .
git commit -m "Add AI code review agent"
git push
```

### 4. Test It! (2 minutes)

1. Create a test branch:
   ```bash
   git checkout -b test-ai-review
   ```

2. Add a test file with an intentional issue:
   ```python
   # test.py
   def unsafe_query(user_id):
       query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection!
       return query
   ```

3. Push and create PR:
   ```bash
   git add test.py
   git commit -m "Test AI review"
   git push origin test-ai-review
   ```

4. Go to GitHub → Create Pull Request

5. Wait 2-3 minutes and check:
   - ✅ SonarQube analysis appears
   - ✅ AI review comment posts
   - ✅ Status checks show up

**Expected:** AI should flag the SQL injection vulnerability!

## What's Next?

- [ ] Configure branch protection: [docs/SETUP.md](docs/SETUP.md#step-44-configure-branch-protection)
- [ ] Customize review settings: `.github/ai-review-config.yaml`
- [ ] Read full setup guide: [docs/SETUP.md](docs/SETUP.md)
- [ ] Understand architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Troubleshooting

**Workflows not running?**
- Go to Actions tab → Enable workflows if prompted

**SonarCloud failing?**
- Check token is copied correctly (no extra spaces)
- Verify project key matches exactly

**AI review failing?**
- Check API key is valid
- Verify endpoint URL format (Azure)
- Check Actions logs for error details

## Getting Help

- 📖 [Full Setup Guide](docs/SETUP.md)
- 🏗️ [Architecture Docs](docs/ARCHITECTURE.md)
- 🐛 [Report Issue](../../issues)
- 💬 [Ask Question](../../discussions)

---

**Ready to improve your code quality? Let's go! 🚀**
