"""Compatibility names from the former .NET MCP, served by the Python runtime.

The default surface keeps all reads and the two safe plan operations. Legacy raw
mutations require an explicit local opt-in; they still enforce owner checks and
never retry. No second server or generated private NuGet client is involved.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from mcp.types import ToolAnnotations
from pydantic import Field

from http_transport import ApiError, InvalidResponse
from plan_tools import _backup_plan, _owned_plan, _owner, _preserved


READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)

COMPAT_TOOL_NAMES = set('''append_plan_days check_plan_updates create_body_characteristic
create_body_stamps create_exercise create_plan create_workout delete_body_characteristic
delete_body_stamp delete_exercise delete_plan delete_workout detach_plan fork_plan
get_active_plan get_apple_health_daily get_apple_health_metrics get_body_characteristic
get_default_exercise get_me get_plan get_plan_from_catalog get_user_settings get_workout
get_workouts_report health_check list_body_characteristics
list_body_characteristics_with_latest list_body_stamps list_default_body_characteristics
list_default_exercises list_equipment list_exercise_catalogs list_exercises list_muscles
list_plan_catalog list_plans list_workouts publish_plan pull_plan_updates set_active_plan
unpublish_plan update_set update_user_settings'''.split())


def _id(value) -> str:
    return str(UUID(str(value)))


def _page(offset, limit, max_limit=200):
    if offset < 0 or not 1 <= limit <= max_limit:
        raise ValueError(f'offset ≥ 0 и limit 1–{max_limit}.')
    return {'offset': offset, 'limit': limit}


def _owned_workout(api_get, workout_id, owner):
    workout_id = _id(workout_id)
    try:
        workout = api_get('/workouts/' + workout_id)
    except ApiError as error:
        if error.status == 404:
            raise ValueError('Личная тренировка с таким ID не найдена.') from None
        raise
    if not isinstance(workout, dict) or _id_or_none(workout.get('id')) != workout_id or \
            _id_or_none(workout.get('createdById')) != owner or workout.get('isDeleted'):
        raise ValueError('Личная тренировка с таким ID не найдена.')
    return workout


def _id_or_none(value):
    try:
        return _id(value)
    except (ValueError, TypeError, AttributeError):
        return None


def _write(transport, method, path, body=None, *, identifier=None, response=True):
    try:
        return transport.write(method, path, body, json_response=response)
    except ApiError as error:
        if error.code == 'subscription_required':
            raise ValueError(str(error)) from None
        if error.status is None or error.status >= 500:
            return {'status': 'unknown', 'id': identifier,
                    'message': 'Исход записи не подтверждён. Прочитайте объект перед любым повтором.'}
        raise ValueError(f'GymAssistant API: HTTP {error.status}; запись не повторялась.') from None
    except InvalidResponse:
        return {'status': 'unknown', 'id': identifier,
                'message': 'Ответ записи не распознан. Прочитайте объект перед любым повтором.'}


def _legacy_enabled(enabled):
    if not enabled:
        raise ValueError('Сырой инструмент записи выключен. Используйте gym_create_plan/gym_append_plan_days '
                         'или явно включите GYM_ENABLE_LEGACY_WRITES=1 в локальной конфигурации.')


def register_compat_tools(mcp, transport, health_get, *, legacy_writes=False):
    api_get = transport.get

    @mcp.tool(annotations=READ)
    def get_me() -> dict:
        """Профиль владельца токена. Scope: profile:read."""
        return api_get('/auth/me')

    @mcp.tool(annotations=READ)
    def health_check() -> dict:
        """Проверка подключения и PAT. Scope: profile:read."""
        me = api_get('/auth/me')
        return {'status': 'ok', 'userId': me.get('id')}

    @mcp.tool(annotations=READ)
    def get_user_settings() -> dict:
        """Настройки владельца. Scope: profile:read."""
        return api_get('/user/settings')

    @mcp.tool(annotations=READ)
    def get_active_plan() -> dict | None:
        """Активный план владельца. Scope: plans:read."""
        return api_get('/user/active-plan')

    @mcp.tool(annotations=READ)
    def list_workouts(offset: Annotated[int, Field(ge=0)] = 0,
                      limit: Annotated[int, Field(ge=1, le=200)] = 30) -> dict:
        """Полные тренировки и подходы, включая measurement:null и заметки. Scope: workouts:read."""
        return api_get('/workouts', _page(offset, limit))

    @mcp.tool(annotations=READ)
    def get_workout(id: UUID) -> dict:
        """Личная тренировка по ID, включая комментарии и измерения. Scopes: workouts:read, profile:read."""
        return _owned_workout(api_get, id, _owner(api_get))

    @mcp.tool(annotations=READ)
    def get_workouts_report(from_: Annotated[str | None, Field(validation_alias='from')] = None,
                            to: str | None = None, format: str = 'txt') -> dict:
        """Проверить доступность экспорта; файл в MCP не передаётся. Scope: workouts:read."""
        for value in (from_, to):
            if value:
                datetime.fromisoformat(value.replace('Z', '+00:00'))
        return transport.request('GET', '/reports/workouts', params={'from': from_, 'to': to,
                                 'format': format}, json_response=False)

    @mcp.tool(annotations=READ)
    def list_plans(offset: Annotated[int, Field(ge=0)] = 0,
                   limit: Annotated[int, Field(ge=1, le=100)] = 50) -> dict:
        """Личные планы со всеми упражнениями. Scope: plans:read."""
        return api_get('/plans', _page(offset, limit, 100))

    @mcp.tool(annotations=READ)
    def get_plan(id: UUID) -> dict:
        """Личный план по ID; чужой неопубликованный план скрыт. Scopes: plans:read, profile:read."""
        return _owned_plan(api_get, id, _owner(api_get))

    @mcp.tool(annotations=READ)
    def list_plan_catalog(offset: Annotated[int, Field(ge=0)] = 0,
                          limit: Annotated[int, Field(ge=1, le=100)] = 50,
                          search: str | None = None) -> dict:
        """Каталог опубликованных планов. Нужен действующий PAT."""
        return api_get('/plans/catalog', {**_page(offset, limit, 100), 'search': search})

    @mcp.tool(annotations=READ)
    def get_plan_from_catalog(id: UUID) -> dict:
        """Опубликованный план из каталога. Нужен действующий PAT."""
        return api_get('/plans/catalog/' + _id(id))

    @mcp.tool(annotations=READ)
    def check_plan_updates(id: UUID) -> dict:
        """Наличие обновлений своего форка. Scopes: plans:read, profile:read."""
        _owned_plan(api_get, id, _owner(api_get))
        return api_get('/plans/' + _id(id) + '/updates/available')

    @mcp.tool(annotations=READ)
    def list_exercises(offset: Annotated[int, Field(ge=0)] = 0,
                       limit: Annotated[int, Field(ge=1, le=200)] = 200) -> dict:
        """Личные упражнения и метаданные шаблонов. Scope: exercises:read."""
        return api_get('/exercises', _page(offset, limit))

    @mcp.tool(annotations=READ)
    def list_default_exercises(offset: Annotated[int, Field(ge=0)] = 0,
                               limit: Annotated[int, Field(ge=1, le=200)] = 200,
                               search: str | None = None, muscleCode: str | None = None,
                               equipmentCode: str | None = None, includeHidden: bool = False) -> dict:
        """Общий каталог, включая скрытые ссылки истории по запросу. Публичный справочник."""
        return api_get('/exercises/defaults', {**_page(offset, limit), 'search': search,
                       'muscleCode': muscleCode, 'equipmentCode': equipmentCode,
                       'includeHidden': str(includeHidden).lower()})

    @mcp.tool(annotations=READ)
    def get_default_exercise(globalId: UUID) -> dict:
        """Общий шаблон по globalId, включая скрытый. Публичный справочник."""
        return api_get('/exercises/defaults/' + _id(globalId))

    @mcp.tool(annotations=READ)
    def list_exercise_catalogs() -> dict:
        """Старый общий справочник мышц и оборудования. Публичный справочник."""
        return api_get('/exercises/catalogs')

    @mcp.tool(annotations=READ)
    def list_muscles() -> list[dict]:
        """Справочник мышц. Нужен действующий PAT."""
        return api_get('/muscles')

    @mcp.tool(annotations=READ)
    def list_equipment() -> list[dict]:
        """Справочник оборудования. Нужен действующий PAT."""
        return api_get('/equipment')

    @mcp.tool(annotations=READ)
    def list_body_characteristics(offset: Annotated[int, Field(ge=0)] = 0,
                                  limit: Annotated[int, Field(ge=1, le=200)] = 100) -> dict:
        """Личные характеристики тела. Scope: body:read."""
        return api_get('/body/characteristics', _page(offset, limit))

    @mcp.tool(annotations=READ)
    def list_body_characteristics_with_latest(asOf: str | None = None) -> list[dict]:
        """Последний замер по характеристике на дату asOf. Scope: body:read."""
        as_of = asOf or datetime.now().astimezone().isoformat()
        datetime.fromisoformat(as_of.replace('Z', '+00:00'))
        return api_get('/body/characteristics/with-latest', {'asOf': as_of})

    @mcp.tool(annotations=READ)
    def list_default_body_characteristics() -> list[dict]:
        """Стандартные характеристики тела. Публичный справочник."""
        return api_get('/body/default-characteristics')

    @mcp.tool(annotations=READ)
    def get_body_characteristic(id: UUID) -> dict:
        """Личная характеристика и история. Scope: body:read."""
        return api_get('/body/characteristics/' + _id(id))

    @mcp.tool(annotations=READ)
    def list_body_stamps(offset: Annotated[int, Field(ge=0)] = 0,
                         limit: Annotated[int, Field(ge=1, le=200)] = 200) -> dict:
        """Замеры тела. Scope: body:read."""
        return api_get('/body/stamps', _page(offset, limit))

    @mcp.tool(annotations=READ)
    def get_apple_health_daily(from_: Annotated[str, Field(validation_alias='from')], to: str) -> list[dict]:
        """Дневные итоги Health до 31 дня, null остаётся отсутствием. Scope: health:read."""
        start, end = date.fromisoformat(from_), date.fromisoformat(to)
        if start.isoformat() != from_ or end.isoformat() != to or not 0 <= (end - start).days < 31:
            raise ValueError('Нужен период от 1 до 31 дня в формате YYYY-MM-DD.')
        return health_get('/health/apple/daily', {'from': from_, 'to': to})

    @mcp.tool(annotations=READ)
    def get_apple_health_metrics() -> dict:
        """Ключи, единицы и агрегация Apple Health. Scope: health:read."""
        return health_get('/health/apple/metrics')

    # Raw .NET mutation names remain available to existing clients only when the
    # local owner explicitly enables them. All mutations use the same transport.
    @mcp.tool(annotations=WRITE)
    def update_user_settings(body: dict) -> dict:
        """Полная замена настроек. Scope: profile:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        current = api_get('/user/settings')
        if not isinstance(body, dict) or not isinstance(current, dict) or any(k not in body for k in current):
            raise ValueError('Передайте полные настройки из get_user_settings.')
        return _write(transport, 'PUT', '/user/settings', body)

    @mcp.tool(annotations=WRITE)
    def set_active_plan(planId: UUID | None = None) -> dict:
        """Назначить личный активный план. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        if planId is not None:
            _owned_plan(api_get, planId, _owner(api_get))
        return _write(transport, 'PUT', '/user/active-plan', {'planId': _id(planId) if planId else None})

    @mcp.tool(annotations=WRITE)
    def create_plan(body: dict) -> dict:
        """Сырой новый план с полным деревом; существующий ID запрещён. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        if not isinstance(body, dict) or not body.get('id') or not body.get('name'):
            raise ValueError('Нужен полный PlanViewModel с новым ID и названием.')
        plan_id = _id(body['id'])
        if UUID(plan_id).version != 4 or body.get('isDeleted') or body.get('isPublished'):
            raise ValueError('Нужен новый UUIDv4 и неопубликованный личный план.')
        owner = _owner(api_get)
        try:
            api_get('/plans/' + plan_id)
        except ApiError as error:
            if error.status != 404:
                raise
        else:
            raise ValueError('План с этим ID уже существует; upsert запрещён.')
        body = {**body, 'id': plan_id, 'authorUserId': owner, 'createdById': owner,
                'isDeleted': False, 'isPublished': False}
        return _write(transport, 'POST', '/plans', body, identifier=plan_id, response=False)

    @mcp.tool(annotations=WRITE)
    def append_plan_days(id: UUID, body: dict) -> dict:
        """Добавить дни к своему плану с expectedUpdatedAt. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        original = _owned_plan(api_get, id, _owner(api_get))
        if not isinstance(body, dict) or body.get('expectedUpdatedAt') != original.get('updatedAt'):
            raise ValueError('План изменился; перечитайте get_plan и передайте свежий expectedUpdatedAt.')
        templates, exercises = body.get('templates'), body.get('exercises')
        if not isinstance(templates, list) or not templates or not isinstance(exercises, list):
            raise ValueError('Нужны только новые templates и exercises.')
        old_ids = {item.get('id') for key in ('templates', 'exercises') for item in original.get(key, [])}
        new_ids = [item.get('id') for item in templates + exercises if isinstance(item, dict)]
        if len(new_ids) != len(templates) + len(exercises) or None in new_ids or \
                len(set(new_ids)) != len(new_ids) or old_ids.intersection(new_ids):
            raise ValueError('ID новых дней и упражнений должны быть уникальны.')
        _backup_plan(original, body)
        saved = _write(transport, 'POST', '/plans/' + _id(id) + '/days', body, identifier=_id(id))
        if saved.get('status') == 'unknown':
            return {**saved, 'added_day_ids': [item['id'] for item in templates]}
        if not _preserved(original, saved, [item['id'] for item in templates]):
            return {'status': 'unknown', 'id': _id(id), 'added_day_ids': [item['id'] for item in templates]}
        return saved

    @mcp.tool(annotations=WRITE)
    def fork_plan(id: UUID) -> dict:
        """Сделать личный форк опубликованного плана. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        api_get('/plans/catalog/' + _id(id))
        return _write(transport, 'POST', '/plans/' + _id(id) + '/fork', identifier=_id(id))

    def own_plan_action(action, id):
        _legacy_enabled(legacy_writes)
        _owned_plan(api_get, id, _owner(api_get))
        return _write(transport, 'POST', '/plans/' + _id(id) + '/' + action, identifier=_id(id))

    @mcp.tool(annotations=DESTRUCTIVE)
    def publish_plan(id: UUID) -> dict:
        """Опубликовать свой план. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        return own_plan_action('publish', id)

    @mcp.tool(annotations=DESTRUCTIVE)
    def unpublish_plan(id: UUID) -> dict:
        """Снять свой план с публикации. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        return own_plan_action('unpublish', id)

    @mcp.tool(annotations=DESTRUCTIVE)
    def pull_plan_updates(id: UUID) -> dict:
        """Обновить свой форк. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        return own_plan_action('pull', id)

    @mcp.tool(annotations=DESTRUCTIVE)
    def detach_plan(id: UUID) -> dict:
        """Отвязать свой форк. Scope: plans:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        return own_plan_action('detach', id)

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_plan(id: UUID) -> dict:
        """Удалить свой план. Scope: plans:delete. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        _owned_plan(api_get, id, _owner(api_get))
        return _write(transport, 'DELETE', '/plans/' + _id(id), identifier=_id(id))

    @mcp.tool(annotations=DESTRUCTIVE)
    def create_workout(body: dict) -> dict:
        """Сырой upsert тренировки. Scope: workouts:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        if not isinstance(body, dict) or not body.get('id'):
            raise ValueError('Нужен полный WorkoutViewModel с ID.')
        owner = _owner(api_get)
        workout_id = _id(body['id'])
        try:
            existing = api_get('/workouts/' + workout_id)
        except ApiError as error:
            if error.status != 404:
                raise
            if UUID(workout_id).version != 4:
                raise ValueError('Для новой тренировки нужен UUIDv4.') from None
        else:
            if _id_or_none(existing.get('createdById')) != owner:
                raise ValueError('Личная тренировка с таким ID не найдена.')
        body = {**body, 'id': workout_id, 'createdById': owner}
        return _write(transport, 'POST', '/workout', body, identifier=workout_id, response=False)

    @mcp.tool(annotations=WRITE)
    def update_set(workoutId: UUID, sessionId: UUID, setId: UUID, body: dict) -> dict:
        """Частичное изменение своего подхода. Scope: workouts:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        workout = _owned_workout(api_get, workoutId, _owner(api_get))
        session = next((s for s in workout.get('trainSessions', []) if _id_or_none(s.get('id')) == _id(sessionId)), None)
        if session is None or not any(_id_or_none(s.get('id')) == _id(setId) for s in session.get('sets', [])):
            raise ValueError('Подход не найден в личной тренировке.')
        if not isinstance(body, dict) or not body:
            raise ValueError('Нужно указать поля подхода.')
        path = f'/workouts/{_id(workoutId)}/sessions/{_id(sessionId)}/sets/{_id(setId)}'
        return _write(transport, 'PATCH', path, body, identifier=_id(setId))

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_workout(id: UUID) -> dict:
        """Удалить свою тренировку. Scope: workouts:delete. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        _owned_workout(api_get, id, _owner(api_get))
        return _write(transport, 'DELETE', '/workouts/' + _id(id), identifier=_id(id))

    @mcp.tool(annotations=DESTRUCTIVE)
    def create_exercise(body: dict) -> dict:
        """Сырой upsert личного упражнения. Scope: exercises:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        if not isinstance(body, dict) or not body.get('id'):
            raise ValueError('Нужен полный ExerciseViewModel с личным ID.')
        exercise_id = _id(body['id'])
        catalog = api_get('/exercises', _page(0, 200))
        existing = next((e for e in catalog.get('items', []) if _id_or_none(e.get('id')) == exercise_id), None)
        if existing is None and UUID(exercise_id).version != 4:
            raise ValueError('Для нового упражнения нужен UUIDv4.')
        if existing and (body.get('templateRevision') != existing.get('templateRevision') or
                         body.get('templateOverrides') != existing.get('templateOverrides')):
            raise ValueError('Сохраните templateRevision и templateOverrides из list_exercises.')
        return _write(transport, 'POST', '/exercises', body, identifier=exercise_id, response=False)

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_exercise(id: UUID) -> dict:
        """Удалить личное упражнение. Scope: exercises:delete. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        catalog = api_get('/exercises', _page(0, 200))
        if not any(_id_or_none(e.get('id')) == _id(id) for e in catalog.get('items', [])):
            raise ValueError('Личное упражнение не найдено.')
        return _write(transport, 'DELETE', '/exercises/' + _id(id), identifier=_id(id))

    @mcp.tool(annotations=DESTRUCTIVE)
    def create_body_characteristic(body: dict) -> dict:
        """Upsert личной характеристики. Scope: body:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        if not isinstance(body, dict) or not body.get('id'):
            raise ValueError('Нужен полный объект с ID.')
        characteristic_id = _id(body['id'])
        try:
            api_get('/body/characteristics/' + characteristic_id)
        except ApiError as error:
            if error.status != 404:
                raise
            if UUID(characteristic_id).version != 4:
                raise ValueError('Для новой характеристики нужен UUIDv4.') from None
        return _write(transport, 'POST', '/body/characteristic', body, identifier=characteristic_id)

    @mcp.tool(annotations=DESTRUCTIVE)
    def create_body_stamps(body: list[dict]) -> dict:
        """Batch upsert личных замеров. Scope: body:write. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        if not isinstance(body, list) or not body:
            raise ValueError('Нужен непустой список замеров.')
        return _write(transport, 'POST', '/body/stamps', body, response=False)

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_body_characteristic(id: UUID) -> dict:
        """Удалить личную характеристику. Scope: body:delete. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        api_get('/body/characteristics/' + _id(id))
        return _write(transport, 'DELETE', '/body/characteristics/' + _id(id), identifier=_id(id))

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_body_stamp(id: UUID) -> dict:
        """Удалить личный замер. Scope: body:delete. Нужен GYM_ENABLE_LEGACY_WRITES=1."""
        _legacy_enabled(legacy_writes)
        stamps = api_get('/body/stamps', _page(0, 200))
        if not any(_id_or_none(s.get('id')) == _id(id) for s in stamps.get('items', [])):
            raise ValueError('Личный замер не найден в текущей странице.')
        return _write(transport, 'DELETE', '/body/stamps/' + _id(id), identifier=_id(id))
