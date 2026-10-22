# GA-043 — объединение MCP 0.3.0 и PR6

## Контекст

По поручению владельца подготовить общий технический выпуск, включающий ревью Claude, без потери уже выпущенных возможностей: новые измерения подходов, дополнение дней плана, Apple Health и существующий ключ Mentoru. Рабочая установка бота и её конфигурация не изменяются на этапе подготовки.

## Исходное состояние

- Ветка `feature/catalog-mcp-techdebt` от `origin/main` c5f5d46 (MCP 0.3.0, клиент 0.16.0).
- Локально объединён PR6, head 5685c91. Основной checkout с чужими незакоммиченными файлами и worktree Claude не изменены.
- .NET MCP остаётся тонкой обёрткой над сгенерированным клиентом. Python MCP теперь целиком воспроизводится из репозитория.

## Сделано

- Сохранены 43 .NET инструмента, включая `append_plan_days`, и 14 Python инструментов. Таблица прав из PR6 дополнена маршрутом добавления дней; сохранены новые DTO измерений и ParentCode.
- `core_tools.py` использует `workout_tools.py`: чтение сохраняет measurement целиком, кардио и неизвестные форматы не попадают в силовые рекорды. Вместе работают новые локальные даты, поиск по истории и явный флаг разминки из PR6.
- Полный установщик включает workout_tools и сохраняет прежние файлы перед заменой; `.env`, `.venv` и существующий run.sh остаются неизменными. Частичный `install_plans.py` сохранён для прежнего монолитного сервера, но для новой установки используется install.py.
- CI запускает один отдельный Python job с закреплёнными зависимостями, unit tests и двумя настоящими stdio-проверками на синтетическом API. Повторный Python прогон внутри .NET job удалён.
- Конфликты документации разрешены с сохранением описания typed measurement и новой воспроизводимой установки.

## Проверка

- .NET Release: 109/109 тестов, ошибок и предупреждений сборки нет. Лог `/tmp/ga043-mcp-techdebt-dotnet-final.log`.
- Python: 81/81, `/tmp/ga043-mcp-techdebt-python.log`.
- Настоящий .NET stdio: 43 инструмента, initialize/health/typed create/append/read, неизменность legacy подходов: PASS.
- Настоящий Python stdio: 14 инструментов, локальная дата, история за пределами 50 последних тренировок, разминка, Health null: PASS.
- Python plans stdio: 7 добавленных дней на синтетическом API, сохранность прежнего дерева, backup перед каждым дополнением, отсутствие повторного POST при неизвестном результате, typed workout/plan read и рекорды: PASS.
- Docker build локального `gymassistant/mcp-server:ga043-integrated` и настоящий stdio этого образа: PASS. Только BuildKit secrets, без записи ключей в репозиторий/образ.
- Production API не использовался для тестов. Рабочие ключи, права, данные и runtime Mentoru не менялись.

## Подготовка перед расширением метаданных

Эти шаги выполнены в контракте метаданных и фактическом выпуске ниже. Для уже открытых MCP-сессий по-прежнему требуется переподключение; публикация образа сама по себе их не обновляет.

## Контракт метаданных после backend0.18.0

- Backend0.18.0 выпущен [workflow39781074992](https://github.com/Gym-Assistant/GymBackendV2/actions/runs/39781074992), с backup/restore/protected-copy и неизменностью истории. [Клиент0.17.0](https://github.com/Gym-Assistant/GymBackendV2/actions/runs/39782758623) сгенерирован из фактически работающего API через SSH loopback; пакет подтверждён GitHub Packages.
- .NET зависимость обновлена0.16.0→0.17.0, оба lockfile пересозданы. Новые nullable metadata/role/media передаются тонкими инструментами без собственного пересчёта.
- `list_default_exercises` добавляет includeHidden=false; новый `get_default_exercise` читает скрытый шаблон по globalId. Итого44 .NET инструмента. CanonicalId не переназначает ссылки и не удаляет личные упражнения.
- Python сохраняет новые и неизвестные metadata как rawJSON. `gym_exercises` добавляет совместимый include_hidden=False, допустимый только для source=default; новый `gym_default_exercise` читает по настоящему ID. Итого15 инструментов. Создание планов по умолчанию использует видимый каталог.
- .NET114/114, Python83/83, настоящий .NETstdio44 и Pythonstdio15: PASS. Проверены includeHidden query, скрытый read-by-ID, metadata/media/role roundtrip, отсутствие записи при чтении, прежние typed create/append/read и Health. Логи `/tmp/ga043-mcp-metadata-{dotnet,dotnet-stdio,python,stdio-python,plans-stdio}.log`.
- В действующем локальном MCP server.py читает vault.env по прежнему hardcoded пути; run.sh пока не задаёт GYM_MCP_ENV_FILE. При установке нового runtime сначала сохранить резервную копию, затем явно указать тот же путь в wrapper с приоритетом существующей переменной процесса. Содержимое .env/ключи не копировать и не изменять.

## Фактический runtime и выпуск

- [PR9](https://github.com/Gym-Assistant/GymAssistantMcpServer/pull/9) объединён commit `cbdf44490de87f1ea3f1ef4b34186e4201927320`; исходный PR6 GitHub также отметил MERGED. Тег `v0.4.0` новый, прежние теги не передвигались.
- [CI39783542621](https://github.com/Gym-Assistant/GymAssistantMcpServer/actions/runs/39783542621) и [mainCI39783775275](https://github.com/Gym-Assistant/GymAssistantMcpServer/actions/runs/39783775275): dotnet/python/docker SUCCESS. Локальный Docker build и настоящий container stdio44 также PASS (`/tmp/ga043-mcp-metadata-docker.log`, `/tmp/ga043-mcp-metadata-docker-stdio.log`).
- Локальный Python runtime установлен из того же дерева. Резервная копия файлов: `/Users/nikitagorovenko/tools/gymassistant-mcp/.backups/repo-20261022T130616000980Z` (закрытый каталог). Проверено совпадение всех6 managed-файлов с релизным исходником.
- Vault `.env` проверен на побайтную неизменность. Единственное изменение wrapper: прежний путь передан через default `GYM_MCP_ENV_FILE`; явная переменная окружения имеет приоритет. Старый run.sh сохранён и проверен по исходному fingerprint. Ключи, права и конфигурация MCP-клиента не менялись.
- Установленный runtime прошёл два синтетических stdio-прогона:15 инструментов, typed plans/append/backup/legacy history и Health PASS. Новый процесс с действующей конфигурацией выполнил **только чтение** профиля, личных упражнений, планов, справочника Health и общего каталога с includeHidden/read-by-ID: PASS, writes0. Агрегированный отчёт `/tmp/ga043-mcp-readonly-live-result.json`, без пользовательских записей и ключей.
- Уже открытые сессии Mentoru продолжают прежний процесс до переподключения; новая установка проверена отдельным процессом. Принудительное завершение процессов не выполнялось.

Откат локального runtime: вернуть5 прежних файлов (`server.py`, `health_tools.py`, `plan_tools.py`, `workout_tools.py`, `run.sh`) из указанной копии. Новые core_tools.py/requirements.txt не влияют на старый server.py; удаление не требуется. Vault `.env`, виртуальное окружение и пользовательские backup планов не восстанавливать поверх текущих. Для .NET можно выбрать предыдущий immutable image0.3.0.


- [Release39783948610](https://github.com/Gym-Assistant/GymAssistantMcpServer/actions/runs/39783948610): SUCCESS, публикация [v0.4.0](https://github.com/Gym-Assistant/GymAssistantMcpServer/releases/tag/v0.4.0)2026-10-22T13:08:58Z. Multi-arch image `ghcr.io/gym-assistant/gymassistant-mcp-server@sha256:6b25d24864ca80275e99a17dac5ec2b297917eef94e542320df5d268839b500e`; GitHub Packages подтверждает теги0.4.0/latest (id1428515463).
- **Именно опубликованный digest** скачан и прошёл настоящий container stdio44 с синтетическим API: Health, metadata/includeHidden/read-by-ID, typed create/append/read и прежние подходы PASS. Лог `/tmp/ga043-mcp040-published-stdio.log`; исходный release log `/tmp/ga043-mcp040-release.log`. Ни одного тестового изменения пользовательских данных.
