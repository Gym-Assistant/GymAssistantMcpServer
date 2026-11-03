# Подключить GymAssistant к Codex · v0.7.0

Ваш ассистент сможет читать тренировки и работать с планами в пределах прав личного API-токена. Это локальный MCP-сервер для ИИ-приложений, которые умеют запускать stdio-команду. Токен GymAssistant — доступ к вашему аккаунту, не ключ ИИ-провайдера. Не отправляйте его в чат.

## 1. Получить токен

В GymAssistant откройте **Настройки → API-токены** и создайте личный токен. Для чтения профиля, планов, тренировок и упражнений выберите `profile:read`, `plans:read`, `workouts:read`, `exercises:read`. Для замеров добавьте `body:read`, для Health — `health:read`. Для создания или дополнения планов добавьте `plans:write`. Остальные права записи для первого подключения не нужны.

Токен можно хранить заранее. Когда платный API доступ будет активирован на backend, действующий grant, в том числе подарок, будет проверяться **на каждом API-запросе**. По окончании grant токен сохраняется; после продления доступ возвращается без его перевыпуска. Пока enforcement на production выключен, это подготовленная модель, а не уже действующее ограничение. Тариф и цену уточняйте в приложении; эта инструкция не закрепляет сумму.

## 2. Установить (проверено на macOS, Python 3.14)

Нужны Git, Python 3.14 и Codex на macOS. Публичные исходники и зависимости PyPI не требуют приватного GitHub-доступа. Команда ниже устанавливает **фиксированный выпуск v0.7.0**:

```sh
git clone --branch v0.7.0 --depth 1 https://github.com/Gym-Assistant/GymAssistantMcpServer.git
cd GymAssistantMcpServer
python3 --version
python3 integrations/local-gymassistant/install.py "$HOME/.local/share/gymassistant-mcp"
python3 -m venv "$HOME/.local/share/gymassistant-mcp/.venv"
"$HOME/.local/share/gymassistant-mcp/.venv/bin/python" -m pip install -r "$HOME/.local/share/gymassistant-mcp/requirements.txt"
```

Проверьте, что `python3` — 3.14. Установщик сохраняет прежние управляемые модули в `.backups` и не заменяет существующие `.env`, `run.sh` и пользовательские файлы. Для следующего выпуска откройте его инструкцию по новому тегу и повторите установку, затем переподключите MCP.

## 3. Сохранить токен без истории команд

Команда спрашивает токен скрыто и создаёт файл только для владельца. Существующий файл не перезаписывается.

```sh
python3 - <<'PY'
import getpass, os
from pathlib import Path
p = Path.home() / '.local/share/gymassistant-mcp/.env'
if p.exists():
    raise SystemExit('Файл уже существует; измените его локально в редакторе.')
token = getpass.getpass('Personal API Token GymAssistant: ').strip()
if not token.startswith('gma_') or any(c.isspace() for c in token):
    raise SystemExit('Нужен личный токен GymAssistant (gma_...).')
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('GYM_API_TOKEN=' + token + '\n')
print('Токен сохранён локально.')
PY
```

Если у вас уже есть защищённый env-файл, укажите его абсолютный путь через `GYM_MCP_ENV_FILE` в настройках MCP-клиента. Не копируйте токен в JSON-конфиг клиента. `GYM_API_URL` по умолчанию `https://gym-assistant.ru/api`.

## 4. Подключить Codex

Добавьте локальный сервер командой Codex. Токен остаётся в защищённом `.env` из шага 3; в конфигурации Codex хранится только путь к запуску:

```sh
codex mcp add gymassistant -- "$HOME/.local/share/gymassistant-mcp/run.sh"
codex mcp list
```

Если команда `codex` недоступна, добавьте в `~/.codex/config.toml` вручную (подставьте своё имя пользователя):

```toml
[mcp_servers.gymassistant]
command = "/Users/ВАШЕ_ИМЯ/.local/share/gymassistant-mcp/run.sh"
```

В Codex desktop перезапустите MCP-подключение. Откройте `/mcp` и убедитесь, что `gymassistant` доступен. Затем попросите: «Покажи список инструментов GymAssistant и вызови `gym_me` и `gym_plans`. Пока ничего не записывай». Проверены `tools/list` и чтения; результат профиля и планов виден только в вашем Codex. [Официальная инструкция Codex по MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) описывает ту же команду и конфигурацию. Windows и интерфейсы других ИИ-клиентов для этого выпуска не проверены.

Сервер выдаёт 59 имён: 15 привычных `gym_*` и 44 имени прежнего .NET MCP (`get_me`, `list_plans` и другие) в **том же процессе**. Чтения доступны по scopes токена. Безопасное создание — `gym_create_plan`, дополнение только с актуальным `expected_updated_at` — `gym_append_plan_days`. Если ответ записи `unknown` или произошёл таймаут, сначала прочитайте объект по возвращённому ID; не повторяйте запись вслепую. Сырой `create_plan`, удаление, публикация и другие старые мутации выключены по умолчанию.

## Ошибки и отключение

- `401`: личный токен недействителен, истёк или отозван. Проверьте его в приложении.
- `403` без `subscription_required`: токен действителен, но не хватает нужного scope. Проверьте права токена; повторный вход в Codex не поможет.
- `403` с кодом `subscription_required`: требуется действующий Plus/Pro/Premium grant со scope `all`; подарок подходит, trial и VK-only — нет. Backend сохраняет PAT, и после продления тот же токен снова работает. На 03.11.2026 этот отдельный production-флаг **выключен**; сообщение описывает поведение после его включения, а не текущую оплату.
- `409` при дополнении плана: перечитайте план и согласуйте изменения.
- Нет инструментов: проверьте абсолютный путь, Python окружение и перезапуск ИИ-клиента.
- Health пустой: проверьте синхронизацию iPhone; `null` означает отсутствие данных, не ноль.

Проверка чтений без вывода персональных ответов из каталога исходников:

```sh
GYM_MCP_ENV_FILE="$HOME/.local/share/gymassistant-mcp/.env" \
  "$HOME/.local/share/gymassistant-mcp/.venv/bin/python" scripts/check-readonly.py \
  -- "$HOME/.local/share/gymassistant-mcp/run.sh"
```

Для отключения отзовите токен в GymAssistant и удалите подключение из ИИ-клиента. Для отката обновления используйте каталог `.backups/repo-...`, который напечатал установщик; не удаляйте `.env` или планы. Удалённый MCP пока не опубликован и не нужен для этого пути.
