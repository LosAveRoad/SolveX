from typing import Dict, List, Optional

from pydantic import Field

from app.agent.toolcall import ToolCallAgent
from app.config import config
from app.logger import logger
from app.prompt.modeling import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.arxiv_search import ArxivSearch
from app.tool.mcp import MCPClients, MCPClientTool
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


class ModelingAgent(ToolCallAgent):
    """Mathematical modeling expert that searches literature and designs models."""

    name: str = "modeling"
    description: str = "Mathematical modeling expert: searches papers, analyzes problems, designs models"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 15

    mcp_clients: MCPClients = Field(default_factory=MCPClients)

    available_tools: ToolCollection = ToolCollection(
        ArxivSearch(),
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )

    connected_servers: Dict[str, str] = Field(default_factory=dict)
    _initialized: bool = False

    async def _initialize_mcp(self) -> None:
        """Connect to configured MCP servers (Zhipu web search)."""
        if self._initialized:
            return
        self._initialized = True

        for server_id, server_config in config.mcp_config.servers.items():
            try:
                if server_config.type == "sse" and server_config.url:
                    await self.mcp_clients.connect_sse(server_config.url, server_id)
                    new_tools = [
                        t for t in self.mcp_clients.tools if t.server_id == server_id
                    ]
                    self.available_tools.add_tools(*new_tools)
                    self.connected_servers[server_id] = server_config.url
                    logger.info(f"Connected MCP: {server_id} ({len(new_tools)} tools)")
            except Exception as e:
                logger.warning(f"MCP {server_id} connection failed: {e}")

    async def think(self) -> bool:
        """Initialize MCP on first use, then think."""
        await self._initialize_mcp()
        return await super().think()

    async def cleanup(self):
        """Clean up MCP connections."""
        if self._initialized:
            await self.mcp_clients.disconnect()
            self._initialized = False
        await super().cleanup()
