from pydantic import Field

from app.agent.toolcall import ToolCallAgent
from app.config import config
from app.prompt.writing import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import PaperSearch, Terminate, ToolCollection
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


def _writing_tools() -> ToolCollection:
    tools = [PythonExecute(), StrReplaceEditor()]
    if config.knowledge.enabled:
        tools.append(PaperSearch(default_top_k=config.knowledge.default_top_k))
    tools.append(Terminate())
    return ToolCollection(*tools)


class WritingAgent(ToolCallAgent):
    """Academic writing expert that composes LaTeX papers from modeling results."""

    name: str = "writing"
    description: str = "Academic writing expert: composes LaTeX papers from modeling and visualization results"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 40

    available_tools: ToolCollection = Field(default_factory=_writing_tools)
