import asyncio
from typing import Literal
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from agents.graph import build_agents


class Route(BaseModel):
    """Which specialist agent should handle the user's query."""
    destination: Literal["weather", "country", "worldcup"] = Field(
        description="'weather' for weather/forecast/temperature questions; "
                    "'country' for questions about countries, capitals, population, currency, languages; "
                    "'worldcup' for FIFA World Cup 2026 matches, fixtures, results, group standings, "
                    "team form, and match predictions."
    )


def _truncate(text: str, limit: int = 600) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + " …"


def _clean_tool_output(content) -> str:
    """MCP tool results arrive as content blocks like [{'type':'text','text':...}].
    Unwrap them to the plain text payload for a readable trace."""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            else:
                parts.append(str(block))
        content = "\n".join(parts)
    return _truncate(content)


def _extract_steps(messages) -> list[dict]:
    """Walk the agent's message history into a readable trace of tool calls/results."""
    steps: list[dict] = []
    for m in messages:
        mtype = getattr(m, "type", None)
        if mtype == "ai":
            for tc in (getattr(m, "tool_calls", None) or []):
                steps.append({
                    "kind": "tool_call",
                    "tool": tc.get("name", "?"),
                    "args": tc.get("args", {}),
                })
        elif mtype == "tool":
            steps.append({
                "kind": "tool_result",
                "tool": getattr(m, "name", "?"),
                "output": _clean_tool_output(getattr(m, "content", "")),
            })
    return steps


async def build_supervisor():
    agent1, agent2, agent3, _, _, _ = await build_agents()
    router_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(Route)

    # One running conversation per session, kept above the agents so context
    # survives when the user switches between them. In-memory: fine for a demo.
    sessions: dict[str, list[tuple[str, str]]] = {}

    async def route_and_run(user_query: str, session_id: str = "default") -> dict:
        history = sessions.setdefault(session_id, [])

        # Let the router see recent turns so follow-ups ("what about there?")
        # route to the right agent.
        recent = "\n".join(f"{role}: {content}" for role, content in history[-6:])
        decision = await router_llm.ainvoke(
            (f"Conversation so far:\n{recent}\n\n" if recent else "")
            + f"Route this new user message to the correct specialist:\n{user_query}"
        )
        if decision.destination == "weather":
            agent, label = agent1, "Agent 1 (weather)"
        elif decision.destination == "worldcup":
            agent, label = agent3, "Agent 3 (world cup)"
        else:
            agent, label = agent2, "Agent 2 (country)"

        # Give the chosen agent the whole conversation plus the new question.
        result = await agent.ainvoke({"messages": history + [("user", user_query)]})
        answer = result["messages"][-1].content

        # Remember this turn (cap length so it does not grow forever).
        history.append(("user", user_query))
        history.append(("assistant", answer))
        del history[:-20]

        return {
            "answer": answer,
            "route": {"destination": decision.destination, "agent": label},
            "steps": _extract_steps(result["messages"]),
            "session_id": session_id,
        }

    return route_and_run


async def main():
    supervisor = await build_supervisor()
    # A single session with follow-ups that only work if context is kept:
    # "there" and "they" refer back to earlier turns, across different agents.
    sid = "demo"
    for q in [
        "What's the weather in Tokyo?",         # weather agent
        "What currency do they use there?",      # country agent, "there" = Japan
        "Are they in the World Cup this year?",   # world cup agent, "they" = Japan
    ]:
        print("\nUSER:", q)
        r = await supervisor(q, sid)
        print(f"[routed to {r['route']['agent']}]")
        print(r["answer"])


if __name__ == "__main__":
    asyncio.run(main())
