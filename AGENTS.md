# AGENTS.md

## Environment

- Use `uv` for Python environment and dependency management.
- Inspect the existing environment before changing dependencies.
- Prefer the standard library and existing dependencies before adding new ones.
- Never commit secrets, `.env`, virtual environments, caches, or generated artifacts.

## Git

- Commit each logical change with a concise, meaningful commit message.
- Do not push, merge, tag, publish, or modify remotes unless explicitly requested.

## Python

- Use `snake_case` for variables, functions, methods, and modules; `PascalCase` for classes and exceptions; `UPPER_SNAKE_CASE` for constants.
- Add type hints to function parameters and return values.
- Prefer modern typing syntax such as `list[str]` and `T | None`; avoid `Any` unless necessary.
- Use `logging` instead of ad-hoc `print` calls in reusable code.

## Documentation

- Maintain a tracked `README_ZH.md` as the primary Chinese project guide.
- Write project documentation in Chinese unless another language is explicitly requested.
- Keep `README_ZH.md` focused on setup, configuration, usage, tests, and important architecture.
- Add Mermaid architecture or workflow diagrams only when they materially improve understanding.
