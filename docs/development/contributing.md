# Contributing to GeoDE

Thank you for your interest in contributing to GeoDE!

## Development Setup

1. **Clone the repository:**
    ```bash
    git clone https://github.com/demiangomez/Parallel.GAMIT.git
    cd geode
    ```

2. **Install dependencies with Pixi:**
    ```bash
    # The default environment includes dev dependencies (type stubs, linters, etc.)
    pixi install
    pixi shell
    ```

3. **Set up pre-commit hooks (recommended):**
    ```bash
    pixi run precommit:install
    ```
    
    This installs git hooks that automatically run:
    - Ruff (linting & formatting)
    - Gitleaks (secret detection)
    - Commitizen (commit message validation)
    - Various file checks

4. **Run tests:**
    ```bash
    pixi run test
    ```

## Code Style

- Follow PEP 8 for Python code
- Use descriptive variable and function names
- Add docstrings to functions and classes
- Include type hints where practical
- Code is automatically formatted with Ruff (Astral)

### Formatting and Linting

```bash
# Check formatting (doesn't modify files)
pixi run format:check

# Auto-format code
pixi run format

# Run linter
pixi run lint

# Auto-fix linting issues
pixi run lint:fix
```

### Type Checking

We use ty (by Astral, makers of Ruff and uv) for static type checking:

```bash
pixi run typecheck
```

Type stubs are included for major dependencies (numpy, pandas, tqdm, requests, etc.).

## Testing

Run the test suite before submitting changes:

```bash
# Run all tests
pixi run test

# Run with coverage report
pixi run test:cov

# Run verbose output
pixi run test:verbose
```

## Documentation

Documentation uses MkDocs with the Material theme.

### Preview documentation locally:

```bash
pixi run -e docs docs:serve
```

Then open http://127.0.0.1:8000 in your browser.

### Build documentation:

```bash
pixi run -e docs docs:build
```

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) for clear, semantic commit messages.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic changes)
- `refactor`: Code refactoring (no features or bug fixes)
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `build`: Build system or dependency changes
- `ci`: CI/CD changes
- `chore`: Other changes (tooling, maintenance)

### Examples

```bash
feat(archive): add support for RINEX 4 format

fix(etm): correct trajectory fitting for large gaps

docs(contributing): add pre-commit hook setup instructions
```

### Using Commitizen

If pre-commit hooks are installed, commits are automatically validated. You can also use commitizen interactively:

```bash
pixi exec cz commit
```

## Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes
4. Run all checks:
   ```bash
   pixi run format:check  # Check formatting
   pixi run lint          # Check for issues
   pixi run typecheck     # Check types (optional but recommended)
   pixi run test          # Run tests
   ```
5. Commit with conventional commit messages
6. Push to your fork
7. Open a Pull Request

### Pre-commit Hooks

If you have pre-commit hooks installed (`pixi run precommit:install`), these checks run automatically on each commit:

- ✅ Code formatting (Ruff)
- ✅ Linting (Ruff)
- ✅ Secret detection (Gitleaks)
- ✅ Commit message validation (Commitizen)
- ✅ File checks (trailing whitespace, file size, etc.)

Run all hooks manually:

```bash
pixi run precommit:run
```

## Issue Reporting

When reporting issues, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant error messages or logs

## Security

### Secret Scanning

Gitleaks runs automatically in CI and as a pre-commit hook to prevent accidental commits of secrets.

If you need to ignore false positives, add them to `.gitleaksignore`.

### Reporting Security Issues

Please report security vulnerabilities privately through GitHub Security Advisories rather than public issues.

## Development Environments

Pixi supports multiple environments:

- **default**: Main environment with dev dependencies (type stubs, ty, pre-commit)
- **docs**: Documentation building environment with mkdocs
- **reports**: PDF and map export dependencies
- **web**: Django/DRF backend testing (`pixi run -e web test:api`)

Switch environments:

```bash
# Use default environment (includes dev tools)
pixi shell

# Use docs environment
pixi shell -e docs
```

## Questions

For questions about the codebase or development, open a GitHub issue or discussion.
