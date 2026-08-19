import asyncio
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from chemanim.mcp_server import build_command


def test_mcp_command_keeps_prompt_as_one_argument():
    prompt = '展示乙醇; Remove-Item "C:\\important"'
    command = build_command(prompt, "medium", "2d", False, "", 90)

    assert prompt in command
    assert command.count(prompt) == 1
    assert "--no-render" in command
    assert "--model" not in command


def test_mcp_stdio_exposes_generation_tool():
    async def discover():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "chemanim.mcp_server"],
        )
        async with Client(
            stdio_client(parameters), read_timeout_seconds=10
        ) as client:
            return await client.list_tools()

    result = asyncio.run(discover())
    tool = next(tool for tool in result.tools if tool.name == "generate_chemistry_animation")
    assert set(tool.input_schema["required"]) == {"prompt"}
