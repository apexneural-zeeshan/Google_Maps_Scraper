# Skill: Add Service

Step-by-step guide for adding a new data collection or processing service.

## Steps

### 1. Create Service Module

File: `backend/app/services/<service_name>.py`

```python
import logging
import httpx

logger = logging.getLogger(__name__)

async def fetch_data(...) -> list[dict]:
    """Fetch data from the external source.

    Args:
        ...

    Returns:
        List of raw result dicts.
    """
    async with httpx.AsyncClient() as client:
        # Implementation
        pass
```

### 2. Add Configuration

File: `backend/app/config.py`

- Add any new environment variables to `Settings`.
- Add rate limit configuration if the service has API limits.

File: `.env.example`

- Document the new environment variable with a placeholder.

### 3. Integrate into Pipeline

File: `backend/app/tasks/scrape.py`

- Import the new service function.
- Add it to the appropriate step in `run_scrape_job`.
- Update progress tracking to include the new step.

### 4. Update Deduplication (if adding a data source)

File: `backend/app/services/dedup.py`

- If the new service returns leads, ensure dedup handles its output.
- Merge fields from the new source into existing leads.

### 5. Add Tests

File: `backend/tests/test_<service_name>.py`

- Test with mocked HTTP responses.
- Test rate limiting behavior.
- Test error handling (timeouts, bad responses).

### 6. Respect Free Tier Limits

All external services have free-tier limits. When adding a new service:

- Track monthly usage with an in-memory counter (see `serp_api.py` or
  `outscraper_api.py` for the pattern).
- Add a `<service>_monthly_limit` setting to `config.py` with an env var.
- Log warnings when approaching the limit.
- Add a `skip_if_over_limit` parameter that gracefully returns empty results.
- Use environment variables for limits so they can be adjusted without code changes.

### 7. Update Documentation

- Update `docs/api-reference.md` if there are new parameters.
- Update `CLAUDE.md` data flow section.
- Update `README.md` architecture diagram if adding a new layer.
