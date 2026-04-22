from app.agent.toolcall import ToolCallAgent
from app.prompt.writing import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


class WritingAgent(ToolCallAgent):
    """Academic writing expert that composes LaTeX papers from modeling results."""

    name: str = "writing"
    description: str = "Academic writing expert: composes LaTeX papers from modeling and visualization results"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 20

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
