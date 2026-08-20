from __future__ import annotations

import asyncio

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions


server = Server("chemanim_probe")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="hello",
            description="Return a fixed response to verify MCP tool discovery and invocation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional name to include in the greeting.",
                        "default": "world",
                    }
                },
                "required": [],
            },
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    if name != "hello":
        raise ValueError(f"Invalid tool name: {name}")

    arguments = arguments or {}
    who = str(arguments.get("name", "world"))
    return [
        types.TextContent(
            type="text",
            text=(
                '{"status":"ok",'
                f'"message":"hello {who}",'
                '"build_id":"chemanim-probe-mcp15-v1"}'
            ),
        )
    ]


async def run_server() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="chemanim_probe",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
