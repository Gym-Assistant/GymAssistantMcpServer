# Техдолг MCP: TD-73, TD-54, TD-40 (часть MCP), TD-74

Ветка: `feature/techdebt-mcp` от `origin/main` `a0dbae0`.

## Контекст

- **TD-73.** Сервер, которым пользуется Mentoru, нельзя было воспроизвести. `server.py` лежал только в установленном каталоге, установщик патчил строки, копия `health_tools.py` в репозитории отставала (13 инструментов вместо 14). Зависимости не были закреплены, Python-тесты в CI не запускались.
- **TD-54 / TD-40.** `gym_workout(date)` брал дату из UTC `createdAt` первого подхода и искал среди 50 последних тренировок. `gym_plan` листал все страницы `/plans`. `gym_records` определял разминку только эвристикой.
- **TD-74.** Описания .NET-инструментов называли права, которых backend не требует. README и CLAUDE.md устарели. Сообщение об ошибке токена ссылалось на Telegram-бота. `get_workouts_report` и `check_plan_updates` теряют ответ.

## Текущее состояние

Все пункты выполнены в ветке, коммиты локальные, push не выполнялся. Установленный сервер владельца не тронут: файлы прочитаны, схемы инструментов сверены офлайн на временной копии.

## План

1. Перенести сервер в репозиторий без изменения поведения, вынести путь env-файла в `GYM_MCP_ENV_FILE`, закрепить зависимости, заменить установщик.
2. Исправить даты тренировок, поиск по истории, учёт разминки; описать формулу Эпли.
3. Читать план через `GET /plans/{id}` с проверкой автора.
4. Добавить Python-задание в CI.
5. Исправить описания .NET по фактическим `RequireScope` backend и закрепить тестом; обновить README, CLAUDE.md, AGENTS.md, `EnvConfig`.
6. Написать план сведения серверов `docs/mcp-convergence-plan.md`.

## Сделано

- `integrations/local-gymassistant/`:
  - добавлены `server.py`, `core_tools.py`, `run.sh`, `requirements.txt` (версии из `pip freeze` рабочей установки), `install.py`; `install_plans.py` удалён;
  - `health_tools.py` побайтно совпадает с установленным;
  - env-файл ищется так: `GYM_MCP_ENV_FILE`, затем `.env` рядом с `server.py`, затем `$XDG_CONFIG_HOME/gymassistant-mcp/.env`; личных путей в коде нет;
  - `GYM_HEALTH_API_TOKEN` поддержан штатно;
  - даты тренировок: `startedAt`, затем `scheduledDateLocal`, в поясе `timeZoneId` (иначе UTC). Поиск страницами по 100, до 5000 тренировок;
  - рекорды: разминка по `isWarmup`, эвристика — только при `null`. Эпли `вес × (1 + повторы/30)`, 1 повтор — сам вес;
  - `gym_plan`: `GET /plans/{id}` и сверка `authorUserId` с `/auth/me`. 404, чужой и удалённый план — «не найден»;
  - новые тесты: `test_core_tools.py`, `test_server.py`, `test_install.py`; `verify_stdio.py` переписан, `verify_plans_stdio.py` запускает код репозитория.
- `.github/workflows/build.yml`: задание `python` (Python 3.14, закреплённые зависимости, unittest, оба stdio-сценария).
- .NET:
  - описания каталогов — «Scope не нужен…» (анонимно или любой PAT), `health_check` — `Scope: profile:read`;
  - честные описания `get_workouts_report` и `check_plan_updates`;
  - `ToolAccessContractTests` (таблица 42 инструментов «маршрут → право» из GymBackendV2 `origin/develop`, проверка описаний, фактических маршрутов и README);
  - сообщение `EnvConfig` указывает «Settings -> API tokens».
- README (42 инструмента, `get_apple_health_metrics`, клиент 0.13.0, права, ограничения), CLAUDE.md, AGENTS.md.
- `docs/mcp-convergence-plan.md`.
- Находка: `GET /api/plans/{id}` на backend не проверяет владельца. Записано в план сведения; backend не менялся.

## Проверка

- `dotnet build GymAssistantMcpServer.slnx -c Release` — 0 предупреждений, 0 ошибок.
- `dotnet test GymAssistantMcpServer.slnx -c Release` — 102 из 102. Изменённое описание `list_muscles` ловится тестом (проверено обратной заменой).
- `python3 scripts/verify-stdio.py dotnet …/GymAssistant.McpServer.dll` — PASS, 42 инструмента, синтетический backend.
- Python 3.14.7, временный venv вне репозитория из `requirements.txt`; `pip freeze` совпадает с рабочей установкой.
  - `python -m unittest discover -s integrations/local-gymassistant` — 73 теста OK.
  - `verify_stdio.py` — PASS: 14 инструментов, локальная дата, поиск дальше 50 тренировок, разминка по флагу.
  - `verify_plans_stdio.py` — PASS: проверка автора по ID, 13 некорректных запросов заблокированы, нет повторов при 500/409.
- Схемы 14 инструментов коммита переноса совпадают со схемами установленного сервера: офлайн-сравнение `list_tools`, временная копия, пустой env-файл.
- Docker-сборка и задание CI на GitHub не запускались.
- Production не вызывался.

## Не входит

- Изменения backend: `Produces<T>`, проверка владельца, агрегаты, клиент ≥ 0.16.
- Перенос защитной логики в .NET и переключение Mentoru (см. план сведения).
- Обновление установленного `~/tools/gymassistant-mcp`: по желанию владельца, шаги — в отчёте и README.
