# Python Coding Rules

## Async/Await

- Use `async def` for all I/O-bound functions (DB queries, HTTP calls, file I/O).
- Use `await` when calling async functions — never call them synchronously.
- Use `httpx.AsyncClient` for HTTP requests, not `requests`.
- Use `asyncpg` via SQLAlchemy async engine for database operations.

## Type Hints

- All function parameters and return types must have type annotations.
- Use `str | None` instead of `Optional[str]` (Python 3.10+ union syntax).
- Use `list[str]` instead of `List[str]` (lowercase generics).
- Import complex types from `typing` only when necessary (e.g., `TypeVar`).

## Data Structures

- Use Pydantic `BaseModel` for API request/response schemas.
- Use `dataclasses` for internal data transfer objects not exposed via API.
- Use SQLAlchemy `DeclarativeBase` models for database entities.

## Error Handling

- Raise `HTTPException` with appropriate status codes in API routes.
- Use custom exception classes for service-layer errors.
- Never catch bare `Exception` — catch specific exceptions.
- Log exceptions with `logger.exception()` to preserve tracebacks.

## Logging

- Use `logging.getLogger(__name__)` at module level.
- Log at appropriate levels: `debug` for verbose, `info` for operations,
  `warning` for recoverable issues, `error` for failures.
- Include structured context in log messages (job_id, place_id, etc.).

## Playwright

- This project uses Playwright async API — always use
  `async with async_playwright() as p:` pattern.
- Nominatim requires 1-second delay between requests — always use
  `await asyncio.sleep(1.0)` before each Nominatim call.
- All external services have free-tier limits. Track monthly usage in
  each service module and respect the configured limits.

## Naming

- `snake_case` for functions, variables, module names.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for constants.
- Prefix private methods/attributes with `_`.
- Use descriptive names — avoid single-letter variables except in comprehensions.
