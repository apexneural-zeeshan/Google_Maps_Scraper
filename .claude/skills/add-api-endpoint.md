# Skill: Add API Endpoint

Step-by-step guide for adding a new API endpoint to the backend.

## Steps

### 1. Define Schemas

File: `backend/app/schemas.py`

- Add request schema (e.g., `ThingCreate`) with input fields.
- Add response schema (e.g., `ThingResponse`) with `model_config = ConfigDict(from_attributes=True)`.
- Add list response schema if the endpoint returns collections.

### 2. Create Route Handler

File: `backend/app/api/<resource>.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas import ThingCreate, ThingResponse

router = APIRouter(prefix="/api/<resource>", tags=["<resource>"])

@router.post("/", response_model=ThingResponse, status_code=201)
async def create_thing(
    payload: ThingCreate,
    db: AsyncSession = Depends(get_db),
):
    # Implementation here
    pass
```

### 3. Register Router

File: `backend/app/main.py`

```python
from app.api.<resource> import router as <resource>_router
app.include_router(<resource>_router)
```

### 4. Add Frontend API Function

File: `frontend/src/lib/api.ts`

- Add TypeScript interface matching the response schema.
- Add fetch function for the new endpoint.

### 5. Create/Update Frontend Component

File: `frontend/src/components/<Component>.tsx`

- Use the new API function.
- Handle loading, error, and success states.

### 6. Write Tests

File: `backend/tests/test_<resource>.py`

- Test success cases with valid input.
- Test validation errors with invalid input.
- Test 404 for missing resources.
