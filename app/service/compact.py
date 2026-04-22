"""
Memory compaction service for SolveX agents.

Inspired by claude-code's compact.ts: uses the LLM itself to summarize
conversation history when it grows too large, replacing old messages
with a structured summary while keeping recent messages intact.
"""

from app.logger import logger
from app.schema import Memory, Message


# --- Constants ---
# Rough character-to-token ratio (ChatGLM uses ~4 chars/token for Chinese+English)
CHARS_PER_TOKEN = 3.5

# Compact when estimated tokens exceed this threshold
COMPACT_THRESHOLD_TOKENS = 80_000

# Always keep the most recent N messages intact (don't summarize these)
KEEP_RECENT_MESSAGES = 4

# Max output tokens for the summary itself
COMPACT_MAX_OUTPUT_TOKENS = 4096


COMPACT_PROMPT = (
    "You are a conversation summarizer for a mathematical modeling agent.\n"
    "Create a detailed summary of the conversation below.\n\n"
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\n\n"
    "Before your summary, wrap your analysis in <analysis> tags to organize your thoughts.\n\n"
    "Your summary MUST include these sections:\n\n"
    "1. **Task**: What problem is being solved?\n"
    "2. **Key Decisions**: Important modeling/coding decisions made.\n"
    "3. **Files**: Files read, created, or modified with key content snippets.\n"
    "4. **Tool Results**: Key results from tool executions (computed values, search results).\n"
    "5. **Errors**: Any errors encountered and how they were fixed.\n"
    "6. **Current State**: What was just done and what needs to happen next.\n\n"
    "Wrap your final summary in <summary> tags.\n\n"
    "Example:\n"
    "<analysis>Reviewing the conversation...</analysis>\n"
    "<summary>\n"
    "1. **Task**: [description]\n"
    "2. **Key Decisions**: [decisions]\n"
    "3. **Files**: [file details]\n"
    "4. **Tool Results**: [key results]\n"
    "5. **Errors**: [errors and fixes]\n"
    "6. **Current State**: [what's happening now]\n"
    "</summary>"
)


def _estimate_tokens(messages: list[Message]) -> int:
    """Rough token estimation from messages."""
    total_chars = 0
    for msg in messages:
        if msg.content:
            total_chars += len(msg.content)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total_chars += len(tc.function.arguments)
    return int(total_chars / CHARS_PER_TOKEN)


def _truncate_tool_results(messages: list[Message], max_chars: int = 2000) -> list[Message]:
    """Truncate long tool result messages to save context space."""
    truncated = []
    for msg in messages:
        if msg.role == "tool" and msg.content and len(msg.content) > max_chars:
            truncated.append(
                Message(
                    role=msg.role,
                    content=msg.content[:max_chars] + "\n...[truncated for compaction]",
                    name=msg.name,
                    tool_call_id=msg.tool_call_id,
                )
            )
        else:
            truncated.append(msg)
    return truncated


def _format_messages_for_summary(messages: list[Message]) -> str:
    """Format messages into readable text for the summarizer."""
    lines = []
    for msg in messages:
        role = msg.role.upper()
        if msg.content:
            # Truncate individual very long messages
            content = msg.content
            if len(content) > 3000:
                content = content[:3000] + "\n...[truncated]"
            lines.append(f"[{role}]: {content}")
        if msg.tool_calls:
            for tc in msg.tool_calls:
                lines.append(f"[{role} TOOL_CALL]: {tc.function.name}({tc.function.arguments[:500]})")
    return "\n\n".join(lines)


def _extract_summary(raw: str) -> str:
    """Extract the <summary> block from LLM output, stripping <analysis>."""
    # Strip analysis
    import re
    result = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw)
    # Extract summary
    match = re.search(r"<summary>([\s\S]*?)</summary>", result)
    if match:
        return match.group(1).strip()
    # Fallback: return everything after analysis if no summary tags
    return result.strip()


async def compact_agent_memory(agent, threshold: int = COMPACT_THRESHOLD_TOKENS) -> bool:
    """
    Compact an agent's memory if it exceeds the token threshold.

    Uses the agent's own LLM to summarize old messages, then replaces
    them with the summary while keeping recent messages intact.

    Inspired by claude-code's compactConversation():
    1. Check if memory exceeds threshold
    2. Split into old (summarize) + recent (keep)
    3. Ask LLM to summarize old messages
    4. Replace old messages with summary

    Args:
        agent: A ToolCallAgent instance with .memory and .llm
        threshold: Token count threshold to trigger compaction

    Returns:
        True if compaction was performed, False if not needed
    """
    messages = agent.memory.messages
    estimated = _estimate_tokens(messages)

    if estimated < threshold:
        return False

    if len(messages) <= KEEP_RECENT_MESSAGES + 1:
        return False  # Not enough messages to compact

    logger.info(
        f"🔄 Compacting {agent.name}'s memory "
        f"({estimated} tokens, {len(messages)} messages)"
    )
    print(f"\033[1;35m  🔄 Compacting {agent.name} memory ({estimated} tokens → summarizing...)\033[0m")

    # Split: old messages to summarize, recent to keep
    split_idx = len(messages) - KEEP_RECENT_MESSAGES
    old_messages = messages[:split_idx]
    recent_messages = messages[split_idx:]

    # Truncate long tool results in old messages
    old_messages = _truncate_tool_results(old_messages)

    # Format old messages for summarization
    conversation_text = _format_messages_for_summary(old_messages)

    # Create summarization request
    summary_request = (
        f"Summarize this agent conversation history:\n\n{conversation_text}"
    )

    try:
        # Use the agent's LLM to generate summary (no tools, just text)
        summary_raw = await agent.llm.ask(
            messages=[Message.user_message(summary_request)],
            system_msgs=[Message.system_message(COMPACT_PROMPT)],
            stream=False,
            temperature=0.0,
        )

        if not summary_raw:
            logger.warning("Compaction produced empty summary, skipping")
            return False

        summary = _extract_summary(summary_raw)

        # Build compact boundary message
        compact_msg = Message.system_message(
            f"[MEMORY COMPACTION]\n"
            f"Previous conversation ({len(old_messages)} messages, ~{estimated} tokens) "
            f"summarized:\n\n{summary}"
        )

        # Replace memory: summary + recent messages
        agent.memory = Memory()
        agent.memory.add_message(compact_msg)
        agent.memory.add_messages(recent_messages)

        new_estimate = _estimate_tokens(agent.memory.messages)
        logger.info(
            f"✅ Compaction complete: {estimated} → {new_estimate} tokens "
            f"({len(old_messages)} messages → 1 summary + {len(recent_messages)} recent)"
        )
        print(f"\033[1;32m  ✓ Compaction done: {estimated} → {new_estimate} tokens\033[0m")
        return True

    except Exception as e:
        logger.warning(f"Compaction failed for {agent.name}: {e}")
        return False
