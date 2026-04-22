# SolveX Phase 1: Modeling + Programming Agent Loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a ModelingAgent and ProgrammingAgent connected by a loop-capable flow, testable with simple math problems.

**Architecture:** Create two specialized `ToolCallAgent` subclasses (ModelingAgent, ProgrammingAgent) with domain-specific prompts. A new `SolveXFlow` (extends `BaseFlow`) manages the modeling→programming loop with configurable max iterations and satisfaction-based exit.

**Tech Stack:** Python, Pydantic, OpenAI SDK (ChatGLM API), existing OpenManus tool framework

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/prompt/modeling.py` | ModelingAgent system + next-step prompts |
| Create | `app/prompt/programming.py` | ProgrammingAgent system + next-step prompts |
| Create | `app/agent/modeling.py` | ModelingAgent class |
| Create | `app/agent/programming.py` | ProgrammingAgent class |
| Create | `app/flow/solvex_flow.py` | SolveXFlow with modeling↔programming loop |
| Modify | `app/flow/flow_factory.py` | Add SOLVEX flow type |
| Modify | `run_flow.py` | Wire up ModelingAgent + ProgrammingAgent + SolveXFlow |
| Create | `tests/test_phase1.py` | Integration test with simple linear programming problem |

---

### Task 1: Modeling Agent Prompts

**Files:**
- Create: `app/prompt/modeling.py`

- [ ] **Step 1: Create the modeling prompt file**

```python
SYSTEM_PROMPT = """你是一位专业的数学建模专家。你的任务是分析问题，选择合适的数学建模方法，并输出结构化的建模方案。

你的职责：
1. 仔细阅读题目，提取关键信息和约束条件
2. 选择最适合的数学建模方法（如线性规划、回归分析、微分方程、优化模型等）
3. 明确定义变量、参数、目标函数和约束条件
4. 给出模型的求解思路和步骤

输出格式要求：
你的建模方案必须包含以下部分，用明确的标题分隔：

## 模型选择
（说明选择的方法及理由）

## 变量定义
（列出所有决策变量、参数、常量的符号和含义）

## 数学模型
（目标函数和约束条件的数学表达式）

## 求解思路
（说明如何求解这个模型，包括可能使用的算法和工具）

## 备注
（对模型的适用性、局限性进行说明）

注意事项：
- 使用清晰的数学符号和公式
- 确保建模方案可以被编程Agent直接理解和实现
- 如果之前的方案有问题，根据反馈进行调整和改进
"""

NEXT_STEP_PROMPT = """请根据当前任务完成数学建模。如果需要调整之前的模型方案，请根据反馈信息进行修改。完成后使用 `terminate` 工具结束。
"""
```

- [ ] **Step 2: Verify file created**

Run: `python -c "from app.prompt.modeling import SYSTEM_PROMPT, NEXT_STEP_PROMPT; print('OK:', len(SYSTEM_PROMPT), 'chars')"`
Expected: `OK: <some number> chars`

---

### Task 2: Programming Agent Prompts

**Files:**
- Create: `app/prompt/programming.py`

- [ ] **Step 1: Create the programming prompt file**

```python
SYSTEM_PROMPT = """你是一位专业的数值计算和编程专家。你的任务是根据建模专家提供的数学模型方案，编写Python代码实现求解，并验证结果的正确性。

你的职责：
1. 仔细阅读建模方案，理解数学模型
2. 编写Python代码实现模型的求解
3. 运行代码并验证结果
4. 如果结果不正确或有问题，给出反馈

输出要求：
- 使用 python_execute 工具执行代码
- 代码必须包含清晰的注释
- 打印出关键的中间结果和最终结果
- 如果使用第三方库，优先使用 numpy、scipy、pandas、matplotlib 等常用库

验证要求：
执行完代码后，你必须在输出中明确标注验证结果：
- 如果结果正确合理，在最后输出: VERIFICATION_RESULT: SATISFIED
- 如果结果有问题需要调整模型，在最后输出: VERIFICATION_RESULT: NEEDS_REVISION
- 并说明需要调整的原因

注意事项：
- 确保代码可以直接运行，不缺少依赖
- 处理可能的数值精度问题
- 对结果进行合理性检查
"""

NEXT_STEP_PROMPT = """请根据建模方案编写并执行Python代码。完成后使用 `terminate` 工具结束。记得在最后标注验证结果：VERIFICATION_RESULT: SATISFIED 或 VERIFICATION_RESULT: NEEDS_REVISION。
"""
```

- [ ] **Step 2: Verify file created**

Run: `python -c "from app.prompt.programming import SYSTEM_PROMPT, NEXT_STEP_PROMPT; print('OK:', len(SYSTEM_PROMPT), 'chars')"`
Expected: `OK: <some number> chars`

---

### Task 3: Modeling Agent

**Files:**
- Create: `app/agent/modeling.py`

- [ ] **Step 1: Create the ModelingAgent class**

```python
from app.agent.toolcall import ToolCallAgent
from app.prompt.modeling import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.python_execute import PythonExecute


class ModelingAgent(ToolCallAgent):
    """数学建模专家Agent，负责分析问题并输出结构化建模方案"""

    name: str = "modeling"
    description: str = "数学建模专家，负责分析问题、选择建模方法、定义数学模型"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 10

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        Terminate(),
    )
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.agent.modeling import ModelingAgent; print('OK')"`
Expected: `OK`

---

### Task 4: Programming Agent

**Files:**
- Create: `app/agent/programming.py`

- [ ] **Step 1: Create the ProgrammingAgent class**

```python
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

    max_steps: int = 15

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.agent.programming import ProgrammingAgent; print('OK')"`
Expected: `OK`

---

### Task 5: SolveX Flow with Loop

**Files:**
- Create: `app/flow/solvex_flow.py`

- [ ] **Step 1: Create the SolveXFlow class**

```python
from typing import Union

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow
from app.logger import logger


class SolveXFlow(BaseFlow):
    """SolveX数学建模工作流，支持建模Agent和编程Agent之间的循环迭代"""

    max_iterations: int = 5

    def __init__(
        self,
        agents: Union[BaseAgent, list, dict],
        max_iterations: int = 5,
        **data,
    ):
        data["max_iterations"] = max_iterations
        super().__init__(agents, **data)

    async def execute(self, input_text: str) -> str:
        """执行建模-编程循环工作流"""
        modeling_agent = self.agents.get("modeling")
        programming_agent = self.agents.get("programming")

        if not modeling_agent or not programming_agent:
            raise ValueError("SolveXFlow requires 'modeling' and 'programming' agents")

        logger.info(f"=== SolveX 开始处理任务 ===")
        logger.info(f"最大迭代次数: {self.max_iterations}")

        modeling_output = ""
        programming_output = ""
        satisfied = False

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"=== 第 {iteration}/{self.max_iterations} 轮迭代 ===")
            logger.info(f"{'='*50}\n")

            # Step 1: 建模Agent分析问题并输出方案
            logger.info(f"--- [ModelingAgent] 开始建模 ---")

            if iteration == 1:
                modeling_prompt = input_text
            else:
                modeling_prompt = (
                    f"之前的建模方案：\n{modeling_output}\n\n"
                    f"编程Agent的反馈：\n{programming_output}\n\n"
                    f"请根据反馈调整建模方案。"
                )

            modeling_agent.state = modeling_agent.state.__class__.IDLE
            modeling_agent.current_step = 0
            modeling_agent.memory = modeling_agent.memory.__class__()
            modeling_output = await modeling_agent.run(modeling_prompt)

            logger.info(f"--- [ModelingAgent] 建模完成 ---\n")

            # Step 2: 编程Agent实现并验证
            logger.info(f"--- [ProgrammingAgent] 开始编程实现 ---")

            programming_prompt = (
                f"原始问题：\n{input_text}\n\n"
                f"建模方案：\n{modeling_output}\n\n"
                f"请根据以上建模方案编写Python代码求解，并验证结果。"
            )

            programming_agent.state = programming_agent.state.__class__.IDLE
            programming_agent.current_step = 0
            programming_agent.memory = programming_agent.memory.__class__()
            programming_output = await programming_agent.run(programming_prompt)

            logger.info(f"--- [ProgrammingAgent] 编程完成 ---\n")

            # Step 3: 检查验证结果
            if "VERIFICATION_RESULT: SATISFIED" in programming_output:
                satisfied = True
                logger.info(f"=== 第 {iteration} 轮迭代：验证通过！ ===")
                break
            else:
                logger.info(f"=== 第 {iteration} 轮迭代：需要修订模型 ===")

        # 汇总结果
        if satisfied:
            result = f"建模-编程循环完成（共 {iteration} 轮迭代）\n\n"
        else:
            result = f"达到最大迭代次数 ({self.max_iterations})，使用当前最佳结果\n\n"

        result += f"=== 最终结果 ===\n\n{programming_output}"

        logger.info(f"=== SolveX 任务完成 ===")
        return result
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.flow.solvex_flow import SolveXFlow; print('OK')"`
Expected: `OK`

---

### Task 6: Update FlowFactory

**Files:**
- Modify: `app/flow/flow_factory.py`

- [ ] **Step 1: Add SOLVEX flow type**

Replace the entire content of `app/flow/flow_factory.py`:

```python
from enum import Enum
from typing import Dict, List, Union

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow
from app.flow.planning import PlanningFlow
from app.flow.solvex_flow import SolveXFlow


class FlowType(str, Enum):
    PLANNING = "planning"
    SOLVEX = "solvex"


class FlowFactory:
    """Factory for creating different types of flows with support for multiple agents"""

    @staticmethod
    def create_flow(
        flow_type: FlowType,
        agents: Union[BaseAgent, List[BaseAgent], Dict[str, BaseAgent]],
        **kwargs,
    ) -> BaseFlow:
        flows = {
            FlowType.PLANNING: PlanningFlow,
            FlowType.SOLVEX: SolveXFlow,
        }

        flow_class = flows.get(flow_type)
        if not flow_class:
            raise ValueError(f"Unknown flow type: {flow_type}")

        return flow_class(agents, **kwargs)
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.flow.flow_factory import FlowFactory, FlowType; print('OK:', FlowType.SOLVEX)"`
Expected: `OK: FlowType.SOLVEX`

---

### Task 7: Update run_flow.py Entry Point

**Files:**
- Modify: `run_flow.py`

- [ ] **Step 1: Replace run_flow.py with SolveX entry**

```python
import asyncio
import time

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.flow.flow_factory import FlowFactory, FlowType
from app.logger import logger


async def run_flow():
    agents = {
        "modeling": ModelingAgent(),
        "programming": ProgrammingAgent(),
    }
    try:
        prompt = input("请输入数学建模题目: ")

        if prompt.strip().isspace() or not prompt:
            logger.warning("Empty prompt provided.")
            return

        flow = FlowFactory.create_flow(
            flow_type=FlowType.SOLVEX,
            agents=agents,
            max_iterations=3,
        )
        logger.warning("Processing your request...")

        try:
            start_time = time.time()
            result = await asyncio.wait_for(
                flow.execute(prompt),
                timeout=3600,
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Request processed in {elapsed_time:.2f} seconds")
            logger.info(result)
        except asyncio.TimeoutError:
            logger.error("Request processing timed out after 1 hour")

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user.")
    except Exception as e:
        logger.error(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(run_flow())
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('run_flow.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

---

### Task 8: Integration Test

**Files:**
- Test: `tests/test_phase1.py`

- [ ] **Step 1: Create integration test**

```python
import asyncio
import pytest

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.flow.solvex_flow import SolveXFlow


@pytest.mark.asyncio
async def test_solvex_flow_linear_programming():
    """Test the full SolveX flow with a simple linear programming problem."""
    agents = {
        "modeling": ModelingAgent(),
        "programming": ProgrammingAgent(),
    }

    flow = SolveXFlow(agents=agents, max_iterations=2)

    problem = """某工厂生产A、B两种产品。生产每件A产品需要原料甲2kg、原料乙1kg，利润为300元；
生产每件B产品需要原料甲1kg、原料乙2kg，利润为400元。
该工厂每天有原料甲100kg、原料乙120kg可用。
请建立数学模型，求每天生产A、B产品各多少件时利润最大？"""

    result = await flow.execute(problem)

    # Result should not be empty
    assert result, "Flow should return a non-empty result"
    assert "VERIFICATION_RESULT:" in result or "结果" in result, "Result should contain verification or answer"


@pytest.mark.asyncio
async def test_modeling_agent_instantiation():
    """Test that ModelingAgent can be instantiated."""
    agent = ModelingAgent()
    assert agent.name == "modeling"
    assert agent.system_prompt is not None
    assert "数学建模" in agent.system_prompt


@pytest.mark.asyncio
async def test_programming_agent_instantiation():
    """Test that ProgrammingAgent can be instantiated."""
    agent = ProgrammingAgent()
    assert agent.name == "programming"
    assert agent.system_prompt is not None
    assert "编程" in agent.system_prompt
```

- [ ] **Step 2: Run agent instantiation tests**

Run: `cd /Users/akuya/Desktop/manus/SolveX && python -m pytest tests/test_phase1.py::test_modeling_agent_instantiation tests/test_phase1.py::test_programming_agent_instantiation -v`
Expected: Both PASS

- [ ] **Step 3: Run full integration test**

Run: `cd /Users/akuya/Desktop/manus/SolveX && python -m pytest tests/test_phase1.py::test_solvex_flow_linear_programming -v -s`
Expected: PASS (will call ChatGLM API, takes ~1-2 minutes)

- [ ] **Step 4: Manual test with run_flow.py**

Run: `cd /Users/akuya/Desktop/manus/SolveX && python run_flow.py`
Then paste the linear programming problem from `tests/simple/linear_programming/problem.md`.
Expected: Agent loop runs, produces solution with code execution results.

- [ ] **Step 5: Commit**

```bash
cd /Users/akuya/Desktop/manus/SolveX
git add app/prompt/modeling.py app/prompt/programming.py app/agent/modeling.py app/agent/programming.py app/flow/solvex_flow.py app/flow/flow_factory.py run_flow.py tests/test_phase1.py
git commit -m "feat(phase1): add ModelingAgent, ProgrammingAgent, and SolveXFlow with loop support"
```
