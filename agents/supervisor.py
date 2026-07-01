import asyncio
from typing import Literal
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from agents.graph import build_agents


class Route(BaseModel):
    """Which specialist agent should handle the user's query."""
    destination: Literal["weather", "country"] = Field(
        description="'weather' for weather/forecast/temperature questions; "
                    "'country' for questions about countries, capitals, population, currency, languages."
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
    agent1, agent2, _, _ = await build_agents()
    router_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(Route)

    async def route_and_run(user_query: str) -> dict:
        decision = await router_llm.ainvoke(
            f"Route this user query to the correct specialist:\n\n{user_query}"
        )
        if decision.destination == "weather":
            agent, label = agent1, "Agent 1 (weather)"
        else:
            agent, label = agent2, "Agent 2 (country)"

        result = await agent.ainvoke({"messages": [("user", user_query)]})
        messages = result["messages"]
        answer = messages[-1].content

        return {
            "answer": answer,
            "route": {"destination": decision.destination, "agent": label},
            "steps": _extract_steps(messages),
        }

    return route_and_run


async def main():
    supervisor = await build_supervisor()
    for q in [
        "What's the weather in Tokyo?",
        "What currency does Brazil use?",
        "How hot is it in Dubai right now?",
        "What's the dialing code for India?",
    ]:
        print("\nUSER:", q)
        r = await supervisor(q)
        print(f"[routed to {r['route']['agent']}]")
        for s in r["steps"]:
            if s["kind"] == "tool_call":
                print(f"  → call {s['tool']}({s['args']})")
            else:
                print(f"  ← {s['tool']} returned: {s['output']}")
        print(r["answer"])


if __name__ == "__main__":
    asyncio.run(main())
