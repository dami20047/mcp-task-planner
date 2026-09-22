"""
task_service: the "real world service" that the MCP server calls.

Stands in for something like an internal team task tracker. It is
deliberately a *separate* HTTP service (not just an in-process function)
because the assignment is about an MCP server that calls services -- this
is the service, and mcp_server/ is the MCP-facing client of it.

IMPORTANT (see README "Design notes"): this service intentionally does NOT
implement the "avoid leaking sensitive information in error messages" best
practice itself -- on an unexpected error it returns the raw exception
message (line 70-ish, `detail=str(exc)`). That's realistic: plenty of
internal/legacy services do this. The best practice is implemented at the
MCP server boundary instead (mcp_server/client.py), which is the layer
this assignment actually asks us to build and secure. exploits/
test_error_disclosure.py demonstrates both halves: the raw leak from this
service, and the MCP layer catching and sanitizing it before it reaches
the model/user.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from task_service import db
from task_service.auth import require_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("task_service")

app = FastAPI(title="Task Service", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_date: str
    priority: str


@app.get("/tasks", dependencies=[Depends(require_api_key)])
def get_tasks(status: str = Query(default="pending")) -> list[dict]:
    return db.list_tasks(status=status)


@app.post("/tasks", dependencies=[Depends(require_api_key)], status_code=201)
def create_task(payload: TaskCreateRequest) -> dict:
    try:
        return db.insert_task(
            title=payload.title,
            due_date=payload.due_date,
            priority=payload.priority,
        )
    except Exception as exc:
        # Deliberately naive: logs AND re-raises the raw exception text.
        # See module docstring -- this is the "unsafe" layer that the MCP
        # server's error handling (mcp_server/client.py) is responsible
        # for not passing along verbatim.
        logger.exception("create_task failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
