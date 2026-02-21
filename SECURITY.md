# Security Policy

## Automated Security Scanning

This repository uses automated security scanning on every pull request:

- **Bandit** - Python security linter
- **Semgrep** - Pattern-based security analysis
- **pip-audit** - Dependency vulnerability scanning
- **Gitleaks** - Secret detection
- **Dependabot** - Automated dependency updates

## Reporting a Vulnerability

If you discover a security vulnerability:

1. **Do NOT open a public issue**
2. Email: amitc3353@gmail.com (replace with actual contact)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Initial response:** Within 48 hours
- **Status update:** Within 7 days
- **Fix timeline:** Depends on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2 weeks
  - Low: 1 month

## Security Best Practices

### API Keys & Secrets
- Never commit API keys to version control
- Use `.env` for local development
- Use GitHub Secrets for CI/CD
- Rotate keys if accidentally exposed

### Dependencies
- Keep dependencies up to date
- Review Dependabot PRs promptly
- Monitor security advisories

### Code Review
- All PRs reviewed by automated tools
- Manual review for security-critical changes
- Follow principle of least privilege

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < 1.0   | :x:                |

## Known Issues

None currently reported.
