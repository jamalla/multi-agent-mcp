import asyncio
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agents.agent_config import get_mcp_client, AGENT_PREFIXES


def filter_tools(all_tools, prefix):
    """The whole mechanism: keep only tools whose name starts with prefix."""
    return [t for t in all_tools if t.name.startswith(prefix)]


async def build_agents():
    client = get_mcp_client()
    all_tools = await client.get_tools()          # full catalog, all tools

    agent1_tools = filter_tools(all_tools, AGENT_PREFIXES["agent1"])   # weather
    agent2_tools = filter_tools(all_tools, AGENT_PREFIXES["agent2"])   # country
    agent3_tools = filter_tools(all_tools, AGENT_PREFIXES["agent3"])   # world cup

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    agent1 = create_agent(llm, agent1_tools)   # bound to weather only
    agent2 = create_agent(llm, agent2_tools)   # bound to country only
    agent3 = create_agent(llm, agent3_tools)   # bound to world cup only

    return agent1, agent2, agent3, agent1_tools, agent2_tools, agent3_tools


async def main():
    a1, a2, a3, t1, t2, t3 = await build_agents()

    # PROOF: each agent sees only its subset
    print("Agent 1 tools:", [t.name for t in t1])
    print("Agent 2 tools:", [t.name for t in t2])
    print("Agent 3 tools:", [t.name for t in t3])

    # Ask agent 1 something it CAN do
    r = await a1.ainvoke({"messages": [("user", "What's the weather in Kuala Lumpur?")]})
    print("\nAgent 1 weather answer:\n", r["messages"][-1].content)

    # Ask agent 3 a world cup question
    r = await a3.ainvoke({"messages": [("user", "What are the upcoming World Cup matches?")]})
    print("\nAgent 3 world cup answer:\n", r["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
