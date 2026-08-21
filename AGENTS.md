# AGENTS.md

Repo-wide commands, the architecture-decision workflow, and code style. Tree-specific conventions live in their own files: back-end package conventions in `audera/AGENTS.md`, UI conventions in `audera/ui/AGENTS.md`, visual conventions in `brand/AGENTS.md`, the public site in `website/AGENTS.md`, tests in `tests/AGENTS.md`, and the device image in `os/dietpi/AGENTS.md`.

## Commands

```bash
uv sync --all-extras        # install all dependencies including dev
uv run ruff check --fix     # lint (max-line-length = 129)
uv run ruff format          # format
uv run ty check             # type check
uv run python testing.py    # run ad-hoc tests (no formal test framework)
uv run pytest tests/dal/ -v                          # DAL tests (no Docker required)
uv run pytest tests/clients/test_snapserver.py -v   # requires Docker
uv run pytest tests/clients/ -v                      # all client tests
uv run pytest -v                                     # everything except the systemd lane
uv run pytest -m systemd -v                          # real systemd in a privileged container (requires Docker)
pre-commit install          # install git hooks (run once after clone)
pre-commit run --all-files  # run all hooks manually
```

Install as a tool directly from GitHub:
```bash
uv tool install git+https://github.com/Eleff-org/audera.git
```

## Package layout

List @audera/ for the Python package layout.

## Architecture decisions

ADRs in `docs/adrs/` are human decision records. Read and follow the relevant ADR when working on code it covers. List @docs/adrs/ for the catalog.

## Code style

- Type-hint all parameters and return values; use `Literal` for constrained string values
- Google-style docstrings
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants, `_leading_underscore` private
- Single quotes unless the string contains a single quote; f-strings for formatting
- 4-space indentation, 129-character line limit

## Conventions

- Follow simplicity as a design goal, e.g. "the least buggy code is the code never written"
- Work in comprehensive increments that incl. code, tests and docs changes in a single commit