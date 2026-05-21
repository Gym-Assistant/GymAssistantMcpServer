# GymAssistant MCP Server

MCP-сервер, который даёт твоему Claude/Cursor/Codex доступ к твоим данным [GymAssistant](https://gym-assistant.ru) через Model Context Protocol.

40 тулз — read и write по тренировкам, замерам тела, упражнениям и планам. Авторизация — через **Personal API Token** (PAT) с гранулярными scope'ами.

## Установка

### 1. Получи PAT

В Telegram-боте GymAssistant создай Personal API Token. Запиши значение — оно показывается один раз, потом только хэш.

Если у тебя ещё нет аккаунта на GymAssistant — заведи его через того же бота или через мини-аппу.

### 2. Подключи к Claude Code

```bash
claude mcp add gymassistant -- docker run -i --rm \
  -e GYM_API_TOKEN=gma_ТВОЙ_ТОКЕН \
  gymassistant/mcp-server:latest
```

### 3. Подключи к Cursor / Continue / другим MCP-клиентам

Добавь в `mcp.json` (точное имя/расположение конфига зависит от клиента):
```json
{
  "mcpServers": {
    "gymassistant": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "GYM_API_TOKEN", "gymassistant/mcp-server:latest"],
      "env": { "GYM_API_TOKEN": "gma_ТВОЙ_ТОКЕН" }
    }
  }
}
```

## Конфигурация (env vars)

| Переменная | Default | Назначение |
|---|---|---|
| `GYM_API_TOKEN` | (обяз.) | Personal API Token, начинается с `gma_` |
| `GYM_API_URL` | `https://gym-assistant.ru/api` | Backend endpoint |
| `GYM_LOG_LEVEL` | `Information` | `Trace` / `Debug` / `Information` / `Warning` / `Error` |

## Что умеют тулзы

40 тулз в 6 группах:

| Группа | Read тулзы | Write тулзы |
|---|---|---|
| Profile | `get_me`, `get_user_settings`, `get_active_plan` | `update_user_settings`, `set_active_plan` |
| Body | `list_body_characteristics`, `list_body_characteristics_with_latest`, `list_default_body_characteristics`, `get_body_characteristic`, `list_body_stamps` | `create_body_characteristic`, `delete_body_characteristic`, `create_body_stamps`, `delete_body_stamp` |
| Workouts | `list_workouts`, `get_workout`, `get_workouts_report` | `create_workout`, `update_set`, `delete_workout` |
| Exercises | `list_exercises`, `list_default_exercises`, `list_exercise_catalogs`, `list_muscles`, `list_equipment` | `create_exercise`, `delete_exercise` |
| Plans | `list_plans`, `get_plan`, `list_plan_catalog`, `get_plan_from_catalog`, `check_plan_updates` | `create_plan`, `delete_plan`, `fork_plan`, `publish_plan`, `unpublish_plan`, `pull_plan_updates`, `detach_plan` |
| Diagnostics | `health_check` | — |

Полные описания и параметры доступны через MCP-протокол — твой Claude/Cursor покажет их автоматически.

## Troubleshooting

- **`FATAL: GYM_API_TOKEN is required`** — env-переменная не передалась в контейнер. Проверь `-e GYM_API_TOKEN=...` в `docker run`.
- **`GYM_API_TOKEN has invalid shape`** — токен не соответствует формату `gma_` + 40-80 URL-safe символов. Сгенерируй новый.
- **HTTP 401 + `token expired`** — твой PAT просрочен. Создай новый в боте.
- **HTTP 403** — у токена нет нужного scope. Создай новый PAT с расширенным набором scope'ов.
- **Cannot connect to Docker daemon** — Docker Desktop не запущен.
- **Cluster of "info: ..." in stderr** — это нормально, MCP-сервер логирует в stderr (stdout зарезервирован под MCP-протокол).

## Совместимость

- .NET 10
- `ModelContextProtocol` 1.3.x
- `GymAssistant.Client` 0.7.* (NSwag-сгенерированный клиент)
- Сервер совместим с любым MCP-клиентом, поддерживающим stdio-транспорт

## Лицензия

MIT — см. [LICENSE](LICENSE).
