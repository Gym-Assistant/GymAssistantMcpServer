"""Локальный MCP GymAssistant: чтение данных, Apple Health и создание/дополнение планов.

Инструменты (15):
- core_tools.py:   gym_me, gym_workouts, gym_workout, gym_records,
                   gym_body_latest, gym_body_history, gym_status;
- health_tools.py: gym_health_daily, gym_health_metrics;
- plan_tools.py:   gym_plans, gym_plan, gym_exercises, gym_create_plan,
                   gym_append_plan_days, gym_default_exercise.

Конфигурация (переменные процесса важнее значений из env-файла):
- GYM_API_TOKEN — обязательный Personal API Token (gma_...);
- GYM_API_URL — по умолчанию https://gym-assistant.ru/api;
- GYM_HEALTH_API_TOKEN — необязательный отдельный токен health:read того же аккаунта;
- GYM_PLAN_BACKUP_DIR — каталог резервных копий перед дополнением плана.

Env-файл ищется так: GYM_MCP_ENV_FILE (если задан, файл обязан существовать),
иначе `.env` рядом с server.py, иначе $XDG_CONFIG_HOME/gymassistant-mcp/.env
(по умолчанию ~/.config/gymassistant-mcp/.env). Если файла нет — только переменные процесса.

Запуск: `.venv/bin/python server.py` (см. run.sh и README.md). stdout — MCP-транспорт.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core_tools import register_core_tools
from health_tools import register_health_tools, same_account_reader
from plan_tools import register_plan_tools, make_plan_writer, make_plan_appender


DEFAULT_API_URL = 'https://gym-assistant.ru/api'
ENV_FILE_VARIABLE = 'GYM_MCP_ENV_FILE'


def env_file_candidates(environ, here: Path) -> tuple[list[Path], bool]:
    """Кандидаты env-файла по порядку и признак явного выбора через GYM_MCP_ENV_FILE."""
    explicit = environ.get(ENV_FILE_VARIABLE)
    if explicit:
        return [Path(explicit).expanduser()], True
    config_home = Path(environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return [here / '.env', config_home / 'gymassistant-mcp' / '.env'], False


def find_env_file(environ, here: Path) -> Path | None:
    candidates, explicit = env_file_candidates(environ, here)
    for path in candidates:
        if path.is_file():
            return path
    if explicit:
        raise SystemExit(f'ERROR: {ENV_FILE_VARIABLE} указывает на отсутствующий файл: {candidates[0]}')
    return None


def read_env_file(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_config(environ=None, here: Path | None = None) -> dict:
    environ = dict(os.environ if environ is None else environ)
    here = Path(__file__).resolve().parent if here is None else here
    path = find_env_file(environ, here)
    return {**(read_env_file(path) if path else {}), **environ}


def make_api_get(api_url: str, default_token: str):
    def api_get(path: str, params: dict | None = None, token: str | None = None) -> dict | list:
        url = f'{api_url}{path}'
        if params:
            url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        request = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {token or default_token}', 'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    return api_get


def build_server(config: dict) -> FastMCP:
    api_url = (config.get('GYM_API_URL') or DEFAULT_API_URL).rstrip('/')
    token = config.get('GYM_API_TOKEN')
    if not token:
        raise SystemExit('ERROR: GYM_API_TOKEN не задан (env-файл или переменная окружения)')
    api_get = make_api_get(api_url, token)
    mcp = FastMCP('gymassistant')
    register_core_tools(mcp, api_get, api_url)
    health_token = config.get('GYM_HEALTH_API_TOKEN')
    health_reader = same_account_reader(
        api_get, lambda path, params=None: api_get(path, params, health_token)
    ) if health_token else api_get
    register_health_tools(mcp, health_reader)
    register_plan_tools(mcp, api_get, make_plan_writer(api_url, token), make_plan_appender(api_url, token))
    return mcp


if __name__ == '__main__':
    build_server(load_config()).run()
