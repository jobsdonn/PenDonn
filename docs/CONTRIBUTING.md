# Contributing to PenDonn

First off, thank you for considering contributing to PenDonn! This is an educational project, and we welcome contributions that help improve security testing capabilities.

## 🔒 Legal Requirements

Before contributing, you **MUST** agree that:

1. ✅ Your contributions will be used for **LEGAL and AUTHORIZED** testing only
2. ✅ You will **NOT** contribute code designed for malicious purposes
3. ✅ You understand this is an **EDUCATIONAL** project
4. ✅ All contributions must include appropriate legal warnings

## 🎯 Ways to Contribute

### 1. Report Bugs
- Use GitHub Issues
- Provide detailed reproduction steps
- Include system information (OS, Python version, etc.)
- Include relevant log excerpts

### 2. Suggest Features
- Open a GitHub Issue with the "enhancement" label
- Describe the use case
- Explain why it would be useful for penetration testing
- Consider security implications

### 3. Write Plugins
- Create new vulnerability scanner plugins
- Follow the plugin development guide in README.md
- Test thoroughly before submitting
- Document what the plugin does

### 4. Improve Documentation
- Fix typos or unclear explanations
- Add examples
- Translate documentation (future)
- Create video tutorials

### 5. Submit Code
- Fix bugs
- Implement features
- Improve performance
- Enhance security

## 📝 Development Setup

### 1. Fork and Clone

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/pendonn.git
cd pendonn
```

### 2. Create Development Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest black flake8 pylint
```

### 3. Create a Branch

```bash
git checkout -b feature/my-awesome-feature
# or
git checkout -b fix/bug-description
```

## 🎨 Code Style

### Python Code Style
- Follow PEP 8
- Use 4 spaces for indentation
- Maximum line length: 100 characters
- Use meaningful variable names
- Add docstrings to all functions/classes

### Example:

```python
def scan_network(host: str, port: int) -> Dict:
    """
    Scan a network host for vulnerabilities.
    
    Args:
        host: IP address or hostname
        port: Port number to scan
    
    Returns:
        Dictionary containing scan results
    
    Raises:
        ScanError: If scan fails
    """
    # Implementation here
    pass
```

### Format Code

```bash
# Format with black
black .

# Check with flake8
flake8 .

# Lint with pylint
pylint core/ web/ plugins/
```

## 🧪 Testing

### Write Tests
- Add tests for new features
- Ensure existing tests pass
- Aim for >80% code coverage

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=web

# Run specific test
pytest tests/test_database.py
```

## 📊 Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting)
- **refactor**: Code refactoring
- **test**: Adding tests
- **chore**: Maintenance tasks

### Examples

```bash
git commit -m "feat(plugins): add DNS enumeration plugin"
git commit -m "fix(cracker): handle empty wordlist gracefully"
git commit -m "docs(readme): update installation instructions"
```

## 🔌 Plugin Development Guidelines

### Plugin Structure

```
plugins/my_scanner/
├── plugin.json          # Plugin metadata
├── my_scanner.py        # Main plugin code
├── README.md            # Plugin documentation
└── requirements.txt     # Plugin-specific dependencies (optional)
```

### Plugin Checklist
- [ ] Inherits from `PluginBase`
- [ ] Implements `run()` method correctly
- [ ] Uses proper logging (`self.log_info()`, etc.)
- [ ] Adds vulnerabilities to database
- [ ] Handles errors gracefully
- [ ] Includes documentation
- [ ] Tested on real networks (authorized only!)

### Plugin Best Practices
- ✅ Use timeouts for network operations
- ✅ Handle exceptions properly
- ✅ Log detailed information
- ✅ Be respectful of target systems (don't DoS)
- ✅ Follow rate limiting guidelines
- ✅ Clean up resources after scanning

## 🔍 Code Review Process

1. **Submit Pull Request**
   - Clear description of changes
   - Reference related issues
   - Include test results
   - Update documentation

2. **Automated Checks**
   - Code style checks pass
   - Tests pass
   - No security vulnerabilities introduced

3. **Manual Review**
   - Code quality assessment
   - Security implications review
   - Legal compliance check
   - Feature completeness

4. **Approval & Merge**
   - At least one maintainer approval
   - All comments addressed
   - CI/CD passes

## 🚫 What NOT to Contribute

- ❌ Exploits for 0-day vulnerabilities
- ❌ Code designed to cause harm or damage
- ❌ Stolen code or copyright violations
- ❌ Backdoors or malicious code
- ❌ Features that enable illegal activities
- ❌ Contributions without proper authorization

## 📜 Legal Considerations

### Your Responsibilities
- Ensure your contributions are legal in your jurisdiction
- Test only on authorized networks
- Don't include real passwords or sensitive data
- Respect intellectual property rights

### Licensing
- All contributions will be under MIT License (Educational Use Only)
- By contributing, you agree to this license
- You retain copyright to your contributions
- You grant the project rights to use your contributions

## 🆘 Getting Help

### Questions?
- Check existing issues and documentation first
- Open a discussion on GitHub
- Join our community chat (if available)
- Contact maintainers

### Stuck?
- Review the README.md thoroughly
- Check troubleshooting section
- Look at existing plugin examples
- Ask for help in your pull request

## 🎖️ Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in plugin headers (for plugin authors)

## 📚 Resources

### Documentation
- [README.md](README.md) - Main documentation
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [LICENSE](LICENSE) - Legal terms

### Related Projects
- Aircrack-ng: https://www.aircrack-ng.org/
- Metasploit: https://www.metasploit.com/
- Nmap: https://nmap.org/
- OWASP: https://owasp.org/

### Learning Resources
- OSCP Certification
- Hack The Box
- TryHackMe
- Security+ Certification

## ✅ Pull Request Checklist

Before submitting, ensure:

- [ ] Code follows style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] Commit messages are clear
- [ ] No merge conflicts
- [ ] Legal implications considered
- [ ] Tested on Raspberry Pi (if hardware-related)
- [ ] Plugin JSON validated (if plugin)
- [ ] Includes legal warnings where appropriate

## 🙏 Thank You!

Your contributions help make PenDonn better for the security community. Together, we can build better tools for ethical security testing.

**Remember: Always stay legal, stay ethical! 🔒**

---

## Questions?

Feel free to open an issue or contact the maintainers.

Happy (legal) hacking! 🚀
