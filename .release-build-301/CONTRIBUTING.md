# Contributing to EPI Recorder

Thank you for your interest in contributing to EPI Recorder! We welcome contributions from the community.

## 🚀 Quick Start

### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/mohdibrahimaiml/epi-recorder.git
   cd epi-recorder
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Development Dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Run Tests**
   ```bash
   pytest
   ```

## 📝 How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- EPI version and Python version
- Relevant code snippets or error messages

### Suggesting Features

We love new ideas! Please create an issue with:
- Clear use case description
- Proposed solution or API
- Examples of how it would be used
- Any alternatives you've considered

### Submitting Pull Requests

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Your Changes**
   - Follow our code style (see below)
   - Add tests for new functionality
   - Update documentation as needed

3. **Run Quality Checks**
   ```bash
   # Format code
   black .
   
   # Lint code
   ruff check .
   
   # Run tests
   pytest --cov
   ```

4. **Commit Your Changes**
   ```bash
   git commit -m "feat: add amazing feature"
   ```
   
   We use [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `test:` - Test additions/changes
   - `refactor:` - Code refactoring

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a PR on GitHub with:
   - Clear title and description
   - Reference to related issues
   - Screenshots/demos if applicable

## 🎨 Code Style

We use automated tools to maintain code quality:

- **Black** for code formatting
- **Ruff** for linting
- **Type hints** for all public APIs
- **Docstrings** for all public functions/classes

### Example:
```python
def verify_signature(
    manifest: ManifestModel,
    public_key_bytes: bytes
) -> tuple[bool, str]:
    """
    Verify manifest signature using Ed25519 public key.
    
    Args:
        manifest: Manifest to verify
        public_key_bytes: Raw Ed25519 public key bytes (32 bytes)
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    # Implementation
```

## 🧪 Testing Guidelines

- Write tests for all new features
- Maintain >80% code coverage
- Use descriptive test names
- Test edge cases and error conditions

### Example Test:
```python
def test_verify_signature_valid():
    """Verify signature validation works correctly."""
    key = Ed25519PrivateKey.generate()
    manifest = ManifestModel(cli_command="test")
    signed = sign_manifest(manifest, key)
    
    pub_key = key.public_key().public_bytes_raw()
    is_valid, msg = verify_signature(signed, pub_key)
    
    assert is_valid is True
    assert "valid" in msg.lower()
```

## 📚 Documentation

When adding features:
- Update README.md if it affects user-facing functionality
- Add docstrings to new code
- Update relevant documentation files
- Include usage examples

## 🤝 Community Guidelines

- Be respectful and inclusive
- Help others learn and grow
- Give constructive feedback

## 📬 Getting Help

- **Questions**: Use [GitHub Discussions](https://github.com/mohdibrahimaiml/epi-recorder/discussions)
- **Bugs**: Create an [Issue](https://github.com/mohdibrahimaiml/epi-recorder/issues)
- **Email**: mohdibrahim@epilabs.org

## 🎯 Priority Areas

We especially welcome contributions in:
- 🧪 Test coverage improvements
- 📖 Documentation enhancements
- 🐛 Bug fixes
- 🔌 New provider integrations (Anthropic, Cohere, etc.)
- 🌍 Internationalization

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for making EPI Recorder better!** 🚀


 