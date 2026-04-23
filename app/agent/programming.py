from app.agent.toolcall import ToolCallAgent
from app.prompt.programming import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


class ProgrammingAgent(ToolCallAgent):
    """编程专家Agent，负责根据建模方案编写代码并验证结果"""

    name: str = "programming"
    description: str = "编程专家，负责根据数学模型编写Python代码、执行并验证结果"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 30

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
