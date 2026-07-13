from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

import anyio
import pydantic_core

from app.servers.mcp.server import create_server


def _jsonable(value: object) -> object:
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
    return pydantic_core.to_jsonable_python(value)


async def _list_tools() -> None:
    server = create_server()
    tools = await server.list_tools()
    print(json.dumps([tool.name for tool in tools], indent=2))


async def _list_resources() -> None:
    server = create_server()
    resources = await server.list_resources()
    templates = await server.list_resource_templates()
    payload = {
        "resources": [_jsonable(resource) for resource in resources],
        "templates": [_jsonable(template) for template in templates],
    }
    print(json.dumps(payload, indent=2))


async def _read_resource(uri: str) -> None:
    server = create_server()
    result = await server.read_resource(uri)
    normalized = [_jsonable(item) for item in result]
    print(json.dumps(normalized, indent=2))


async def _list_prompts() -> None:
    server = create_server()
    prompts = await server.list_prompts()
    print(json.dumps([_jsonable(prompt) for prompt in prompts], indent=2))


async def _get_prompt(name: str, arguments: dict[str, object]) -> None:
    server = create_server()
    result = await server.get_prompt(name, arguments)
    payload = _jsonable(result)
    print(json.dumps(payload, indent=2))


async def _call_tool(name: str, arguments: dict[str, object]) -> None:
    server = create_server()
    result = await server.call_tool(name, arguments)
    if isinstance(result, Sequence):
        normalized = [_jsonable(item) for item in result]
        print(json.dumps(normalized, indent=2))
        return

    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local MCP smoke tests for the Jarvis server.")
    parser.add_argument("--list-tools", action="store_true", help="Print the registered MCP tool names.")
    parser.add_argument("--list-resources", action="store_true", help="Print the registered MCP resources and templates.")
    parser.add_argument("--read-resource", help="Read a specific resource URI.")
    parser.add_argument("--list-prompts", action="store_true", help="Print the registered MCP prompts.")
    parser.add_argument("--prompt", help="Render a prompt by name.")
    parser.add_argument("--tool", help="Invoke a specific tool by name.")
    parser.add_argument(
        "--args-json",
        default="{}",
        help='JSON object of tool arguments, for example: {"query": "raspberry pi"}',
    )
    args = parser.parse_args()

    if args.list_tools:
        anyio.run(_list_tools)
        return

    if args.list_resources:
        anyio.run(_list_resources)
        return

    if args.read_resource:
        anyio.run(_read_resource, args.read_resource)
        return

    if args.list_prompts:
        anyio.run(_list_prompts)
        return

    if args.prompt:
        anyio.run(_get_prompt, args.prompt, json.loads(args.args_json))
        return

    if args.tool:
        anyio.run(_call_tool, args.tool, json.loads(args.args_json))
        return

    parser.error("Choose a list, prompt, resource, or tool action.")


if __name__ == "__main__":
    main()
