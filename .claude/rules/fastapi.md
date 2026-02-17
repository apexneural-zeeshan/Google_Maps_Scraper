# FastAPI Rules

## Route Structure

- Group routes by resource in separate files under `app/api/`.
- Use `APIRouter` with a prefix and tags for each resource.
- Register all routers in `app/main.py`.
- Keep route handlers thin — delegate logic to service functions.

## Dependencies

- Use `Depends()` for shared dependencies (DB session, auth, pagination).
- Define `get_db` in `app/db/session.py` as an async generator.
- Use path parameters for resource IDs: `/jobs/{job_id}`.
- Use query parameters for filtering, sorting, pagination.

## Schemas

- Define all request/response schemas in `app/schemas.py`.
- Use `model_config = ConfigDict(from_attributes=True)` for ORM mapping.
- Input schemas: only include fields the client sends.
- Output schemas: include all fields the client needs.
- Use `Annotated` types for common query parameter patterns.

## Error Responses

- 400: Invalid request body or parameters.
- 404: Resource not found.
- 409: Conflict (e.g., job already cancelled).
- 422: Validation error (auto-handled by FastAPI).
- 500: Unexpected server error.
- Always return a JSON body with `{"detail": "message"}`.

## Pagination

- Use `skip` (offset) and `limit` query parameters.
- Default: `skip=0`, `limit=50`, max `limit=200`.
- Return total count in list responses for frontend pagination.

## OpenAPI

- Add `summary` and `description` to route decorators.
- Use `response_model` on all endpoints.
- Tag routes for grouping in Swagger UI.
