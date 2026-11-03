# Реализация MCP GymAssistant

Это единственный сервер репозитория: `server.py` регистрирует инструменты для локального stdio, `remote_http.py` оборачивает **тот же реестр** для подготовленного Streamable HTTP. Установка, токен, обновление и откат описаны только в [QUICKSTART](../../QUICKSTART.md).

`core_tools.py`, `health_tools.py`, `plan_tools.py` и `workout_tools.py` сохраняют 15 исходных `gym_*` имён. `compat_tools.py` добавляет 44 имени прежнего .NET клиента в тот же процесс. `http_transport.py` ограничивает ответы и ошибки, не повторяет записи, не выводит токены или серверные тела ошибок. `install.py` копирует управляемые модули с локальной резервной копией.

Локальная проверка: `python -m unittest discover -s integrations/local-gymassistant -q`, затем `verify_stdio.py` и `verify_plans_stdio.py`. Все сетевые вызовы этих проверок идут к синтетическому loopback API.
