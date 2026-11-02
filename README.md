# GymAssistant MCP Server

MCP-сервер, который даёт твоему Claude/Cursor/Codex доступ к твоим данным [GymAssistant](https://gym-assistant.ru) через Model Context Protocol.

44 инструмента — read и write по тренировкам, замерам тела, упражнениям, планам и Apple Health. Авторизация — через **Personal API Token** (PAT) с гранулярными scope'ами.

## Подключение нового пользователя

**[Пошаговая установка без Docker и GitHub Packages → QUICKSTART.md](QUICKSTART.md)**

Рекомендуемый путь первого подключения — существующий Python stdio-коннектор
из `integrations/local-gymassistant`: 15 инструментов, личный API-токен,
локальная установка. В нём доступны безопасное создание и дополнение планов.
Не передавайте токен в чат; сохраняйте его в локальном закрытом env-файле.

Этот репозиторий также содержит .NET MCP с 44 инструментами (описан ниже).
Выпуск Docker `0.6.0` проверяется отдельно от Python: это разные реализации и наборы инструментов.
На проверке 03.11.2026 анонимное получение образа GHCR вернуло **401**;
прежняя инструкция с `latest` не является рабочим публичным стартом для нового пользователя.
Доступ к приватному registry не требуется для Python-варианта.

Для уже авторизованных пользователей registry .NET запускается так:

```sh
# Файл содержит GYM_API_TOKEN и доступен только владельцу (chmod 600).
# Не добавляйте токен непосредственно в команду или сообщения ассистенту.
docker run --rm -i --env-file /абсолютный/путь/gymassistant.env \
  ghcr.io/gym-assistant/gymassistant-mcp-server:0.6.0
```

## Конфигурация (env vars)

| Переменная | Default | Назначение |
|---|---|---|
| `GYM_API_TOKEN` | (обяз.) | Personal API Token, начинается с `gma_` |
| `GYM_API_URL` | `https://gym-assistant.ru/api` | Backend endpoint |
| `GYM_LOG_LEVEL` | `Information` | `Trace` / `Debug` / `Information` / `Warning` / `Error` |

## Что умеют тулзы

44 инструмента в 7 группах:

| Группа | Read тулзы | Write тулзы |
|---|---|---|
| Profile | `get_me`, `get_user_settings`, `get_active_plan` | `update_user_settings`, `set_active_plan` |
| Body | `list_body_characteristics`, `list_body_characteristics_with_latest`, `list_default_body_characteristics`, `get_body_characteristic`, `list_body_stamps` | `create_body_characteristic`, `delete_body_characteristic`, `create_body_stamps`, `delete_body_stamp` |
| Workouts | `list_workouts`, `get_workout`, `get_workouts_report` | `create_workout`, `update_set`, `delete_workout` |
| Exercises | `list_exercises`, `list_default_exercises`, `get_default_exercise`, `list_exercise_catalogs`, `list_muscles`, `list_equipment` | `create_exercise`, `delete_exercise` |
| Plans | `list_plans`, `get_plan`, `list_plan_catalog`, `get_plan_from_catalog`, `check_plan_updates` | `create_plan`, `append_plan_days`, `delete_plan`, `fork_plan`, `publish_plan`, `unpublish_plan`, `pull_plan_updates`, `detach_plan` |
| Apple Health | `get_apple_health_daily`, `get_apple_health_metrics` (право `health:read`) | — |
| Diagnostics | `health_check` | — |

Полные описания и параметры доступны через MCP-протокол — твой Claude/Cursor покажет их автоматически.

### Права токена

Описание каждого инструмента называет ровно то право, которое проверяет backend (тест `ToolAccessContractTests`):

- `Scope: <право>` — маршрут с `RequireScope`, например `plans:read`, `body:write`, `health:read`;
- без scope и без авторизации — публичные справочники `list_default_exercises`, `get_default_exercise`, `list_exercise_catalogs`, `list_default_body_characteristics`;
- без scope, но с любым действующим PAT — `list_muscles`, `list_equipment`, `list_plan_catalog`, `get_plan_from_catalog`.

### Известные ограничения

- **03.11.2026: Docker 0.6.0 несовместим с явным `measurement: null`** в обычных силовых подходах: `list_plans` и `list_workouts` падают при десериализации, хотя API возвращает 200. До исправления и нового проверенного .NET-выпуска используйте Python-коннектор из QUICKSTART. Это не повреждение ваших планов.

- `get_workouts_report` и `check_plan_updates` возвращают только факт успешного вызова. Backend объявляет эти маршруты без типа ответа (`Produces(200)`), поэтому NSwag генерирует в `GymAssistant.Client` метод `void`, и тело (файл отчёта, `{hasUpdate, latestRevision}`) теряется. Исправление — на стороне backend: `Produces<T>` (или отдельный текстовый/JSON-ответ для отчёта), новая версия клиента и обновление пакета здесь. До этого используй `list_workouts`/`get_workout` и сравнение `ForkedFromRevision` с `Revision` исходного плана.
- `create_plan` — сырой upsert полного `PlanViewModel`: можно перезаписать существующий план. Безопасное создание и добавление дней пока есть только в локальном Python-сервере (`integrations/local-gymassistant`), план сведения — `docs/mcp-convergence-plan.md`.

## Дневные итоги Apple Health

В приложении iPhone подключить Apple Здоровье и включить сохранение в аккаунте. Для чтения через MCP создать PAT с отдельным правом `health:read`; старые токены его автоматически не получают. Период запроса — до 31 дня включительно (`from`, `to`, YYYY-MM-DD). Ответ содержит показатели, часовой пояс, время чтения на iPhone и получения сервером. `null` означает отсутствие данных, не ноль. Сегодняшние итоги могут дополняться позднее; несколько устройств не суммируются. MCP читает только загруженные на сервер данные и сам HealthKit не опрашивает.

## Troubleshooting

- **`FATAL: GYM_API_TOKEN is required`** — env-переменная не передалась в контейнер. Проверь защищённый `--env-file` в `docker run`.
- **`GYM_API_TOKEN has invalid shape`** — токен не соответствует формату `gma_` + 40-80 URL-safe символов. Сгенерируй новый.
- **HTTP 401 + `token expired`** — твой PAT просрочен. Создай новый в приложении: Настройки → API-токены.
- **HTTP 403** — у токена нет нужного scope. Создай новый PAT с расширенным набором scope'ов.
- **Cannot connect to Docker daemon** — Docker Desktop не запущен.
- **Cluster of "info: ..." in stderr** — это нормально, MCP-сервер логирует в stderr (stdout зарезервирован под MCP-протокол).

## Совместимость

- .NET 10
- `ModelContextProtocol` 1.3.x
- `GymAssistant.Client` 0.22.0 (NSwag-сгенерированный клиент)
- Сервер совместим с любым MCP-клиентом, поддерживающим stdio-транспорт

## Лицензия

MIT — см. [LICENSE](LICENSE).

### Измерения подходов и дополнение планов

Контракт клиента 0.17.0 передаёт `TrackingType`, `Measurement` и `ParentCode`.
Время хранится в секундах, дистанция — в метрах, помощь — в килограммах.
Наличие `Measurement` у конкретного подхода определяет его формат; старые
`Reps`/`Weight` без этого поля сохраняют прежний смысл.

`append_plan_days` добавляет только новые дни через отдельный endpoint, не заменяя
существующий план. Перед записью нужно прочитать план и передать его
`ExpectedUpdatedAt`. При 409 нужно заново прочитать план и согласовать изменения;
автоматического повтора POST нет.

Локальная Python-интеграция Mentoru описана отдельно в
[integrations/local-gymassistant](integrations/local-gymassistant/README.md).
Обновление файлов требует переподключения уже запущенного MCP-клиента.

## Метаданные каталога

Клиент 0.17.0 добавляет `GroupCode`, английские названия/описания/алиасы, `Media`,
`LoadConvention`, `IsUnilateral` и роли мышц. Значения передаются без пересчёта
исторических подходов. Для личного упражнения сохраняется его собственный ID.

`list_default_exercises(includeHidden: true)` включает скрытые общие шаблоны;
по умолчанию список и поиск их исключают. `get_default_exercise(globalId)` читает
шаблон по ID, даже если он скрыт. `CanonicalId` — справочная связь, инструмент
ничего не перепривязывает и не удаляет. Оба маршрута публичны.
