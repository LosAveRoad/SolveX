from typing import Dict, List, Optional

from pydantic import Field

from app.agent.toolcall import ToolCallAgent
from app.logger import logger
from app.prompt.modeling import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.arxiv_search import ArxivSearch
from app.tool.mermaid_diagram import MermaidDiagram
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor
from app.tool.tavily_search import TavilySearch
from app.tool.tavily_extract import TavilyExtract


class ModelingAgent(ToolCallAgent):
    """Mathematical modeling expert that searches literature and designs models."""

    name: str = "modeling"
    description: str = "Mathematical modeling expert: searches papers, analyzes problems, designs models"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 25

    available_tools: ToolCollection = ToolCollection(
        ArxivSearch(),
        MermaidDiagram(),
        TavilySearch(),
        TavilyExtract(),
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
