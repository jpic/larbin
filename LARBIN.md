# Project Guidelines

## Code Style

### Python (.py)

#### Formatting
- **Indentation**: 4 spaces
- **Line length**: 79 characters (PEP 8)
- **Blank lines**:
  - 2 around top-level functions/classes
  - 1 around methods
- **Imports**:
  - Grouped (standard, third-party, local)
  - Each on separate lines

#### Naming Conventions
- **Variables/functions**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Classes**: `PascalCase`
- **Private members**: `_leading_underscore`

#### Language-Specific Practices
- Use list comprehensions where readable
- Prefer `with` for file operations
- Avoid mutable default arguments

#### Tools
- **Linter**: flake8
- **Formatter**: ruff
- **Type checker**: mypy (optional)

#### Comment/Documentation Standards
- **Docstrings**: Google or NumPy style
- **Inline comments**: `#` with space, explain why not what
- Module docstring at top

#### File Structure
1. Shebang (`#!`) only if executable
2. Imports
3. Constants
4. Functions/classes
5. `if __name__ == "__main__":` guard at bottom

## Testing

```python
# Python .py
python -m pytest -v -l --showlocals --tb=long
```

## Documentation

```bash
sphinx-build -b html docs docs/_build/html -v
```
