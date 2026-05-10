"""
OpenAI GPT-4o-mini function-calling agent loop.

Implements the ReAct pattern:
  1. Send messages + system prompt + tools to OpenAI
  2. If response contains tool_calls → execute each tool → append results
  3. Repeat until response is a plain text message (no tool_calls)
  4. Return the final text response

Conversation history is passed in from the caller (from the DB) so each
run_agent() call is stateless — no in-memory conversation state.

All OpenAI calls use tenacity retry for transient errors and rate limits.
"""
import json
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger
from config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, MAX_TOKENS, MAX_AGENT_TURNS, AGENT_TEMPERATURE
from agent.tools import OPENAI_TOOLS, TOOL_DISPATCH
from agent.prompts import LAWYER_SYSTEM_PROMPT

_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _chat(messages: list[dict], tools: list | None = None) -> object:
    """Single OpenAI chat completion call with retry."""
    kwargs = {
        "model":       OPENAI_CHAT_MODEL,
        "messages":    messages,
        "max_tokens":  MAX_TOKENS,
        "temperature": AGENT_TEMPERATURE,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _openai().chat.completions.create(**kwargs)


def run_agent(
    user_message: str,
    conversation_history: list[dict],
    case_context: str = "",
) -> str:
    """
    Run the agent for one user turn.

    Args:
        user_message: the user's current input
        conversation_history: list of OpenAI-format message dicts
            [{"role": "user"|"assistant", "content": "..."}]
        case_context: text extracted from user's uploaded documents

    Returns:
        The agent's final text response as a string.
    """
    # Build system message
    system_content = LAWYER_SYSTEM_PROMPT
    if case_context:
        system_content += (
            f"\n\nCASE DOCUMENTS UPLOADED BY USER:\n"
            f"{case_context[:2000]}\n"
            "(Use these facts when analyzing the user's situation.)"
        )

    # Build message list: system + history + current user message
    messages = [{"role": "system", "content": system_content}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    # Agent loop
    for turn in range(MAX_AGENT_TURNS):
        logger.debug(f"Agent turn {turn + 1}/{MAX_AGENT_TURNS}")
        response = _chat(messages, tools=OPENAI_TOOLS)
        msg = response.choices[0].message

        # No tool calls → final response
        if not msg.tool_calls:
            return msg.content or "I could not generate a response. Please try again."

        # Execute tool calls
        messages.append(msg)  # append assistant message with tool_calls

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            logger.info(f"Tool call: {tool_name}({tool_args})")

            if tool_name in TOOL_DISPATCH:
                try:
                    result = TOOL_DISPATCH[tool_name](**tool_args)
                except Exception as e:
                    result = f"Tool '{tool_name}' failed: {str(e)}"
                    logger.error(f"Tool error: {e}")
            else:
                result = f"Unknown tool: {tool_name}"

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

    # Max turns reached — request a summary
    logger.warning(f"Max agent turns ({MAX_AGENT_TURNS}) reached. Requesting summary.")
    messages.append({
        "role":    "user",
        "content": "Please summarize your findings and give your final legal analysis now.",
    })
    final = _chat(messages)  # no tools — force plain text
    return final.choices[0].message.content or "Analysis complete."
