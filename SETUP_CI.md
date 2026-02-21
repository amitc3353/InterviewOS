# CI/CD Setup Guide

## 🚀 Quick Start (5 minutes)

### 1. Add OpenAI API Key (Required for PR-Agent)

**GitHub Repository → Settings → Secrets and variables → Actions → New repository secret**

- **Name:** `OPENAI_API_KEY`
- **Value:** Your OpenAI API key (sk-...)

This enables AI-powered code reviews on every PR.

---

### 2. Enable Dependabot (Free vulnerability scanning)

**GitHub Repository → Settings → Code security and analysis**

Enable:
- ✅ Dependabot alerts
- ✅ Dependabot security updates

Dependabot will:
- Monitor `requirements.txt` for vulnerabilities
- Auto-create PRs for security updates weekly
- Auto-merge patch updates (after checks pass)

---

### 3. Verify Workflow Permissions

**GitHub Repository → Settings → Actions → General → Workflow permissions**

Select:
- ✅ Read and write permissions
- ✅ Allow GitHub Actions to create and approve pull requests

This lets PR-Agent post review comments and Dependabot auto-merge.

---

## ✅ Test It

### On PR #7 (already open):

1. **Trigger workflows:**
   ```bash
   # Make a trivial change to trigger CI
   git checkout feature/realtime-voice-phase1
   echo "# CI Test" >> SETUP_CI.md
   git add SETUP_CI.md
   git commit -m "test: Trigger CI workflows"
   git push origin feature/realtime-voice-phase1
   ```

2. **Check PR #7 → Checks tab:**
   - `ai-review` - PR-Agent review comments
   - `security-quality` - Lint/type/security reports
   - `secret-scan` - Gitleaks results

3. **Review feedback:**
   - PR-Agent comments appear inline
   - Security reports in artifacts
   - All checks must pass to merge

---

## 🛠️ What Runs on Every PR

| Check | Tool | What It Does |
|-------|------|-------------|
| **AI Review** | PR-Agent | Context-aware code review, design feedback |
| **Linting** | Ruff | PEP 8, code style |
| **Type Safety** | mypy | Type checking |
| **Security** | Bandit | Python security issues |
| **Patterns** | Semgrep | Bug patterns, OWASP rules |
| **Dependencies** | pip-audit | CVE scanning |
| **Secrets** | Gitleaks | API key leakage |

---

## 📊 View Reports

**After PR checks run:**

1. Go to PR → Checks → `security-quality` → Summary
2. Download artifacts:
   - `bandit-report.json` - Security issues
   - `semgrep-report.json` - Pattern analysis
   - `pip-audit-report.json` - Dependency vulnerabilities

---

## 🔧 Troubleshooting

### PR-Agent not commenting?

**Check:**
1. `OPENAI_API_KEY` is set in repo secrets
2. Workflow has PR write permissions (Settings → Actions → General)
3. OpenAI API key has credits

**Fix:** Add/update the secret, re-run workflow

---

### Checks failing?

**Common issues:**

1. **Ruff linting errors:**
   ```bash
   # Auto-fix locally
   pip install ruff
   ruff check --fix .
   ruff format .
   git add -A && git commit -m "fix: Ruff auto-fixes"
   ```

2. **Bandit security warnings:**
   - Review `bandit-report.json` artifact
   - Fix flagged issues or add `# nosec` comment if false positive

3. **Dependency vulnerabilities:**
   - Wait for Dependabot PR
   - Or update manually: `pip install --upgrade <package>`

---

### Dependabot not creating PRs?

**Check:**
1. Dependabot enabled in Settings → Security
2. `.github/dependabot.yml` syntax valid
3. Wait for Monday 9:00 AM (scheduled run)

**Force run:** Settings → Security → Dependabot → Check for updates

---

## 📝 Customization

### Adjust PR-Agent behavior

Edit `.github/pr-agent.toml`:
```toml
[pr_reviewer]
num_code_suggestions = 10  # More suggestions
require_security_review = true  # Force security review
```

### Change Dependabot schedule

Edit `.github/dependabot.yml`:
```yaml
schedule:
  interval: "daily"  # Check daily instead of weekly
```

### Add more security checks

Edit `.github/workflows/pr-review.yml`:
```yaml
- name: Custom security check
  run: |
    your-security-tool .
```

---

## 🎯 Next Steps

1. ✅ Add `OPENAI_API_KEY` secret
2. ✅ Enable Dependabot
3. ✅ Set workflow permissions
4. ✅ Test on PR #7
5. ✅ Review reports
6. ✅ Fix any issues flagged
7. ✅ Merge PR #7

CI is now protecting your codebase! 🎉
