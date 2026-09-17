"""
chat.py — interactive terminal chat with an Ollama model that has access to
agml-agent's tools THROUGH THE REAL MCP SERVER (mcp_server.py), not a
hand-duplicated set of wrapper functions. This makes chat.py itself the
MCP-to-Ollama bridge: any framework that doesn't speak MCP natively (Ollama
today; the same pattern covers any future non-MCP backend) needs exactly
this kind of adapter — start mcp_server.py, list its tools, translate the
schema, forward tool calls through the MCP session. A framework that DOES
speak MCP (Claude Code, Claude Desktop, Cursor...) needs none of this —
just point it at mcp_server.py directly.

One true source of tool definitions (mcp_server.py) either way.

Point at a remote Ollama server (e.g. a VM with more VRAM/compute) with
--host or the OLLAMA_HOST env var; pick any locally-pulled model, or let
this list what's available and choose interactively.

    uv run python -m agml_agent.chat                          # local ollama, pick model interactively
    agml-agent-chat --host http://192.168.1.50:11434           # remote VM (once installed)
    agml-agent-chat --model qwen2.5:7b                         # skip the picker
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

import ollama
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

SYSTEM_PROMPT = (
    "You are an assistant helping with agricultural computer vision work. "
    "You have two tools:\n"
    "- retrieve_grounding: live text/image grounding for a disease/pest/species/quality "
    "class, from external sources (EPPO, GBIF, UC IPM, Bugwood, USDA). Use it when you "
    "need factual/visual information ABOUT a specific class.\n"
    "- search_agml: search or look up AgML's own dataset catalog (real training datasets, "
    "with classes, licenses, and benchmark results). Use it when the user wants to find, "
    "evaluate, or learn about a DATASET, not a single class's biology.\n"
    "If a tool call returns nothing useful, try again with different arguments "
    "(a different scientific_name, fewer/no filters, different keywords) rather than "
    "giving up after one attempt."
)

MCP_SERVER_COMMAND = StdioServerParameters(command=sys.executable, args=["-m", "agml_agent.mcp_server"])


def _mcp_tool_to_ollama(tool) -> dict:
    """MCP's Tool schema (name, description, input_schema) maps directly
    onto Ollama's {"type": "function", "function": {...}} shape — same
    JSON Schema underneath, just a different wrapper key."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


def _tool_result_to_text(result) -> str:
    """CallToolResult.content is a list of content blocks (usually one
    TextContent, since both our tools return JSON strings) — flatten to
    plain text for the chat message."""
    parts = []
    for block in result.content:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else str(block))
    return "\n".join(parts) if parts else "(empty result)"


async def _choose_model_async(client: ollama.AsyncClient) -> str:
    models = (await client.list()).models
    if not models:
        print("No models found on this Ollama server. Pull one first, e.g.: ollama pull qwen2.5:7b")
        sys.exit(1)
    print("Available models:")
    for i, m in enumerate(models):
        print(f"  [{i}] {m.model}")
    while True:
        choice = input("Pick a model number: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(models):
            return models[int(choice)].model
        print("Invalid choice.")


async def run_turn(
    ollama_client: ollama.AsyncClient,
    mcp_session: ClientSession,
    tools: list[dict],
    model: str,
    messages: list[dict],
) -> None:
    """One user turn: call chat, execute any tool calls THROUGH THE MCP
    SESSION, loop until the model returns a plain answer. Printing tool
    activity along the way so it's visible, not just the final response."""
    while True:
        response = await ollama_client.chat(model=model, messages=messages, tools=tools)
        msg = response.message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            print(f"\nassistant: {msg.content}\n")
            return

        for call in msg.tool_calls:
            name = call.function.name
            args = dict(call.function.arguments)
            print(f"  [tool call] {name}({args})")
            try:
                result = await mcp_session.call_tool(name, args)
                text = _tool_result_to_text(result)
            except Exception as e:
                text = json.dumps({"error": str(e)})
            preview = text[:200] + ("..." if len(text) > 200 else "")
            print(f"  [tool result] {preview}")
            messages.append({"role": "tool", "tool_name": name, "content": text})


async def run(args: argparse.Namespace) -> None:
    ollama_client = ollama.AsyncClient(host=args.host)

    async with stdio_client(MCP_SERVER_COMMAND) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            mcp_tools = (await mcp_session.list_tools()).tools
            tools = [_mcp_tool_to_ollama(t) for t in mcp_tools]
            print(f"MCP tools available: {', '.join(t.name for t in mcp_tools)}")

            model = args.model or await _choose_model_async(ollama_client)
            print(f"Using model: {model}  (host: {args.host or 'default/OLLAMA_HOST'})")
            print("Type your message, or 'exit' to quit.\n")

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(None, input, "you: ")
                    user_input = user_input.strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    break
                messages.append({"role": "user", "content": user_input})
                await run_turn(ollama_client, mcp_session, tools, model, messages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive terminal chat with MCP-mediated access to agml-agent's tools.")
    parser.add_argument("--host", default=None, help="Ollama server URL, e.g. http://192.168.1.50:11434 — also reads OLLAMA_HOST env var if unset")
    parser.add_argument("--model", default=None, help="model name to use, e.g. qwen2.5:7b — omit to pick interactively from what's available")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
