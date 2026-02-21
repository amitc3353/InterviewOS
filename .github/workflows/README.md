# GitHub Actions Workflows

## PR Review & Security (`pr-review.yml`)

Runs on every pull request to ensure code quality and security.

### Checks Performed

**1. AI-Powered Review (PR-Agent)**
- Context-aware code review
- Logic and design feedback
- Best practice suggestions
- Security recommendations

**2. Linting & Formatting (Ruff)**
- PEP 8 compliance
- Code style consistency
- Auto-fixable issues flagged

**3. Type Checking (mypy)**
- Type safety validation
- Catches type-related bugs early

**4. Security Scanning (Bandit)**
- Python-specific security issues
- Common vulnerability patterns
- Safe coding practices

**5. Pattern Analysis (Semgrep)**
- Bug patterns
- Security rules (OWASP Top 10)
- Framework-specific checks

**6. Dependency Audit (pip-audit)**
- CVE scanning
- Known vulnerability detection
- Outdated package warnings

**7. Secret Detection (Gitleaks)**
- API key leakage prevention
- Credential scanning
- Historical commit analysis

### Reports

All security reports are uploaded as artifacts for review:
- `bandit-report.json`
- `semgrep-report.json`
- `pip-audit-report.json`

---

## Dependabot (`dependabot.yml`)

Automated dependency updates.

**Schedule:** Weekly (Mondays, 9:00 AM)

**Monitors:**
- Python packages (`requirements.txt`)
- GitHub Actions versions

**Auto-merge:** Patch updates auto-merge after checks pass

---

## Setup Requirements

### 1. Add OpenAI API Key (for PR-Agent)

Repository Settings → Secrets and variables → Actions → New repository secret

**Name:** `OPENAI_API_KEY`
**Value:** Your OpenAI API key

### 2. Enable Dependabot

Repository Settings → Code security and analysis → Enable:
- Dependabot alerts
- Dependabot security updates

### 3. Required Permissions

Ensure GitHub Actions has:
- Read access to code
- Write access to pull requests
- Write access to checks

---

## Testing

To test workflows locally before pushing:

```bash
# Install act (GitHub Actions local runner)
brew install act

# Run PR review workflow
act pull_request -W .github/workflows/pr-review.yml
```

---

## Troubleshooting

**PR-Agent not commenting:**
- Check OPENAI_API_KEY is set correctly
- Verify PR-Agent has PR write permissions
- Check workflow logs for errors

**Checks failing:**
- Review security reports in artifacts
- Fix issues flagged by linters
- Update dependencies with vulnerabilities

**Dependabot not creating PRs:**
- Enable Dependabot in repo settings
- Check dependabot.yml syntax
- Verify GitHub Actions permissions
