from __future__ import annotations

from mcp.server import MCPServer


mcp = MCPServer(
    "ChemAnimProbe",
    instructions="Minimal MCP probe used to verify hosted tool discovery.",
)


@mcp.tool()
def hello(name: str = "world") -> dict[str, str]:
    """Return a fixed response to verify MCP tool discovery and invocation."""
    return {
        "status": "ok",
        "message": f"hello {name}",
        "build_id": "chemanim-isolated-probe-v1",
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
