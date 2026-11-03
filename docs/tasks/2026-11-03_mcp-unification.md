# Один безопасный MCP GymAssistant · 03.11.2026

## Цель и границы

Эпик: один поддерживаемый коннектор для текущего API, локальный stdio для нового пользователя без приватного GitHub-доступа, сохранение имён действующих MCP-клиентов и подготовка удалённого Streamable HTTP с изоляцией аккаунтов. База репозитория `d62e3f5`, переданный branch commit `ded0130`; опубликованный .NET Docker `0.6.0` — исторический baseline. Candidate — ветка `feature/mcp-current-api` поверх `ded0130`; целевой локальный выпуск `v0.7.0`.

Внутри scope: код одного runtime, public dependency install, тесты, read-only production API smoke, синтетические записи, HTTP прототип и конфигурация Selectel. Владелец отдельно разрешил commit/PR/CI/merge/tag/release локального stdio, чистую установку из опубликованного тега и подключение в Codex с личным PAT вне чата и репозитория. Вне scope: backend production, оплата, включение entitlement gate, публичный HTTP endpoint, админка, RuStore.

## Выбор runtime и фактический baseline

Выбран Python/FastMCP. Его 15 исходных инструментов прошли 88 unit, два реальных stdio synthetic и read-only текущего API; он сохраняет `measurement:null` в силовых подходах и умеет безопасно создать/дополнить план. .NET Docker `0.6.0` имел 44 имени и работал на части synthetic/live чтений, но live `list_plans`/`list_workouts` падали на `measurement:null`. Анонимный GHCR token exchange вернул 401; локальный NuGet restore 401/403. Открытие registry само по себе не исправляет контракт. Не подменяли пакет или выключали nullability. Невлитые GA-057/086/089/090 изменения .NET просмотрены как отдельные ветки, не переигрывались и не включены скрытно.

Из репозитория удалён .NET runtime, тестовый проект, Dockerfile и приватная NuGet-конфигурация. Git-история сохранена. Один Python процесс регистрирует прежние 15 `gym_*` и 44 совместимых имени .NET. Все чтения используют текущий JSON напрямую, включая явный `null` и будущие поля. Старые прямые upsert/удаления/публикации зарегистрированы, но по умолчанию fail-closed; локальный владелец может включить `GYM_ENABLE_LEGACY_WRITES=1`. `create_plan` даже тогда отклоняет уже существующий ID, `append_plan_days` требует `expectedUpdatedAt`, копирует исходное дерево и проверяет результат. Рекомендуемые записи — `gym_create_plan` и `gym_append_plan_days`. Сервер не повторяет мутации после 5xx/таймаута/неразборчивого ответа, возвращает `unknown` и ID для readback.

Ограничение совместимости: имена всех 44 старых инструментов есть, но часть старых сырых записей теперь требует opt-in; `get_plan`/`get_workout` дополнительно сверяют владельца через `profile:read`. Это осознанный безопасный переход, а не прозрачная побайтовая эквивалентность. `get_workouts_report` по прежнему возвращает только успешность, без файла. Миграция действующей установки проводится после выпуска с сохранением ключей и откатом.

## Подписка и API

Backend gate принадлежит отдельному пакету админки/подписок, не дублируется в MCP. В его текущем рабочем дереве `Billing:ApiTokenSubscriptionGateEnabled` по умолчанию OFF; когда его включат, каждый PAT запрос требует действующий Plus/Pro/Premium grant со scope `all`, подарок подходит, trial/VK-only не подходят. При окончании доступа PAT не отзывается; сервер отвечает HTTP 403 JSON `{"error":"subscription_required"}` и `WWW-Authenticate: Bearer error="insufficient_scope", error_description="subscription_required"`. Продление возвращает доступ тем же токеном. JWT-сессия приложения и создание PAT отдельно остаются доступными. Точная цена и код тарифа в MCP не зашиты. Кандидат backend gate пока не опубликован и может измениться в активном чате.

`http_transport.py` распознаёт только machine code `subscription_required` (также в поле `code` для совместимости), выдаёт фиксированный текст без тела ответа. 401 недействительного PAT и обычный 403 scope остаются отдельными. Ни один отказ не вызывает token refresh или повтор записи. Удалённый адаптер на `subscription_required` даёт 403, а не `invalid_token`.

## Удалённый HTTP: подготовка, не выпуск

`remote_http.py` использует тот же `build_server(remote=True)` и реестр инструментов, `stateless_http=True`. Каждый HTTP-запрос требует ровно один Bearer PAT `gma_*`; он проверяется вызовом backend `/auth/me`, без общего сервисного PAT или кэша. Токен живёт только в ContextVar запроса; параллельные синтетические пользователи и последовательные вызовы разных PAT не смешались. Security review нашёл кэш каталога в замыкании общей регистрации: первый пользователь мог передать свой счётчик упражнений второму. Кэш удалён, добавлен regression test с разными каталогами двух PAT. Remote режим принудительно отключает сырой legacy write opt-in и отказывается запускаться с общим `GYM_API_TOKEN`/`GYM_HEALTH_API_TOKEN`. Loopback bind по умолчанию; внешний bind требует явного флага и HTTPS public URL, с проверкой Host/Origin. Это ручная PAT авторизация для клиентов, умеющих передать Bearer header; OAuth discovery/one-click авторизация сторонних клиентов отдельно не доказана.

Для Selectel подготовлены `deploy/selectel/Dockerfile.http`, пример ограниченного контейнера и фрагмент nginx. Они **не применены**. Read-only срез `gym-app` 03.11: 2 vCPU, 3915 MiB RAM, около 3014 MiB available и swap 1023 MiB без использования; API использовал 240 MiB, фронт 3.5 MiB, nginx 7.8 MiB, promtail 70.5 MiB. Предлагаемый MCP budget 0.5 CPU / 256 MiB, без host port, только `gym-app_default`, non-root, read-only FS, без capabilities. Оценка достаточности — предварительная; нужна нагрузочная проверка и оценка backend PAT проверки на каждый запрос. Новый VPS по этой оценке не требуется.

Порядок будущего выпуска: точный MCP commit и CI → независимое security review публичного образа и зависимостей → backend PAT gate candidate/contract с пакетом подписок → изолированный backend/MCP тест с gifts, expiry, renewal, scopes и двумя пользователями → проверенная сборка amd64 и pinned image digest → отдельно согласованный backend release с data gates → отдельно согласованное включение флага для пользователей → отдельное MCP HTTP окно с TLS/reverse proxy, лимитами и мониторингом → smoke no-token/expired/scope/gift/parallel-owner, без реальных записей → наблюдение. Пока любой gate не пройден, остаётся локальный stdio. Откат HTTP: убрать только новый location, остановить MCP контейнер, сохранить backend и данные. Откат PAT gate: выключить отдельный флаг после проверки текущего state; токены не пересоздавать. Старый Docker `0.6.0` не считается безопасным общим rollback из-за `measurement:null`.

## Проверки кандидата

| Среда | Сценарий | Итог |
|---|---|---|
| Python 3.14, macOS, loopback synthetic | 98 unit: имена44, чужой owner, expiry/scope/подписка, редактирование ошибок, запрет PAT redirect, без retry | PASS |
| Новый stdio process, loopback synthetic | 59 tools; legacy `measurement:null`, Health null, локальная дата и рекорды | PASS |
| Новый stdio process, loopback synthetic | План2 дня/6 подходов, append7 дней, 409/500 unknown, backup0600, сохранение дерева | PASS |
| Отдельная чистая временная установка (удалена после проверки) | PyPI dependencies без GitHub auth, оба stdio сценария на финальном дереве | PASS |
| Текущий source stdio, production API, только GET | 10 вызовов: `gym_*` и соответствующие aliases профиля/каталога/планов/тренировок/Health | PASS; ответы/токены не выводились |
| ASGI Streamable HTTP, loopback synthetic | разные PAT параллельно и последовательно с разными каталогами, invalid401, scope403, subscription403, renewal тем же PAT | PASS; public endpoint не тестировался |
| Docker Desktop, local arm64 + linux/amd64 | Python3.14 image build, non-root/read-only/cap-drop import и app construction | PASS; реальные контейнерные запросы к backend не проводились |

Не проверены Windows/Linux установка, UI каждого стороннего ИИ-клиента, публичная TLS-сеть, полный набор 44 aliases на live API, подаренный entitlement на точном объединённом backend/MCP SHA, нагрузка и production activation. Чистая установка использовала временный каталог; API smoke запускался из текущего source. Пользовательская установка не изменена. Токены и реальные payload не попали в отчёты.

## Следующее действие

Выполнить CI/PR и выпуск `v0.7.0`, затем проверить чистую установку именно из опубликованного тега, подключение Codex, `tools/list` и безопасное чтение. Удалённый сервис и backend gate остаются отдельными release/activation решениями. Один HTML-отчёт: `docs/research/mcp-unification-2026-11-03/index.html`.
