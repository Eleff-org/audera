# Audera Agent Guidelines

## Build/Lint/Test Commands

### Building
- Install package: `pip install .`
- Install in development mode: `pip install -e .`

### Linting
- Run flake8: `flake8`
- Configuration: max-line-length = 129

### Testing
- Run test files: `python testing.py` or `python testing_2.py`
- No formal test framework configured (pytest/unittest not in requirements)

## Code Style Guidelines

### Imports
- Use absolute imports: `from audera import module`
- Group imports: standard library, third-party, local
- Use `from __future__ import annotations` for forward references

### Type Hints
- Use comprehensive type annotations
- Use `Literal` for constrained values: `Literal[1, 2]`
- Use `Union`/`Optional` for complex types
- Type hint all function parameters and return values

### Naming Conventions
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_CASE`
- Private members: `_leading_underscore`

### Documentation
- Use Google-style docstrings
- Document all classes, methods, and functions
- Include parameter descriptions with types
- Include return value descriptions

### Code Structure
- Use dataclasses for structured data: `@dataclass`
- Implement `from_dict()` and `to_dict()` methods for serialization
- Use `__post_init__()` for dataclass initialization logic
- Implement `__repr__()` with JSON formatting
- Implement `__eq__()` for comparison

### Error Handling
- Use specific exception types (TypeError, KeyError, ValueError)
- Provide descriptive error messages
- Validate input parameters

### Formatting
- Max line length: 129 characters
- Use 4 spaces for indentation
- Use single quotes for strings unless containing single quotes
- Use f-strings for string formatting

### Best Practices
- Use type checking with `isinstance()`
- Use list comprehensions for simple transformations
- Use context managers where appropriate
- Avoid global state when possible
- Use meaningful variable names
- Keep functions focused and single-purpose

## Orchestrator Usage
- **Import**: `from audera import orchestrator`
- **Purpose**: Isolate critical tasks from blocking the main event loop
- **Key Features**:
  - Thread/process pool execution
  - Automatic retry on failure
  - Configurable timeouts
  - Comprehensive logging
- **Usage Patterns**:
  - **Synchronous execution**:
    ```python
    orchestrator = audera.orchestrator.Orchestrator(logger=logger)
    result = orchestrator.run(
        task_id="unique_task_id",
        func=critical_function,
        restart_on_failure=True,
        timeout=30.0,
        pool_type="thread"
    )
    ```
  - **Asynchronous execution** (for coroutines):
    ```python
    result = await orchestrator.arun(
        task_id="unique_task_id",
        coro_func=async_critical_function,
        restart_on_failure=True,
        timeout=30.0,
        pool_type="thread"
    )
    ```
- **Integration**:
  - `streamer.py`: NTP synchronization, audio streaming, and timing-critical mDNS browsing with player synchronization (blocking I/O and precision timing)
  - `player.py`: Audio playback, timing-critical streamer synchronization, mDNS broadcasting, audio stream receiving, and deprecated shairport-sync service monitoring (blocking I/O, precision timing, network I/O, and subprocess management)