# Contributing to AI Code Review Agent

Thank you for your interest in contributing! 🎉

## How to Contribute

### Reporting Bugs

1. Check if the bug is already reported in [Issues](../../issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)
   - Relevant logs from GitHub Actions

### Suggesting Features

1. Check existing [Issues](../../issues) and [Discussions](../../discussions)
2. Create a new issue with:
   - Clear description of the feature
   - Use case and benefits
   - Possible implementation approach

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes:
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation as needed
4. Test your changes:
   ```bash
   pytest tests/
   ```
5. Commit with clear messages:
   ```bash
   git commit -m "Add feature: description"
   ```
6. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
7. Open a Pull Request with:
   - Clear description of changes
   - Reference related issues
   - Screenshots if UI changes

## Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/ai-code-review-agent.git
cd ai-code-review-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r scripts/requirements.txt

# Run tests
pytest tests/ -v
```

## Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep functions focused and single-purpose
- Write descriptive variable names

## Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting PR
- Aim for >80% code coverage

## Documentation

- Update README.md for user-facing changes
- Update ARCHITECTURE.md for design changes
- Update SETUP.md for configuration changes
- Add inline comments for complex logic

## Questions?

- Open a [Discussion](../../discussions) for general questions
- Create an [Issue](../../issues) for bug reports or feature requests

Thank you for contributing! 🚀
