import sys
import asyncio
import json
from typing import Optional, Any, Dict, List
from contextlib import AsyncExitStack
from pydantic import AnyUrl

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(
        self,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
    ):
        self._command = command
        self._args = args
        self._env = env
        self._session: Optional[ClientSession] = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()

    async def connect(self):
        """Establish connection with MCP server"""
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )

        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        _stdio, _write = stdio_transport

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(_stdio, _write)
        )

        await self._session.initialize()

    def session(self) -> ClientSession:
        """Return active session"""
        if self._session is None:
            raise ConnectionError(
                "Client session not initialized. Call connect() first."
            )
        return self._session

    async def list_tools(self) -> List[types.Tool]:
        """List available tools from MCP server"""
        result = await self.session().list_tools()
        return result.tools

    async def call_tool(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> Optional[types.CallToolResult]:
        """Call a tool on MCP server"""
        return await self.session().call_tool(tool_name, tool_input)

    async def list_prompts(self) -> List[types.Prompt]:
        """List available prompts (if supported by server)"""
        try:
            result = await self.session().list_prompts()
            return result.prompts
        except AttributeError:
            raise NotImplementedError("MCP server does not support prompts API")

    async def get_prompt(
        self, prompt_name: str, args: Dict[str, str]
    ) -> types.GetPromptResult:
        """Fetch a prompt from MCP server"""
        try:
            return await self.session().get_prompt(prompt_name, args)
        except AttributeError:
            raise NotImplementedError("MCP server does not support get_prompt")

    async def read_resource(self, uri: str) -> Any:
        """Read and parse resource from MCP server"""
        result = await self.session().read_resource(AnyUrl(uri))

        if not result.contents:
            return None

        resource = result.contents[0]

        if isinstance(resource, types.TextResourceContents):
            if resource.mime_type == "application/json":
                return json.loads(resource.text)
            return resource.text

        return resource

    async def cleanup(self):
        """Close connection and cleanup resources"""
        await self._exit_stack.aclose()
        self._session = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


# ------------------ TESTING ------------------ #

async def main():
    async with MCPClient(
        command="uv",  # change to "python" if not using uv
        args=["run", "mcp_server.py"],
    ) as client:

        print("\n🔧 Available Tools:")
        tools = await client.list_tools()
        for tool in tools:
            print(f"- {tool.name}")

        # Example: Call a tool (modify as per your server)
        # result = await client.call_tool("example_tool", {"input": "test"})
        # print("\n🛠 Tool Result:", result)

        # Example: Read resource
        # resource = await client.read_resource("file://example.json")
        # print("\n📄 Resource:", resource)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())