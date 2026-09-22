"""
Personal Productivity MCP server: a daily task planner.

Domain: Personal Productivity (task tracking + daily planning).
Structure: one resource + one tool + one prompt, per the assignment.

- Resource `tasks://pending`  -- read-only context: the caller's current
  pending tasks, pulled from the task service.
- Tool `add_task`             -- the one write action: create a new task.
  Input is sanitized (mcp_server/validation.py) before it is ever sent to
  the task service.
- Prompt `plan_my_day`        -- a reusable prompt template that tells the
  model to read the tasks:// resource and produce a prioritized plan.

Authentication: this server authenticates to the task service with an API
key (mcp_server/client.py reads TASK_SERVICE_API_KEY from .env). It does
not itself require the *MCP client* (Claude Desktop) to authenticate --
Claude Desktop launches this server as a local subprocess over stdio, which
is the standard trust boundary for local MCP servers (see README).

Portions of this file's structure (FastMCP decorator usage for resources /
tools / prompts) follow the patterns shown in the MCP Python SDK README:
https://github.com/modelcontextprotocol/python-sdk
"""

import json
import sys
from pathlib import Path

# Claude Desktop launches this file directly as a script (see
# claude_desktop_config.json), which puts mcp_server/ itself on sys.path
# rather than the project root -- so `from mcp_server import client` would
# fail. Make sure the project root is importable regardless of how this
# file is invoked (as a script, or with `python -m mcp_server.server`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from mcp_server import client
from mcp_server.validation import (
    ValidationError,
    validate_due_date,
    validate_priority,
    validate_title,
)

mcp = FastMCP(
    name="task-planner",
    instructions=(
        "Tools for tracking personal tasks and planning the day. "
        "Read the tasks://pending resource to see what's outstanding, "
        "use add_task to create new tasks, and use the plan_my_day "
        "prompt to get a structured daily plan."
    ),
)


@mcp.resource("tasks://pending")
def pending_tasks() -> str:
    """The caller's current pending tasks, as JSON.

    Read-only: this resource never modifies state. It calls the task
    service's GET /tasks endpoint (authenticated with the API key) and
    returns the result as a JSON string for the model to read as context.
    """
    try:
        tasks = client.fetch_pending_tasks()
    except client.ServiceError as exc:
        # Error Disclosure best practice: exc's message is already the
        # generic, safe form -- see mcp_server/client.py.
        return json.dumps({"error": str(exc)})
    return json.dumps(tasks, indent=2)


@mcp.tool()
def add_task(title: str, due_date: str, priority: str) -> dict:
    """Add a new task to the task tracker.

    Args:
        title: Short description of the task (plain text; letters, numbers,
            spaces, and basic punctuation only).
        due_date: Date the task is due, in YYYY-MM-DD format. Must not be
            in the past.
        priority: One of "low", "medium", or "high".

    Returns:
        The created task on success, or {"error": "<safe message>"} if the
        input was rejected or the task service call failed.
    """
    # Input Sanitization best practice: every field is validated against
    # an allow-list before it leaves this process. See
    # mcp_server/validation.py and exploits/test_input_sanitization.py.
    try:
        title = validate_title(title)
        due_date = validate_due_date(due_date)
        priority = validate_priority(priority)
    except ValidationError as exc:
        return {"error": str(exc)}

    try:
        return client.create_task(title=title, due_date=due_date, priority=priority)
    except client.ServiceError as exc:
        # Error Disclosure best practice: exc's message is already the
        # generic, safe form -- see mcp_server/client.py.
        return {"error": str(exc)}


@mcp.prompt()
def plan_my_day(focus_area: str = "") -> str:
    """Build a prompt asking the model to turn pending tasks into a plan.

    Args:
        focus_area: Optional area to weight the plan toward, e.g. "MAE
            coursework" or "job applications". Leave blank for a general
            plan.
    """
    focus_line = (
        f"Weight the plan toward this focus area if possible: {focus_area}.\n"
        if focus_area
        else ""
    )
    return (
        "Read the tasks://pending resource to see my current pending "
        "tasks. Then produce a prioritized plan for today: group tasks "
        "into Now / Later / Can Wait, call out anything overdue or due "
        "today, and keep the whole plan to a few short bullet points. "
        f"{focus_line}"
        "If a task's priority and its due date disagree (e.g. a "
        "low-priority task due today), flag that instead of silently "
        "picking one."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
