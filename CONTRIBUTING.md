## Contributing to DevMemory

### Development setup

- Clone the repository and create a virtualenv.
- Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
- Start the local stack with `make up`.
- Install the package in editable mode with dev extras:

```bash
pip install -e .[dev]
```

### Running tests and linting

- Run tests with:

```bash
pytest
```

- Run Ruff linting (optional) with:

```bash
ruff check .
```

### Code style and guidelines

- Use type hints throughout new code.
- Keep dependencies minimal and aligned with existing stack (typer, httpx, rich).
- Follow the existing command structure:
  - CLI entry points in `devmemory/cli.py`.
  - Command implementations in `devmemory/commands/<name>.py` with `run_<name>()`.
  - Core logic in `devmemory/core/`.

### Proposing changes

- Open an issue describing the problem or feature.
- For pull requests:
  - Create a topic branch from `main`.
  - Add or update tests when changing behavior.
  - Ensure `pytest` passes locally.
  - Keep commits focused and descriptive.

