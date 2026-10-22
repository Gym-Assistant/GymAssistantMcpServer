"""Планы для локального MCP: чтение и создание нового личного плана."""
from datetime import datetime, timezone
from pathlib import Path
import os
from http.client import HTTPException
from typing import Annotated, Literal
from uuid import UUID, uuid4
import json
import urllib.error
import urllib.request

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


REPS_TYPES = {'weight_reps', 'bodyweight_reps', 'assisted_reps', 'band_reps'}


class SetMeasurement(Input):
    """Дополнительные значения API: секунды, метры, кг помощи и сантиметры."""
    trackingType: Literal['weight_reps', 'bodyweight_reps', 'assisted_reps', 'band_reps',
                          'duration', 'cardio', 'weight_distance', 'interval']
    durationSeconds: int | None = Field(default=None, ge=0, le=604800)
    distanceMeters: float | None = Field(default=None, ge=0, le=1000000)
    assistanceWeight: float | None = Field(default=None, ge=0, le=10000)
    resistanceLevel: str | None = Field(default=None, min_length=1, max_length=80)
    inclinePercent: float | None = Field(default=None, ge=-100, le=100)
    heightCm: float | None = Field(default=None, ge=0, le=1000)
    rounds: int | None = Field(default=None, ge=0, le=10000)
    workSeconds: int | None = Field(default=None, ge=0, le=604800)
    recoverySeconds: int | None = Field(default=None, ge=0, le=604800)
    side: Literal['left', 'right', 'both'] | None = None

    @model_validator(mode='after')
    def compatible_values(self):
        allowed = {
            'durationSeconds': {'duration', 'cardio', 'weight_distance', 'interval'},
            'distanceMeters': {'cardio', 'weight_distance'},
            'assistanceWeight': {'assisted_reps'},
            'resistanceLevel': {'band_reps', 'cardio', 'assisted_reps'},
            'inclinePercent': {'cardio'},
            'heightCm': {'weight_reps', 'bodyweight_reps'},
            'rounds': {'interval'}, 'workSeconds': {'interval'}, 'recoverySeconds': {'interval'},
        }
        for field, types in allowed.items():
            if getattr(self, field) is not None and self.trackingType not in types:
                raise ValueError(f'{field} не применяется к {self.trackingType}.')
        if self.trackingType in {'duration', 'cardio', 'weight_distance'}:
            if not ((self.durationSeconds or 0) > 0 or (self.distanceMeters or 0) > 0):
                raise ValueError('Укажите время или дистанцию больше нуля.')
        if self.trackingType == 'interval' and not ((self.rounds or 0) > 0 and (self.workSeconds or 0) > 0):
            raise ValueError('Укажите количество интервалов и длительность работы больше нуля.')
        return self


class PlanSet(Input):
    reps: int | None = Field(default=None, ge=0, description='Повторы для силовых подходов; для времени/дистанции/интервалов можно не задавать.')
    measurement: SetMeasurement | None = None
    weight: float | None = Field(default=None, ge=0, description='Вес; null — не задан, 0 — без внешнего веса.')
    weight_percent: float | None = Field(default=None, gt=0, le=200, description='Процент 1RM вместо абсолютного веса.')
    unit: Literal['kg', 'lb'] = 'kg'
    warmup: bool = False
    rest_seconds: int | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)

    @model_validator(mode='after')
    def weight_mode(self):
        if self.weight is not None and self.weight_percent is not None:
            raise ValueError('Укажите либо вес, либо процент 1RM.')
        if (self.measurement is None or self.measurement.trackingType in REPS_TYPES) and not (self.reps and self.reps > 0):
            raise ValueError('Для силового подхода укажите повторы больше нуля.')
        return self


class PlanExercise(Input):
    user_exercise_id: UUID | None = Field(default=None, description='ID личного упражнения из gym_exercises.')
    default_exercise_id: UUID | None = Field(default=None, description='globalId базового упражнения из gym_exercises(source="default").')
    comment: str = ''
    sets: list[PlanSet] = Field(min_length=1)

    @model_validator(mode='after')
    def one_exercise(self):
        if (self.user_exercise_id is None) == (self.default_exercise_id is None):
            raise ValueError('Нужна ровно одна ссылка: личное или базовое упражнение.')
        return self


class PlanDay(Input):
    title: str = Field(min_length=1)
    description: str = ''
    exercises: list[PlanExercise] = Field(min_length=1)


def _items(response):
    return response.get('items', []) if isinstance(response, dict) else response


def _all(api_get, path):
    offset = 0
    while True:
        response = api_get(path, {'offset': offset, 'limit': 100})
        items = _items(response)
        yield from items
        offset += len(items)
        total = response.get('total') if isinstance(response, dict) else None
        if not items or (total is not None and offset >= total) or (total is None and len(items) < 100):
            return


def _owner(api_get):
    return str(UUID(api_get('/auth/me')['id']))


def _owned_plan(api_get, plan_id, owner):
    """GET /plans/{id} с проверкой автора.

    Маршрут по ID на старых и новых backend не фильтрует владельца, поэтому
    автор сверяется здесь. 404, чужой или удалённый план — одинаково «не найден».
    """
    not_found = 'Личный план с таким ID не найден.'
    plan_id = str(UUID(str(plan_id)))
    try:
        plan = api_get(f'/plans/{plan_id}')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            e.close()
            raise ValueError(not_found) from None
        raise
    if (not isinstance(plan, dict) or plan.get('isDeleted')
            or not _same_id(plan.get('id'), plan_id) or not _same_id(plan.get('authorUserId'), owner)):
        raise ValueError(not_found)
    return plan


def _same_id(value, expected):
    try:
        return str(UUID(str(value))) == expected
    except ValueError:
        return False


def make_plan_writer(api_url, token):
    """Один POST без повторов: повтор после таймаута может создать лишний план."""
    def post(body):
        request = urllib.request.Request(
            api_url.rstrip('/') + '/plans',
            data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8'),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    return post


def _exercise_indexes(api_get, days):
    sources = {('personal' if e.user_exercise_id else 'default') for d in days for e in d.exercises}
    indexes = {}
    for source in sources:
        path = '/exercises' if source == 'personal' else '/exercises/defaults'
        id_field = 'id' if source == 'personal' else 'globalId'
        indexes[source] = {e[id_field]: e for e in _all(api_get, path) if not e.get('isDeleted')}
    for day in days:
        for exercise in day.exercises:
            source = 'personal' if exercise.user_exercise_id else 'default'
            exercise_id = str(exercise.user_exercise_id or exercise.default_exercise_id)
            if exercise_id not in indexes[source]:
                raise ValueError('Упражнение не найдено в доступном каталоге; обновите gym_exercises.')
    return indexes

def _add_days(plan, days, indexes, audit, existing_pool=()):
    plan_id = plan['id']
    pool = {}
    for entry in existing_pool:
        if entry.get('userExerciseId'):
            pool.setdefault(('personal', entry['userExerciseId']), entry)
        elif entry.get('defaultExerciseGlobalId'):
            pool.setdefault(('default', entry['defaultExerciseGlobalId']), entry)
    for day_index, day in enumerate(days):
        template_id = str(uuid4())
        template = {'id': template_id, 'planId': plan_id, 'sortOrder': day_index,
                    'title': day.title, 'description': day.description, 'exercises': [], **audit}
        plan['templates'].append(template)
        for exercise_index, exercise in enumerate(day.exercises):
            source = 'personal' if exercise.user_exercise_id else 'default'
            exercise_id = str(exercise.user_exercise_id or exercise.default_exercise_id)
            key = (source, exercise_id)
            if key not in pool:
                entry = {'id': str(uuid4()), 'planId': plan_id,
                         'userExerciseId': exercise_id if source == 'personal' else None,
                         'defaultExerciseGlobalId': exercise_id if source == 'default' else indexes[source][exercise_id].get('globalId'),
                         'displayName': indexes[source][exercise_id]['name'], **audit}
                pool[key] = entry
                plan['exercises'].append(entry)
            entry = pool[key]
            nested_id = str(uuid4())
            nested = {'id': nested_id, 'planTemplateId': template_id, 'sortOrder': exercise_index,
                      'planExerciseId': entry['id'], 'userExerciseId': entry['userExerciseId'],
                      'defaultExerciseGlobalId': entry['defaultExerciseGlobalId'],
                      'displayName': entry['displayName'], 'comment': exercise.comment,
                      'sets': [], **audit}
            template['exercises'].append(nested)
            for number, s in enumerate(exercise.sets, 1):
                nested['sets'].append({'id': str(uuid4()), 'planTemplateExerciseId': nested_id,
                                      'number': number, 'reps': s.reps if s.reps is not None else 0, 'targetWeight': s.weight,
                                      **({'measurement': s.measurement.model_dump(exclude_none=True)} if s.measurement else {}),
                                      'targetWeightPercent': s.weight_percent, 'weightUnit': s.unit,
                                      'targetRpe': s.rpe, 'setType': 1 if s.warmup else 0,
                                      'restSecondsOverride': s.rest_seconds, **audit})


def register_plan_tools(mcp, api_get, api_post_plan, api_append_plan=None, backup_plan=None):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

    @mcp.tool(annotations=read)
    def gym_plans(offset: Annotated[int, Field(ge=0)] = 0,
                  limit: Annotated[int, Field(ge=1, le=100)] = 50) -> dict:
        """Личные планы со всеми днями и подходами. Scope: plans:read.

        Перед созданием проверь, нет ли уже согласованного плана; листай offset/limit.
        """
        return api_get('/plans', {'offset': offset, 'limit': limit})

    @mcp.tool(annotations=read)
    def gym_plan(plan_id: UUID) -> dict:
        """Полный личный план по ID. Scopes: plans:read, profile:read.

        Чужие и удалённые планы не возвращаются: автор плана сверяется с /auth/me.
        """
        return _owned_plan(api_get, plan_id, _owner(api_get))

    @mcp.tool(annotations=read)
    def gym_exercises(source: Literal['personal', 'default'] = 'personal',
                      offset: Annotated[int, Field(ge=0)] = 0,
                      limit: Annotated[int, Field(ge=1, le=100)] = 50,
                      include_hidden: bool = False) -> dict:
        """Упражнения с ID и метаданными. personal требует exercises:read; default публичный.

        personal: id — личное упражнение, globalId — связь с общим шаблоном.
        default: globalId — сам шаблон. Не подменяй личный id значением globalId.
        Для плана предпочитай личный вариант пользователя; листай offset/limit.
        include_hidden допустим только для default: включает скрытые шаблоны для
        восстановления ссылок истории. По умолчанию новые планы используют видимый каталог.
        Поля groupCode, nameEn, aliasesEn, media, loadConvention, isUnilateral и
        muscles.role, templateRevision и templateOverrides передаются без преобразования.
        Это версии и личные переопределения метаданных, не история подходов.
        canonicalId не переназначает личные ID.
        """
        if source == 'personal' and include_hidden:
            raise ValueError('include_hidden доступен только для общего каталога (source=default).')
        path = '/exercises' if source == 'personal' else '/exercises/defaults'
        params = {'offset': offset, 'limit': limit}
        if include_hidden:
            params['includeHidden'] = 'true'
        return api_get(path, params)

    @mcp.tool(annotations=read)
    def gym_default_exercise(global_id: UUID) -> dict:
        """Общий шаблон по реальному globalId, включая скрытый. Публичный справочник.

        Для разбора старых планов/истории, если шаблон отсутствует в обычном списке.
        Сохраняет метаданные, templateRevision, isHidden и canonicalId;
        ничего не перепривязывает и не создаёт личное упражнение.
        """
        return api_get('/exercises/defaults/' + str(global_id))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
    def gym_create_plan(name: Annotated[str, Field(min_length=1)],
                        days: Annotated[list[PlanDay], Field(min_length=1)],
                        description: str = '',
                        work_rest_seconds: Annotated[int | None, Field(ge=0)] = None,
                        warmup_rest_seconds: Annotated[int | None, Field(ge=0)] = None) -> dict:
        """Создать согласованный с пользователем НОВЫЙ личный план с днями и подходами.

        Scopes: profile:read, exercises:read, plans:write. Перед вызовом прочитай
        gym_plans и gym_exercises, используй реальные ID и согласованные веса.
        Все ID плана генерируются заново; существующие планы не обновляются.
        План не публикуется и не назначается активным. Вес: kg/lb; отдых: секунды;
        warmup=true — разминка. Комментарии к упражнению — comment.
        Новый формат задаётся в sets[].measurement: trackingType и значения API
        (durationSeconds, distanceMeters, assistanceWeight в кг, rounds/workSeconds/
        recoverySeconds). Для кардио/времени/интервалов reps не обязателен.
        Старые подходы без measurement сохраняют смысл веса и повторов.
        Если status=unknown, проверь plan_id через gym_plan; НЕ повторяй создание,
        пока не выяснен результат. status=created означает успешный ответ сервера.
        """
        name = name.strip()
        if not name:
            raise ValueError('Название плана не может быть пустым.')
        # Валидация также при прямом вызове, вне MCP/Pydantic-обвязки.
        days = [PlanDay.model_validate(day) for day in days]
        if not days:
            raise ValueError('Добавьте хотя бы один день.')
        indexes = _exercise_indexes(api_get, days)

        owner = _owner(api_get)
        now = datetime.now(timezone.utc).isoformat()
        audit = {'createdById': owner, 'createdAt': now, 'updatedAt': now}
        plan_id = str(uuid4())
        rest = {str(k): v for k, v in [(0, work_rest_seconds), (1, warmup_rest_seconds)] if v is not None}
        plan = {'id': plan_id, 'authorUserId': owner, 'name': name, 'description': description,
                'isPublished': False, 'isDeleted': False, 'revision': 1, 'restDefaults': rest or None,
                'exercises': [], 'templates': [], **audit}
        _add_days(plan, days, indexes, audit)

        try:
            api_post_plan(plan)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise ValueError(f'План не сохранён: HTTP {e.code}. Проверьте доступ и параметры.') from None
            return {'status': 'unknown', 'plan_id': plan_id,
                    'message': 'Сервер не подтвердил сохранение. Проверьте этот ID через gym_plan перед повтором.'}
        except (OSError, HTTPException):
            return {'status': 'unknown', 'plan_id': plan_id,
                    'message': 'Ответ не получен. Проверьте этот ID через gym_plan перед повтором.'}
        return {'status': 'created', 'plan_id': plan_id, 'name': name,
                'days': len(days), 'sets': sum(len(e.sets) for d in days for e in d.exercises)}


    if api_append_plan is None:
        return

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
    def gym_append_plan_days(plan_id: UUID, expected_updated_at: str,
                             days: Annotated[list[PlanDay], Field(min_length=1)]) -> dict:
        """Добавить согласованные дни В КОНЕЦ существующего личного плана.

        Scopes: profile:read, plans:read, plans:write, exercises:read.
        Сначала прочитай gym_plan; expected_updated_at скопируй из updatedAt.
        Передавай только НОВЫЕ дни, не повторяй существующие. Их ID, упражнения,
        подходы, веса и заметки сохраняются. Сначала сохраняется локальная копия
        исходного плана. Сервер проверяет актуальность и вставляет новые строки.
        409 означает изменение плана: перечитай его и согласуй следующие действия.
        При status=unknown проверь added_day_ids через gym_plan; не повторяй вслепую.
        Это дни-шаблоны, не тренировки в календаре: date отсутствует в модели API.
        Новые форматы — sets[].measurement как в gym_create_plan; прежние дни не пересчитываются.
        """
        days = [PlanDay.model_validate(day) for day in days]
        if not days:
            raise ValueError('Добавьте хотя бы один новый день.')
        expected = _timestamp(expected_updated_at)
        owner = _owner(api_get)
        original = _owned_plan(api_get, plan_id, owner)
        if _timestamp(original['updatedAt']) != expected:
            raise ValueError('План изменился. Перечитайте gym_plan перед добавлением дней.')
        indexes = _exercise_indexes(api_get, days)
        now = datetime.now(timezone.utc).isoformat()
        addition = {'id': str(plan_id), 'exercises': [], 'templates': []}
        _add_days(addition, days, indexes,
                  {'createdById': owner, 'createdAt': now, 'updatedAt': now}, original.get('exercises', []))
        body = {'expectedUpdatedAt': expected_updated_at,
                'exercises': addition['exercises'], 'templates': addition['templates']}
        added_ids = [day['id'] for day in addition['templates']]
        (backup_plan or _backup_plan)(original, body)
        unknown = {'status': 'unknown', 'plan_id': str(plan_id), 'added_day_ids': added_ids,
                   'message': 'Сохранение не подтверждено. Проверьте эти дни через gym_plan перед повтором.'}
        try:
            saved = api_append_plan(str(plan_id), body)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                raise ValueError('План изменился или IDs уже заняты (409). Перечитайте gym_plan; запрос не повторён.') from None
            if e.code < 500:
                raise ValueError(f'Дни не добавлены: HTTP {e.code}. Проверьте доступ и параметры.') from None
            return unknown
        except (OSError, HTTPException, ValueError):
            return unknown
        try:
            if not _preserved(original, saved, added_ids):
                return unknown
        except (ValueError, TypeError, KeyError):
            return unknown
        return {'status': 'appended', 'plan_id': str(plan_id), 'added_day_ids': added_ids,
                'added_days': len(days), 'total_days': len(saved['templates']), 'updated_at': saved['updatedAt']}


def _timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('updatedAt должен содержать часовой пояс; скопируйте значение из gym_plan.')
    return parsed


def _preserved(original, saved, added_ids):
    if not isinstance(saved, dict):
        return False
    for key, value in original.items():
        if key not in {'updatedAt', 'revision', 'templates', 'exercises'} and saved.get(key) != value:
            return False
    for collection in ('templates', 'exercises'):
        current = {entry['id']: entry for entry in saved.get(collection, [])}
        if any(current.get(entry['id']) != entry for entry in original.get(collection, [])):
            return False
    saved_ids = {entry['id'] for entry in saved.get('templates', [])}
    return set(added_ids) <= saved_ids and isinstance(saved.get('updatedAt'), str)


def _backup_plan(original, addition):
    """Личная восстанавливаемая копия до изменения; вне репозитория и журналов."""
    root = Path(os.environ.get('GYM_PLAN_BACKUP_DIR',
                str(Path.home() / 'Library/Application Support/GymAssistant/McpBackups')))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / f"plan-{original['id']}-{uuid4()}.json"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'before': original, 'addition': addition}, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def make_plan_appender(api_url, token):
    def append(plan_id, body):
        request = urllib.request.Request(
            api_url.rstrip('/') + '/plans/' + str(UUID(plan_id)) + '/days',
            data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8'),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    return append
