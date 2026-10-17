"""Чтение дневных итогов Apple Health через существующий GymAssistant MCP."""
from datetime import date
from mcp.types import ToolAnnotations


def register_health_tools(mcp, api_get):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    def gym_health_daily(from_date: str, to_date: str) -> list[dict]:
        """Дневные итоги Apple Health владельца аккаунта. Scope: health:read.

        from_date/to_date: YYYY-MM-DD включительно, максимум 31 день за запрос.
        snapshot.values: steps — шаги; sleepMinutes — минуты сна; energy — съеденные
        ккал; activeEnergy/basalEnergy — активные/базовые ккал; protein/fat/carbs —
        граммы; weight — кг. snapshot.timeZone — зона дня, readAt — чтение на iPhone,
        receivedAt — получение сервером. null означает отсутствие доступных данных,
        а не ноль. Пустой список означает отсутствие загруженных дней. Сегодняшний
        день может быть неполным; время получения не гарантирует полноту Health.
        Для дня возвращается один свежий снимок, устройства не суммируются.
        """
        start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
        if start.isoformat() != from_date or end.isoformat() != to_date:
            raise ValueError('Укажите даты в формате YYYY-MM-DD.')
        if not 0 <= (end - start).days < 31:
            raise ValueError('Период должен составлять от 1 до 31 дня включительно.')
        return api_get('/health/apple/daily', {'from': from_date, 'to': to_date})


def same_account_reader(primary_get, health_get):
    """Не смешивает Health другого аккаунта с тренировками основного токена."""
    def read(path, params=None):
        primary_id = primary_get('/auth/me').get('id')
        health_id = health_get('/auth/me').get('id')
        if not primary_id or primary_id != health_id:
            raise ValueError('Токены тренировок и Apple Health относятся к разным аккаунтам.')
        return health_get(path, params)
    return read
