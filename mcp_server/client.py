"""
HTTP client the MCP server uses to call the task service.

Two things live here:

1. Authentication: every request carries the API key (from .env, never
   hardcoded) in the X-API-Key header.
2. Best Practice #2 -- Error Disclosure: `_safe_call` is the single choke
   point every backend call goes through. Whatever actually goes wrong
   (connection refused, a 500 with a raw SQLite error message, a timeout,
   an unexpected response shape), the real detail is logged to
   mcp_server.log on this machine only, and the caller (the MCP tool /
   resource function, and ultimately the LLM) gets back one of a small
   set of generic, safe messages. See exploits/test_error_disclosure.py.
"""

import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

LOG_PATH = Path(__file__).parent / "mcp_server.log"
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mcp_server.client")

TASK_SERVICE_URL = os.environ.get("TASK_SERVICE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("TASK_SERVICE_API_KEY")


class ServiceError(Exception):
    """Safe-to-display error raised for any task-service failure.

    The message on this exception is always generic. Callers (the MCP
    tool/resource functions in server.py) can surface str(exc) directly
    to the model/user without risking a leak.
    """


def _headers() -> dict:
    return {"X-API-Key": API_KEY or ""}


def _safe_call(description: str, fn):
    """Run `fn`, translating any failure into a generic ServiceError.

    `description` is a short, safe label (e.g. "fetch pending tasks") used
    only in the generic message -- never any part of the underlying
    exception, response body, or headers.
    """
    try:
        response = fn()
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        # This is exactly the case exploited in test_error_disclosure.py:
        # the task service's 500 response body can contain a raw SQLite
        # error message. We deliberately do NOT include exc.response.text
        # in anything returned to the caller -- only in the log.
        logger.error(
            "%s failed: HTTP %s from task service. Response body: %r",
            description,
            exc.response.status_code,
            exc.response.text,
        )
        if exc.response.status_code == 401:
            raise ServiceError("Not authorized to reach the task service.") from exc
        if exc.response.status_code == 409 or exc.response.status_code == 500:
            raise ServiceError(
                f"Could not {description} right now. The task may already "
                "exist, or the service hit an internal error."
            ) from exc
        raise ServiceError(f"Could not {description} (unexpected response).") from exc
    except httpx.RequestError as exc:
        # Connection refused, DNS failure, timeout, etc. -- never expose
        # the underlying URL, host, or socket error text to the caller.
        logger.error("%s failed: could not reach task service: %r", description, exc)
        raise ServiceError(
            f"Could not {description}: the task service is unreachable."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort catch-all
        logger.exception("%s failed with an unexpected error", description)
        raise ServiceError(f"Could not {description} due to an internal error.") from exc


def fetch_pending_tasks() -> list[dict]:
    return _safe_call(
        "fetch pending tasks",
        lambda: httpx.get(
            f"{TASK_SERVICE_URL}/tasks",
            params={"status": "pending"},
            headers=_headers(),
            timeout=5.0,
        ),
    )


def create_task(title: str, due_date: str, priority: str) -> dict:
    return _safe_call(
        "add task",
        lambda: httpx.post(
            f"{TASK_SERVICE_URL}/tasks",
            json={"title": title, "due_date": due_date, "priority": priority},
            headers=_headers(),
            timeout=5.0,
        ),
    )
