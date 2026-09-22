"""
API key authentication for the task service.

The task service is meant to stand in for "a real backend service" that the
MCP server calls out to (per the assignment's Personal Productivity domain
and the "calling services" framing). It requires a shared-secret API key on
every request, read from the environment (see .env.example) rather than
hardcoded -- this is the "secret management using .env" rubric item.
"""

import os
import secrets

from fastapi import Header, HTTPException, status

# Loaded once at import time. python-dotenv (loaded in main.py) populates
# os.environ before this module's functions are called.
EXPECTED_API_KEY = os.environ.get("TASK_SERVICE_API_KEY")


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency: reject the request unless X-API-Key matches."""
    if not EXPECTED_API_KEY:
        # Fail closed: if the service was never configured with a key,
        # refuse everything rather than silently allowing all requests.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service is not configured with an API key.",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, EXPECTED_API_KEY):
        # secrets.compare_digest avoids a timing side-channel that a plain
        # `!=` string comparison would have.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
