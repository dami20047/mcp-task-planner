"""
Standalone demo/verification client for the task-planner MCP server.

Chat clients like Claude Desktop typically only wire a server's *tools*
into the normal conversation flow -- resources and prompts are separate
MCP primitives that usually need a different UI affordance (an attach
picker, a slash command) rather than being callable from plain language.
So asking Claude Desktop "what are my pending tasks?" may not reach the
tasks://pending resource even though the resource works fine.

This script talks the MCP protocol directly, the same way Claude Desktop
does under the hood (spawning the server over stdio), and exercises all
three primitives -- resource, tool, prompt -- so you can see and
demonstrate that all three actually work, independent of any particular
chat client's UI support for resources/prompts.

Run with the task_service already running (see README):

    python demo_client.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


async def main() -> None:
    api_key = os.environ.get("TASK_SERVICE_API_KEY")
    if not api_key:
        print("TASK_SERVICE_API_KEY not set (check your .env). Aborting.")
        sys.exit(1)

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(PROJECT_ROOT / "mcp_server" / "server.py")],
        env={
            "TASK_SERVICE_API_KEY": api_key,
            "TASK_SERVICE_URL": os.environ.get("TASK_SERVICE_URL", "http://127.0.0.1:8000"),
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("== Server capabilities ==")
            tools = await session.list_tools()
            print("Tools:    ", [t.name for t in tools.tools])
            resources = await session.list_resources()
            print("Resources:", [str(r.uri) for r in resources.resources])
            prompts = await session.list_prompts()
            print("Prompts:  ", [p.name for p in prompts.prompts])

            print("\n== Calling the add_task TOOL ==")
            result = await session.call_tool(
                "add_task",
                {"title": "Demo client verification", "due_date": "2026-11-15", "priority": "medium"},
            )
            print(result.content[0].text if result.content else result)

            print("\n== Reading the tasks://pending RESOURCE ==")
            res = await session.read_resource("tasks://pending")
            print(res.contents[0].text)

            print("\n== Getting the plan_my_day PROMPT ==")
            prompt = await session.get_prompt("plan_my_day", {"focus_area": "coursework"})
            print(prompt.messages[0].content.text)

            print("\nAll three MCP primitives (resource, tool, prompt) confirmed working.")


if __name__ == "__main__":
    asyncio.run(main())
