# Development Quick Reference

## 🚀 Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd geode
pixi install --locked     # Reproduce the committed development environment
pixi run precommit:install  # Setup git hooks (recommended!)
```

Pixi keeps this repository's environments in `.pixi/envs/`; no separate uv or
virtualenv setup is needed. Run tools through `pixi run` so they use the locked
Python and dependencies. Python 3.13+ uses `legacy-cgi` for the existing Dispy
monitoring server until the planned Celery migration replaces Dispy.

## 📦 Pixi Environments

### Default Environment (Automatic)
The **default** environment now includes the `dev` feature, so `pixi install` automatically installs:
- ✅ All runtime dependencies
- ✅ Type stubs (types-tqdm, types-requests, types-paramiko, types-setuptools)
- ✅ ty (type checker by Astral)
- ✅ Pre-commit (git hooks)
- ✅ Commitizen (conventional commits)

**You don't need `--feature dev` anymore!** 🎉

### Docs Environment
```bash
pixi shell -e docs     # For building documentation
pixi run docs:serve    # Preview docs
pixi run docs:build    # Build static docs
```

## 🛠️ Common Tasks

### Testing
```bash
pixi run test           # Run pytest
pixi run test:cov       # Run with coverage report
pixi run test:verbose   # Verbose output
```

### Linting & Formatting (Ruff by Astral)
```bash
pixi run lint           # Check for issues
pixi run lint:fix       # Auto-fix issues
pixi run format         # Format code
pixi run format:check   # Check formatting without changes
```

### Type Checking (ty by Astral)
```bash
pixi run typecheck      # Check types in geode/ and com/
```

### Pre-commit Hooks
```bash
pixi run precommit:install  # Install hooks (one-time setup)
pixi run precommit:run      # Run all hooks manually
```

### All Checks (CI-like)
```bash
pixi run check          # Runs: lint + format:check + test
```

## 📝 Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `perf`: Performance
- `test`: Tests
- `build`: Build/dependencies
- `ci`: CI/CD
- `chore`: Maintenance

### Examples
```bash
feat(archive): add RINEX 4 support
fix(etm): correct trajectory fitting algorithm
docs(readme): update installation instructions
```

### Interactive Commits
```bash
pixi exec cz commit     # Guided commit message creation
```

## 🔒 Security

### Gitleaks
Gitleaks runs automatically:
- ✅ On every commit (pre-commit hook)
- ✅ In CI on push/PR
- ✅ Weekly scheduled scans

False positives? Add to `.gitleaksignore`

### GitHub Actions
Three workflows:
1. **test.yml** - Linting, formatting, and tests
2. **security.yml** - Gitleaks, dependency review, pip-audit
3. **publish.yml** - Package publishing (existing)

## 🎯 Pre-commit Hooks

Installed hooks run automatically on `git commit`:

1. **Ruff** - Format and lint code
2. **Gitleaks** - Detect secrets
3. **Commitizen** - Validate commit messages
4. **File checks** - Trailing whitespace, file sizes, YAML syntax, etc.

Skip hooks (not recommended):
```bash
git commit --no-verify
```

## 📚 File Overview

### New Files Created
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `.gitleaksignore` - Gitleaks false positive ignore list
- `.github/workflows/security.yml` - Security scanning workflow
- `DEVELOPMENT.md` - This file!

### Modified Files
- `pixi.toml` - Added dev feature, tasks, and default environment
- `pyproject.toml` - Added commitizen and ty configuration
- `docs/development/contributing.md` - Updated with new dev workflow

## 🔧 Configuration Files

### ty (`pyproject.toml`)
- Checks: `geode/`, `com/`
- Excludes: `archive/`, `web/`, `node_modules`, etc.

### Commitizen (`pyproject.toml`)
- Standard: Conventional Commits
- Version: Managed by setuptools-scm
- Auto-update changelog on version bumps

### Pre-commit (`.pre-commit-config.yaml`)
- Excludes: `archive/`, `*.lock`
- Auto-fix enabled for ruff and file issues

## ❓ FAQ

### Q: Why ty instead of mypy?
**A:** ty (by Astral, makers of ruff and uv) is:
- Faster
- Modern architecture
- Part of the same ecosystem as ruff

### Q: Do I need to run `pixi install --feature dev`?
**A:** No! The default environment now includes dev features automatically. Just run `pixi install`.

### Q: Can I skip pre-commit hooks?
**A:** Technically yes (`git commit --no-verify`), but don't! They catch issues before CI does.

### Q: What if Gitleaks flags a false positive?
**A:** Add the specific line to `.gitleaksignore` with the format: `SHA:file:line`

### Q: How do I update pre-commit hooks?
**A:** Run `pre-commit autoupdate` to update to latest versions in `.pre-commit-config.yaml`

## 🎓 Learning Resources

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Pre-commit Documentation](https://pre-commit.com/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [ty Documentation](https://docs.astral.sh/ty/)
- [Pixi Documentation](https://pixi.sh/)
- [Gitleaks Documentation](https://github.com/gitleaks/gitleaks)

## 🚨 Troubleshooting

### Pre-commit hooks not running?
```bash
pixi run precommit:install  # Reinstall hooks
```

### Type checking errors?
```bash
pixi install  # Ensure type stubs are installed
```

### Ruff conflicts?
```bash
pixi run format  # Auto-format first
pixi run lint:fix  # Then fix remaining issues
```

### Commit message rejected?
Follow the conventional commits format. Use `pixi exec cz commit` for guidance.
