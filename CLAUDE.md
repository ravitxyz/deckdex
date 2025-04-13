# DeckDex Development Guide

## Build & Test Commands
```bash
# Install dev dependencies
python -m pip install -e ".[test]"

# Run all tests
pytest

# Run a single test
pytest src/deckdex/tests/path/to/test_file.py::TestClass::test_method

# Run with markers
pytest -m "slow" # or "integration"

# Code quality
black src/
ruff src/
mypy src/
```

## Code Style Guidelines
- **Types:** Use type hints everywhere; follow Python 3.9+ syntax `list[str]` vs `List[str]`
- **Classes:** Use dataclasses for models
- **Async:** Prefer asyncio for I/O operations; implement context managers with `__aenter__/__aexit__`
- **Error handling:** Use custom exception types; catch specific exceptions
- **Imports:** Group imports by standard lib, third-party, and local; sort alphabetically
- **Naming:** snake_case for methods/variables, PascalCase for classes
- **Documentation:** Docstrings should use triple double-quotes
- **Testing:** Use pytest fixtures; mock external dependencies; test edge cases

Developed by Claude for the DeckDex project.