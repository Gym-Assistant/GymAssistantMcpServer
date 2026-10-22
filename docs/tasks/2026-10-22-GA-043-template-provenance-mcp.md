# GA-043 — совместимость MCP с наследованием шаблонов

## Контекст

Подготовить MCP к первому выпуску 197 общих упражнений: сохранить связь личных упражнений с шаблонами, версию метаданных и явные личные переопределения. Новых инструментов в этой партии нет. Рабочие ключи, права, `.env` и `run.sh` не изменяются.

## Текущее состояние

Ветка `feature/catalog-template-client` от `origin/main` 190bc83 (MCP 0.4.0, клиент 0.17.0). Контракт backend 0.19.1, NuGet 0.18.0: `ExerciseViewModel.templateRevision` — nullable string, `templateOverrides` — nullable string[]; `ExerciseDefaultViewModel.templateRevision` — nullable string.

## План и сделано

- Установлен NuGet 0.18.0, обновлены оба lockfile. Публикация подтверждена [workflow 39816446273](https://github.com/Gym-Assistant/GymBackendV2/actions/runs/39816446273) и registry ID1429770157 (2026-10-22 16:44:52 UTC).
- Тонкие .NET инструменты передают новые поля через DTO без логики наследования. В описаниях различаются личный `Id` и `GlobalId` шаблона; при новой привязке нужно читать шаблон и передавать его `TemplateRevision` с явным списком overrides.
- Старое отсутствие provenance не заменяется выдуманной версией. Пустой список overrides не объявлен командой сброса: это решает отдельный backend refresh, который в этой партии не добавляется как MCP tool.
- Python `gym_exercises` и `gym_default_exercise` сохраняют raw JSON; уточнены только описания, добавлены unit/stdio-проверки provenance. Создание и дополнение планов продолжают использовать личные и общие ID по назначению.
- Версия совместимости MCP планируется 0.4.1. Первый релиз использует текущие иллюстрации; генерация недостающих фаз не относится к этой партии.

## Проверка

Подготовлены проверки чтения/записи provenance, отсутствия полей в legacy payload, пустого списка overrides, неизменности ID/имени/залов/1RM и настоящего stdio на синтетическом backend.

- Python unit: 84 теста PASS (`/tmp/ga043-mcp041-python.log`).
- Python общий stdio: PASS, 15 инструментов, Health/тренировки/записи сохранены (`/tmp/ga043-mcp041-python-stdio.log`).
- Python plans stdio: PASS; чтение provenance и ссылки личного упражнения на общий шаблон, создание двух дней и дополнение семью днями, сохранность прежнего плана, защита от повторных запросов. Запросов к production: 0 (`/tmp/ga043-mcp041-plans-stdio.log`).
- .NET Release build: 0 предупреждений, 0 ошибок; 116 тестов PASS (`/tmp/ga043-mcp041-build.log`, `/tmp/ga043-mcp041-dotnet-tests.log`).
- .NET host и Docker actual stdio: PASS, по 44 инструмента, поля provenance в input schema и запросе сохранения, отсутствие выдуманной версии в legacy, typed/legacy планы и Health (`/tmp/ga043-mcp041-dotnet-stdio.log`, `/tmp/ga043-mcp041-docker-stdio.log`).
- Docker build: PASS; пользователь контейнера 1654, локальный image ID `sha256:ef2f9d12377597d4fe594c9d0a3653d1c2d81d6c4bd9424b31ac904f8c171c1c`.

## Локальная установка и границы

Managed-файлы установлены в `/Users/nikitagorovenko/tools/gymassistant-mcp`; резервная копия — `.backups/repo-20261022T164749411297Z`. До установки все шесть managed-файлов совпадали с предыдущим выпуском; фактически меняется только описание инструментов в `plan_tools.py`. `.env` и `run.sh` побайтно сохранены. Установленные модули проверены обоими stdio-сценариями на синтетическом loopback API; production-запросов нет.

Работающие MCP-процессы не прерывались: новые описания инструментов загрузятся при штатном переподключении клиента. Публикация контейнера 0.4.1 фиксируется отдельно после PR/CI; локальная установка файлов не означает завершение контейнерного релиза.
