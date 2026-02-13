# Contributing to mcp-fess

Thank you for your interest in contributing to mcp-fess! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pip

### Setting up the Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/Buttje/mcp-fess.git
   cd mcp-fess
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package in development mode with dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Install pre-commit hooks (optional but recommended):
   ```bash
   pre-commit install
   ```

## Development Workflow

### Code Style

This project uses:
- **Ruff** for linting and code formatting
- **MyPy** for static type checking
- **Pytest** for testing

### Running Linters

```bash
# Run ruff linter
ruff check src tests

# Auto-fix issues
ruff check --fix src tests

# Format code
ruff format src tests
```

### Type Checking

```bash
mypy src
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=mcp_fess --cov-report=html

# Run specific test file
pytest tests/test_server.py

# Run tests matching pattern
pytest -k "test_main"
```

### Pre-commit Hooks

Pre-commit hooks run automatically before each commit if installed. To run manually:

```bash
pre-commit run --all-files
```

## Code Quality Standards

- All code must pass ruff linting and formatting checks
- All code must pass mypy type checking
- All tests must pass
- Code coverage should be maintained or improved
- New features should include tests
- Public APIs should have docstrings

## Pull Request Process

1. Fork the repository and create a new branch from `main`
2. Make your changes following the code style guidelines
3. Add or update tests as needed
4. Ensure all tests pass and linters are satisfied
5. Update documentation if needed
6. Submit a pull request with a clear description of changes

## Reporting Issues

When reporting issues, please include:
- A clear description of the problem
- Steps to reproduce the issue
- Expected vs actual behavior
- Your environment (OS, Python version)
- Any relevant error messages or logs

## Questions?

Feel free to open an issue for any questions about contributing!
