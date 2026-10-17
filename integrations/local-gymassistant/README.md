# Локальный MCP GymAssistant

Фактически подключённый в Codex сервер запускается из `~/tools/gymassistant-mcp/run.sh`. Он независим от Docker-образа .NET MCP. Этот модуль добавляет чтение Apple Health, сохраняя существующие инструменты.

## Установка

Сначала сохранить резервную копию `server.py` и `run.sh`. Скопировать `health_tools.py` рядом с `server.py`. Перед блоком запуска добавить:

```python
from health_tools import register_health_tools
register_health_tools(mcp, _api_get)
```

Используется уже настроенный `GYM_API_TOKEN`. Для отдельного узкого доступа можно задать `GYM_HEALTH_API_TOKEN` с правами `profile:read` и `health:read`, сохранив основной токен. Тогда обёртка `_api_get` принимает необязательный аргумент `token`, а регистрация выглядит так:

```python
from health_tools import register_health_tools, same_account_reader
health_token = _ENV.get("GYM_HEALTH_API_TOKEN")
health_reader = same_account_reader(
    _api_get, lambda path, params=None: _api_get(path, params, health_token)
) if health_token else _api_get
register_health_tools(mcp, health_reader)
```

`same_account_reader` перед чтением сопоставляет владельцев обоих токенов через `/auth/me` и не позволяет смешать Health другого аккаунта с тренировками. Токен должен принадлежать тому же аккаунту, что импортирует Health, и иметь отдельное право `health:read`. Старые токены не расширяются автоматически. Не записывать токен в репозиторий или журнал.

После установки переподключить MCP в клиенте: существующий процесс не перечитывает исходники. Проверка только через импорт Python не заменяет `initialize`, `tools/list` и настоящий `tools/call` в новом stdio-процессе.

## Проверка

Запустить `python -m unittest discover -s integrations/local-gymassistant -v` окружением с MCP SDK. Проверяются диапазон дат, отсутствие запросов при неправильном диапазоне, сохранение null и свежести данных. Серверные проверки дополнительно покрывают авторизацию, разделение аккаунтов и повторный импорт.

Для проверки установленного процесса: `python integrations/local-gymassistant/verify_stdio.py /absolute/path/to/run.sh`. Проверка использует локальный синтетический API и тестовый PAT, не обращается к production.
