#!/bin/sh
# Запуск локального MCP GymAssistant из каталога установки (stdout — MCP-транспорт).
# Токен: GYM_MCP_ENV_FILE=/путь/к/.env в конфиге MCP-клиента или строкой export ниже;
# без него ищется .env рядом с server.py, затем ~/.config/gymassistant-mcp/.env.
# export GYM_MCP_ENV_FILE="/путь/к/.env"
cd "$(dirname "$0")" || exit 1
exec ./.venv/bin/python server.py
