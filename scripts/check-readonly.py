"""Read-only stdio smoke against the configured API. Never prints personal payloads.

Use the Python integration's venv. GYM_MCP_ENV_FILE points to a private env file.
Example: python scripts/check-readonly.py -- python integrations/local-gymassistant/server.py
Only the explicit allowlist below can be called; no arbitrary tool execution.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/local-gymassistant'))
from server import load_config

CHECKS = [
    ('gym_me', 'get_me', {}, {}),
    ('gym_exercises', 'list_default_exercises', {'source': 'default'}, {'limit': 2}),
    ('gym_plans', 'list_plans', {}, {'limit': 2}),
    ('gym_workouts', 'list_workouts', {'n': 1}, {'limit': 1}),
    ('gym_health_metrics', 'get_apple_health_metrics', {}, {}),
]

async def main(command):
    config = load_config()
    env = os.environ.copy()
    for key in ('GYM_API_TOKEN', 'GYM_API_URL', 'GYM_HEALTH_API_TOKEN'):
        if key in config:
            env[key] = config[key]
    if not env.get('GYM_API_TOKEN'):
        raise SystemExit('GYM_API_TOKEN missing; configure a private env file.')
    failed = 0
    # Server stderr can contain API error bodies: do not send it to terminal/logs.
    with tempfile.TemporaryFile(mode='w+') as errors:
        async with stdio_client(StdioServerParameters(command=command[0], args=command[1:], env=env), errlog=errors) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                print(json.dumps({'transport': 'PASS', 'tools': len(names)}))
                for py, net, py_args, net_args in CHECKS:
                    for name, args in ((py, py_args), (net, net_args)):
                        if name not in names:
                            failed += 1
                            print(json.dumps({'tool': name, 'result': 'MISSING'}))
                            continue
                        try:
                            result = await session.call_tool(name, args)
                            ok = not result.isError
                        except Exception:
                            ok = False
                        failed += not ok
                        print(json.dumps({'tool': name, 'result': 'PASS' if ok else 'FAIL'}))
    return int(bool(failed))

if __name__ == '__main__':
    command = sys.argv[1:]
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        raise SystemExit('Usage: check-readonly.py -- <command> [args...]')
    try:
        raise SystemExit(asyncio.run(main(command)))
    except Exception:
        raise SystemExit('Connection failed. Check runtime, API URL, token and scopes locally; no payload logged.')
