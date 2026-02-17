# Architecture Overview

This document explains the technical architecture and design decisions of the AI Code Review Agent.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      GitHub Repository                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      │ Push/PR Event
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions Runner                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Workflow 1: SonarQube Analysis                       │  │
│  │  ┌─────────────┐         ┌──────────────┐           │  │
│  │  │  Checkout   │────────▶│  SonarCloud  │           │  │
│  │  │  Code       │         │  Scan        │           │  │
│  │  └─────────────┘         └──────┬───────┘           │  │
│  │                                  │                    │  │
│  │                                  │ Results            │  │
│  │                                  ▼                    │  │
│  │                          ┌──────────────┐            │  │
│  │                          │ Quality Gate │            │  │
│  │                          │ Status       │            │  │
│  │                          └──────┬───────┘            │  │
│  └─────────────────────────────────┼────────────────────┘  │
│                                    │                        │
│  ┌────────────────────────────────┼────────────────────┐   │
│  │  Workflow 2: AI Code Review    │                    │   │
│  │                                 │                    │   │
│  │  ┌──────────────┐              │                    │   │
│  │  │ Wait for     │◀─────────────┘                    │   │
│  │  │ SonarQube    │                                    │   │
│  │  └──────┬───────┘                                    │   │
│  │         │                                            │   │
│  │         ▼                                            │   │
│  │  ┌──────────────────────────────────────────┐       │   │
│  │  │     review.py (Main Orchestrator)        │       │   │
│  │  │                                           │       │   │
│  │  │  ┌────────────────┐  ┌─────────────────┐│       │   │
│  │  │  │ github_api.py  │  │  sonar_api.py   ││       │   │
│  │  │  │                │  │                 ││       │   │
│  │  │  │ • Fetch diff   │  │ • Get issues    ││       │   │
│  │  │  │ • Get PR info  │  │ • Quality gate  ││       │   │
│  │  │  │ • Post review  │  │ • Format results││       │   │
│  │  │  └────────┬───────┘  └────────┬────────┘│       │   │
│  │  │           │                   │          │       │   │
│  │  │           └────────┬──────────┘          │       │   │
│  │  │                    ▼                     │       │   │
│  │  │           ┌─────────────────┐            │       │   │
│  │  │           │  llm_client.py  │            │       │   │
│  │  │           │                 │            │       │   │
│  │  │           │ • Claude API    │            │       │   │
│  │  │           │ • Azure OpenAI  │            │       │   │
│  │  │           │ • Fallback      │            │       │   │
│  │  │           └────────┬────────┘            │       │   │
│  │  └────────────────────┼─────────────────────┘       │   │
│  └─────────────────────────┼──────────────────────────┘   │
└─────────────────────────────┼──────────────────────────────┘
                              │
                              │ AI Review Results
                              ▼
                    ┌──────────────────┐
                    │   GitHub PR      │
                    │                  │
                    │ • Summary review │
                    │ • Inline comments│
                    │ • Status checks  │
                    │ • Suggestions    │
                    └──────────────────┘
```

## Components

### 1. GitHub Actions Workflows

#### sonarqube.yml
- **Trigger:** PR opened, synchronized, reopened
- **Purpose:** Static code analysis
- **Actions:**
  - Checkout code
  - Run SonarCloud scan
  - Check quality gate
  - Post status to PR

#### ai-review.yml
- **Trigger:** PR opened, synchronized, reopened, ready_for_review
- **Dependencies:** Waits for SonarQube completion
- **Purpose:** AI-powered semantic code review
- **Actions:**
  - Checkout code
  - Setup Python environment
  - Install dependencies
  - Run review.py
  - Create status checks

### 2. Core Python Modules

#### review.py (Main Orchestrator)
```python
main()
  ├─ Initialize clients (GitHub, SonarQube, LLM)
  ├─ Fetch PR information
  ├─ Get code diff
  ├─ Fetch SonarQube results
  ├─ Call LLM for analysis
  ├─ Determine review event type
  ├─ Post review to GitHub
  └─ Set status checks
```

**Responsibilities:**
- Workflow orchestration
- Error handling and retry logic
- Decision making (approve/request changes/comment)
- Status reporting
- Confidence-based filtering of AI suggestions
- Duplicate suggestion suppression
- PR risk scoring
- Severity tagging for inline issues
- Refactor opportunity detection

#### github_api.py (GitHub Client)
```python
GitHubClient
  ├─ get_pr_info() → PR metadata
  ├─ get_pr_diff() → Code changes
  ├─ get_changed_files() → File list
  ├─ should_skip_file() → Filter logic
  ├─ post_review_comment() → Inline comments
  ├─ post_review_summary() → Overall review
  ├─ create_suggested_change() → One-click fixes
  └─ set_status() → Status checks
```

**Key Features:**
- Uses PyGithub library
- Rate limit handling
- Configuration-based file filtering
- Supports suggested changes syntax

#### sonar_api.py (SonarQube Client)
```python
SonarClient
  ├─ get_issues_for_pr() → Issue list
  ├─ get_quality_gate_status() → Pass/fail status
  ├─ get_metrics() → Code metrics
  ├─ format_issues_for_context() → LLM-friendly format
  └─ has_critical_issues() → Severity check
```

**Key Features:**
- REST API integration
- Issue grouping by severity
- Quality gate validation
- Formatted output for AI context

#### llm_client.py (LLM Integration)
```python
LLMClient
  ├─ review_with_claude() → Claude Sonnet 4.5
  ├─ review_with_azure_openai() → GPT-4.1.mini(GPT4.1)
  ├─ review_code() → Main entry with fallback
  ├─ _build_system_prompt() → Expert reviewer persona
  └─ _build_user_prompt() → Context assembly
  ├─ review_code_structured() → Structured JSON output
  ├─ Severity classification (CRITICAL/MAJOR/MINOR/STYLE/REFACTOR)
  ├─ Confidence scoring (0.0–1.0)
  ├─ Inline suggestion generation
  ├─ Refactor detection
  ├─ Large PR chunking
  └─ Natural-language suggestion sanitization
```

**Key Features:**
- Multi-provider support (Claude + Azure OpenAI)
- Automatic fallback
- Retry logic with exponential backoff
- Structured prompting
- Cost optimization (streaming, caching)

### 3. Configuration

#### .github/ai-review-config.yaml
```yaml
review:
  exclude_patterns: [patterns]
  include_extensions: [extensions]
  max_comments: N

llm:
  primary_model: "model-name"
  fallback_model: "fallback-name"
  max_tokens: N
  temperature: 0.0-1.0

sonarqube:
  enforce_quality_gate: true/false
  block_on_critical: true/false

github:
  post_summary: true/false
  suggest_changes: true/false
```

## Data Flow

### 1. PR Creation/Update Flow

```
Developer pushes code
       ↓
GitHub webhook fires
       ↓
sonarqube.yml triggers
       ↓
SonarCloud analyzes code
       ↓
Quality gate evaluated
       ↓
Status posted to PR
       ↓
ai-review.yml triggers
       ↓
Waits for SonarQube completion
       ↓
review.py executes
```

### 2. Review Script Flow

```
review.py starts
       ↓
1. Initialize clients
   ├─ GitHubClient (PyGithub)
   ├─ SonarClient (requests)
   └─ LLMClient (anthropic/openai)
       ↓
2. Fetch PR data
   ├─ PR metadata (title, author, stats)
   ├─ Code diff (changed lines)
   └─ File list (filtered by config)
       ↓
3. Get SonarQube results
   ├─ Issues by severity
   ├─ Quality gate status
   └─ Code metrics
       ↓
4. Build LLM prompt
   ├─ System: Expert reviewer persona
   └─ User: PR info + diff + SonarQube context
       ↓
5. Call LLM API
   ├─ Primary: Claude Sonnet 4.5
   └─ Fallback: Azure OpenAI GPT-4
       ↓
6. Parse AI response
   ├─ Extract critical issues
   ├─ Extract suggestions
   └─ Identify positive feedback
       ↓
7. Determine review type
   ├─ Critical issues? → REQUEST_CHANGES
   ├─ All positive? → APPROVE
   └─ Default → COMMENT
       ↓
8. Post to GitHub
   ├─ Summary review
   ├─ Inline comments
   └─ Status check
       ↓
Review complete
```

## Design Decisions
## AI Review Intelligence Layer (New)

The AI reviewer now includes a multi-stage intelligence pipeline:

1) Diff + Full File Context
2) SonarQube issue context
3) Structured LLM analysis
4) Post-processing layer:
   - Confidence filtering
   - Duplicate detection
   - Severity tagging
   - Refactor suggestion classification
   - Risk scoring

### Severity Levels

Each suggestion is categorized as:

- CRITICAL → Security / crash risks
- MAJOR → Logic bugs / performance issues
- MINOR → Code quality improvements
- STYLE → Formatting / naming
- REFACTOR → Structural improvements

### Confidence Filtering

Suggestions below confidence threshold (default: 0.65) are discarded to reduce noise.

### Duplicate Suppression

Similar suggestions are removed using semantic similarity comparison.

### Risk Score Engine

Each PR receives a risk score (0–10) based on:

- Size of PR
- Sonar issues
- Critical suggestions
- Code churn

Displayed in review summary as:

Risk Score: 7/10 (HIGH)

### Why GitHub Actions over GitHub App?

**Chosen:** GitHub Actions
**Alternative:** GitHub App with webhook server

**Reasons:**
1. **Zero infrastructure** - No server to host
2. **Simpler setup** - Just YAML files
3. **Sufficient for scale** - 20 PRs/day easily handled
4. **Cost effective** - Free tier covers usage
5. **Easy debugging** - Logs in Actions tab

**Trade-off:** Limited to 5,000 API calls/hour vs 15,000 with GitHub App

### Why Sequential (SonarQube → AI) over Parallel?

**Chosen:** Sequential with wait
**Alternative:** Parallel execution

**Reasons:**
1. **Better context** - AI sees SonarQube results
2. **Avoid duplication** - AI doesn't repeat static analysis findings
3. **Informed decisions** - Review type considers both analyses
4. **Clear workflow** - Easier to debug

**Trade-off:** Adds 2-3 minutes to total review time

### Why Claude Sonnet 4.5 as Primary?

**Chosen:** Claude Sonnet 4.5
**Alternative:** GPT-4, GPT-4o

**Reasons:**
1. **Best SWE-bench score** - 77.2% (82% with parallel)
2. **Superior code understanding** - Proven on real PRs
3. **Lower error rate** - 0% vs 9% (Replit benchmark)
4. **Better context window** - 200K tokens
5. **Azure Foundry availability** - Unified billing

**Trade-off:** Slightly higher cost ($0.024 vs $0.014 per PR)

### Why Direct API over MCP?

**Chosen:** Direct REST/SDK calls
**Alternative:** Model Context Protocol (MCP)

**Reasons:**
1. **Deterministic workflow** - Operations known at design time
2. **Lower latency** - No tool discovery overhead
3. **Simpler debugging** - Fewer abstraction layers
4. **Production patterns** - No major tool uses MCP for CI/CD
5. **Easier maintenance** - Standard HTTP libraries

**Trade-off:** Less flexible for future agentic workflows

### Why Suggested Changes over Auto-commit?

**Chosen:** GitHub suggested changes API
**Alternative:** AI pushes fix commits

**Reasons:**
1. **Security best practice** - Human review gate
2. **Developer control** - One-click apply or reject
3. **Clear audit trail** - Changes attributed correctly
4. **Industry standard** - Copilot, CodeRabbit use this
5. **Simpler permissions** - No write access needed

**Trade-off:** Requires developer action to apply fixes



## Security Model

### Secrets Management
- All credentials stored in GitHub encrypted secrets
- Never logged or exposed in workflow output
- Rotated regularly (recommended: 90 days)
- Minimum required permissions

### Branch Protection
- Required status checks prevent merge without review
- Stale approvals dismissed on new commits
- No bypass for AI agent
- Force push blocked

### API Permissions

**GitHub Token (GITHUB_TOKEN):**
- `contents: read` - Read code
- `pull-requests: write` - Post reviews
- `checks: write` - Create status checks

**SonarQube Token:**
- Read-only access to project
- Scoped to specific organization

**LLM API Keys:**
- Rate-limited by provider
- Billing alerts configured
- Usage monitoring enabled

## Performance Characteristics

### Latency
- **SonarQube scan:** 1-3 minutes (varies by code size)
- **AI review:** 30-60 seconds (typical PR)
- **Total:** 2-5 minutes per PR

### Throughput
- **Concurrent PRs:** Handled by GitHub Actions concurrency
- **Daily capacity:** 20-50 PRs comfortably
- **Peak handling:** Scales with Actions minutes

### Resource Usage
- **CPU:** Minimal (I/O bound)
- **Memory:** <512MB per review
- **Network:** 1-5 MB per PR (diff + API calls)
- **Storage:** Ephemeral (no persistence)

## Cost Model

### Fixed Costs
- GitHub Actions: $0 (within free tier)
- SonarCloud: $0-€30/month

### Variable Costs (per PR)
- LLM API: $0.01-0.024 (model dependent)
- GitHub API: $0 (no charges)
- SonarCloud API: $0 (no charges)

### Monthly Estimates (20 PRs/day)
- Infrastructure: $0-10
- SonarCloud: $0-30
- LLM APIs: $10-20
- **Total: $15-60/month**

## Scalability

### Current Scale (20 PRs/day)
- ✅ Well within all limits
- ✅ No optimization needed
- ✅ Cost negligible

### 100 PRs/day
- ⚠️ May exceed GitHub Actions free tier
- ✅ API rate limits still comfortable
- ⚠️ LLM costs: ~$75/month

### 1000 PRs/day
- ❌ Need GitHub Actions paid plan
- ⚠️ Consider rate limit optimization
- ⚠️ LLM costs: ~$750/month
- ✅ Consider GitHub App migration

## Monitoring & Observability

### Built-in Logging
- GitHub Actions logs (15 days retention)
- Status checks history
- PR comments timeline

### Recommended Additions
- LLM API usage dashboard
- Cost tracking alerts
- Review quality metrics
- Response time monitoring

## Extension Points

### Custom Prompts
Edit `llm_client.py` → `_build_system_prompt()` for domain-specific review focus.

### Additional Checks
Add modules in `scripts/` and import in `review.py` for:
- License compliance
- Dependency vulnerability scanning
- Custom linters
- Test coverage analysis

### Multi-file Analysis
Extend `github_api.py` → `get_file_content()` usage in `review.py` for full file context (increases LLM costs).

### Inline Suggestions
Implement parsing of AI response to extract line-specific issues and post with `create_suggested_change()`.

## Failure Modes & Recovery

### LLM API Failure
- **Retry:** 3 attempts with exponential backoff
- **Fallback:** Switch to alternate provider
- **Degradation:** Post error comment, don't block PR

### SonarQube Failure
- **Continue:** AI review proceeds without static analysis context
- **Warning:** Note in review that SonarQube data missing

### GitHub API Failure
- **Retry:** Automatic via PyGithub
- **Fail:** Mark status check as error, log for investigation

### Rate Limits
- **GitHub:** 5,000/hour → Pause 15 min
- **LLM:** Provider-dependent → Exponential backoff
- **SonarCloud:** Generous → Rare issue

## Future Enhancements

### Considered
- [ ] Multi-language prompt optimization
- [ ] Fine-tuned model for domain-specific reviews
- [ ] Automated fix PRs for simple issues
- [ ] Learning from human review overrides

---

**Architecture Version:** 1.0  
**Last Updated:** February 2026  
**Status:** Production Ready
