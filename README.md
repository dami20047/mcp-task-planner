# task-planner MCP server

A Model Context Protocol (MCP) server for the Personal Productivity domain:
track tasks and get help planning the day, from Claude Desktop.

Built for Cornell [course] Assignment 4: Calling Services / MCP.

## What this is

Two Python processes running on your machine:

1. **`task_service/`** — a small FastAPI REST API backed by SQLite. This
   stands in for "a real backend service" (think: an internal team task
   tracker). It requires an API key on every request.
2. **`mcp_server/`** — the actual MCP server, built with the [MCP Python
   SDK](https://github.com/modelcontextprotocol/python-sdk). This is what
   Claude Desktop talks to. It calls `task_service` on your behalf,
   authenticating with the API key.

Claude Desktop launches `mcp_server/server.py` as a local subprocess over
stdio (the standard way local MCP servers work) — it does **not** launch
`task_service`, so you start that one yourself before opening Claude
Desktop.

```
Claude Desktop  <--stdio (MCP)-->  mcp_server/server.py  <--HTTP + API key-->  task_service (:8000)  <-->  tasks.db
```

See `diagrams/architecture.png` for the full picture, including where the
two best-practice safeguards sit.

## MCP primitives implemented

| Type | Name | What it does |
|---|---|---|
| Resource | `tasks://pending` | Read-only: current pending tasks, as JSON |
| Tool | `add_task(title, due_date, priority)` | Creates a new task |
| Prompt | `plan_my_day(focus_area?)` | Prompt template that asks the model to read the resource and produce a prioritized daily plan |

## Best practices implemented

### 1. Input Sanitization (`mcp_server/validation.py`)

`add_task`'s three fields are each checked against an **allow-list** before
anything is sent to `task_service`:

- `title` — letters, numbers, spaces, and a small set of punctuation only
  (`.,!?():/_-`). This excludes the characters that do the work in SQL
  injection (`'`, `;`, `--`) and command injection (`` ` ``, `$()`, `|`,
  `&&`) payloads.
- `due_date` — must match `YYYY-MM-DD` and be a real, non-past calendar
  date.
- `priority` — must be exactly `low`, `medium`, or `high`.

`task_service`'s own database layer (`task_service/db.py`) also uses
parameterized SQL queries, so there are two independent layers of defense —
but the exploit test targets the MCP boundary specifically, since that's
the layer this assignment is about.

**Exploit test:** `exploits/test_input_sanitization.py` fires SQL-injection
and command-injection payloads (`'; DROP TABLE tasks; --`, `` `whoami` ``,
etc.) at the validation layer directly, at the real `add_task` tool
function, and then confirms against the live service that no injected row
was ever created.

### 2. Error Disclosure (`mcp_server/client.py`)

`task_service` is deliberately **not** hardened against leaking internal
error detail — on an unexpected error (e.g. a duplicate task, which trips
a `UNIQUE(title, due_date)` constraint) it returns the raw exception text,
e.g.:

```json
{"detail": "UNIQUE constraint failed: tasks.title, tasks.due_date"}
```

That's realistic: plenty of internal services behave this way. The
safeguard lives one layer up, at the MCP boundary: every call from
`mcp_server` to `task_service` goes through `client._safe_call()`, which
catches *any* failure (HTTP error, connection refused, timeout, unexpected
response) and returns one of a small set of generic messages to the
caller — the full detail (including the raw response body) is written only
to `mcp_server/mcp_server.log` on this machine, never returned to the
model or the client.

**Exploit test:** `exploits/test_error_disclosure.py` calls `task_service`
directly to force and confirm the raw leak, then makes the equivalent call
through the real `add_task` tool and confirms none of the leaked text
(table name, column names, `sqlite3`) appears in the result — only in the
log file.

## Authentication

`task_service` requires an `X-API-Key` header on every request, compared
with `secrets.compare_digest` (constant-time, to avoid a timing
side-channel). The key lives in `.env` (gitignored — see `.env.example`)
and `mcp_server` reads the same key from its own environment to
authenticate its calls. If the key is missing or wrong, `task_service`
returns `401` and `mcp_server`'s error-disclosure safeguard turns that into
a generic "not authorized" message rather than echoing anything about the
key itself.

This is a local dev setup, so Claude Desktop itself doesn't need to
authenticate to `mcp_server` — it launches it as a subprocess it already
trusts (the standard local-MCP-server trust model). The API key protects
the boundary that actually crosses a network hop: `mcp_server` → `task_service`.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# from the project root
uv venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

uv pip install -r requirements.txt

cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# paste the output into .env as TASK_SERVICE_API_KEY
```

### Run the task service

In one terminal, with the venv active:

```bash
uvicorn task_service.main:app --port 8000
```

Leave this running. Verify it's up: `curl http://127.0.0.1:8000/health`
should return `{"status":"ok"}`.

### Run the MCP server standalone (sanity check)

In a second terminal, with the venv active:

```bash
python mcp_server/server.py
```

It should sit waiting on stdio with no errors. Ctrl+C to stop — Claude
Desktop will launch it itself for the real demo (next step).

### Connect Claude Desktop

Open Claude Desktop's MCP config file (Settings → Developer → Edit Config,
or directly at `%APPDATA%\Claude\claude_desktop_config.json` on Windows /
`~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS) and merge in the contents of `claude_desktop_config.json` from this
repo, replacing the placeholder paths with the absolute path to this
project on your machine and the same API key you put in `.env`.

Restart Claude Desktop. With `task_service` still running in its terminal,
you should see `task-planner` listed under available MCP tools, and can
ask Claude things like "what are my pending tasks?" or "add a task to
finish the MCP assignment, due tomorrow, high priority" or "help me plan
my day."

### Run the exploit tests

With `task_service` running:

```bash
python -m exploits.test_input_sanitization
python -m exploits.test_error_disclosure
```

Both print what they're doing step by step and exit `0` if every exploit
was blocked (non-zero otherwise).

## Code citations

- FastMCP decorator usage (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`,
  `mcp.run(transport="stdio")`) in `mcp_server/server.py` follows the
  patterns shown in the MCP Python SDK README:
  https://github.com/modelcontextprotocol/python-sdk
- `secrets.compare_digest` for constant-time API key comparison
  (`task_service/auth.py`) follows the recommendation in the Python stdlib
  docs: https://docs.python.org/3/library/secrets.html#secrets.compare_digest
- All other code (FastAPI routes, SQLite access, validation logic, HTTP
  client wrapper, exploit scripts) was written for this assignment.

## Project layout

```
mcp-task-planner/
├── task_service/         # the backend service being called
│   ├── main.py            # FastAPI app, /tasks endpoints
│   ├── db.py               # SQLite storage, parameterized queries
│   └── auth.py              # API key check
├── mcp_server/            # the MCP server (the actual deliverable)
│   ├── server.py            # resource + tool + prompt definitions
│   ├── client.py             # authenticated HTTP client + error disclosure safeguard
│   └── validation.py         # input sanitization
├── exploits/               # exploit tests for both best practices
├── diagrams/                # architecture diagram (source + rendered PNG)
├── claude_desktop_config.json
├── requirements.txt
└── .env.example
```
