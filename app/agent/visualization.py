from app.agent.toolcall import ToolCallAgent
from app.prompt.visualization import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


class VisualizationAgent(ToolCallAgent):
    """Data visualization expert that creates publication-quality figures."""

    name: str = "visualization"
    description: str = "Data visualization expert: creates figures and visual analysis from modeling results"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 15

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
