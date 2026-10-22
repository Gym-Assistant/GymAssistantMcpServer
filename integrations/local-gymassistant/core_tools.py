"""Чтение профиля, тренировок, рекордов и замеров тела для локального MCP."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone, tzinfo
from http.client import HTTPException
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


WORKOUT_PAGE_SIZE = 100
# Верхняя граница поиска по истории: 50 страниц по 100 тренировок.
MAX_SCANNED_WORKOUTS = 5000
RECORDS_WINDOW = 200
# Эвристика разминки для старых подходов без флага isWarmup.
WARMUP_WEIGHT_SHARE = 0.6
WARMUP_MIN_REPS_EXCLUSIVE = 12


def _items(response):
    return response.get('items', []) if isinstance(response, dict) else response


def load_workouts(api_get, max_items=MAX_SCANNED_WORKOUTS, page_size=WORKOUT_PAGE_SIZE):
    """Тренировки страницами от новых к старым. Возвращает (список, просмотрена_вся_история)."""
    items, offset = [], 0
    while True:
        limit = min(page_size, max_items - offset)
        if limit <= 0:
            return items, False
        response = api_get('/workouts', {'offset': offset, 'limit': limit})
        page = _items(response)
        items.extend(page)
        offset += len(page)
        total = response.get('total') if isinstance(response, dict) else None
        if not page or (total is not None and offset >= total) or (total is None and len(page) < limit):
            return items, True


def user_time_zone(api_get) -> tuple[tzinfo, str]:
    """Часовой пояс из GET /user/settings (timeZoneId); при любой недоступности — UTC."""
    try:
        settings = api_get('/user/settings')
    except (OSError, ValueError, HTTPException):
        return timezone.utc, 'UTC'
    name = settings.get('timeZoneId') if isinstance(settings, dict) else None
    if not isinstance(name, str) or not name.strip():
        return timezone.utc, 'UTC'
    try:
        return ZoneInfo(name.strip()), name.strip()
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc, 'UTC'


def _instant(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def local_workout_date(workout: dict, tz: tzinfo = timezone.utc) -> str | None:
    """Локальная дата тренировки YYYY-MM-DD в поясе пользователя.

    Порядок: startedAt -> scheduledDateLocal (уже локальная дата) -> самый ранний
    createdAt подхода -> createdAt тренировки. Последние два — только для старых
    записей без startedAt; все моменты времени переводятся в пояс пользователя.
    """
    started = _instant(workout.get('startedAt'))
    if started:
        return started.astimezone(tz).date().isoformat()
    scheduled = workout.get('scheduledDateLocal')
    if isinstance(scheduled, str) and scheduled:
        try:
            return date.fromisoformat(scheduled[:10]).isoformat()
        except ValueError:
            pass
    instants = [moment for session in workout.get('trainSessions') or []
                for s in session.get('sets') or [] if (moment := _instant(s.get('createdAt')))]
    first = min(instants, default=None) or _instant(workout.get('createdAt'))
    return first.astimezone(tz).date().isoformat() if first else None


def epley_1rm(weight: float, reps: int) -> float:
    """Расчётный 1RM по формуле Эпли: вес × (1 + повторы / 30), округление до 0.1.

    1 повтор — сам вес; 0 и меньше повторов — 0. Повторы сверху не ограничены,
    поэтому оценка для многоповторных подходов грубая и может отличаться от
    приложения (там другие ограничения формулы).
    """
    if reps <= 0:
        return 0.0
    if reps == 1:
        return float(weight)
    return round(weight * (1 + reps / 30.0), 1)


def is_warmup(s: dict, max_weight: float) -> bool:
    """Флаг isWarmup подхода важнее эвристики; эвристика — только при null/отсутствии."""
    flag = s.get('isWarmup')
    if flag is not None:
        return bool(flag)
    return (max_weight > 0 and s['weight'] / max_weight < WARMUP_WEIGHT_SHARE
            and s['reps'] > WARMUP_MIN_REPS_EXCLUSIVE)


def summarize_workout(w: dict, ex_idx: dict, tz: tzinfo = timezone.utc) -> dict:
    sessions = w.get('trainSessions', [])
    total_sets = 0
    total_volume = 0.0
    by_ex = []
    for ts in sessions:
        ex = ex_idx.get(ts.get('exerciseId', ''), {})
        ex_name = ex.get('name', '?')
        sets = sorted(ts.get('sets', []), key=lambda s: s.get('number', 0))
        sets = [s for s in sets if s.get('isDone')]
        if not sets:
            continue
        total_sets += len(sets)
        ex_vol = sum(s['weight'] * s['reps'] for s in sets)
        total_volume += ex_vol
        top = max(sets, key=lambda s: s['weight'] * s['reps'])
        by_ex.append({
            'name': ex_name,
            'sets': [{'weight': s['weight'], 'reps': s['reps']} for s in sets],
            'volume_kg': ex_vol,
            'top': {'weight': top['weight'], 'reps': top['reps']},
        })
    return {
        'id': w.get('id'),
        'date': local_workout_date(w, tz),
        'exercises_count': len(by_ex),
        'sets_count': total_sets,
        'volume_kg': round(total_volume, 1),
        'exercises': by_ex,
    }


def find_records(items: list[dict], ex_idx: dict, tz: tzinfo, top_n: int) -> list[dict]:
    max_w = defaultdict(float)
    for w in items:
        for ts in w.get('trainSessions', []):
            ex_id = ts.get('exerciseId', '')
            for s in ts.get('sets', []):
                # Отмеченная разминка не задаёт рабочий максимум для эвристики.
                if s.get('isDone') and s.get('isWarmup') is not True and s['weight'] > max_w[ex_id]:
                    max_w[ex_id] = s['weight']
    records = {}
    for w in items:
        d = local_workout_date(w, tz)
        for ts in w.get('trainSessions', []):
            ex_id = ts.get('exerciseId', '')
            ex_name = ex_idx.get(ex_id, {}).get('name', '?')
            for s in ts.get('sets', []):
                if not s.get('isDone') or is_warmup(s, max_w[ex_id]):
                    continue
                rm = epley_1rm(s['weight'], s['reps'])
                cur = records.get(ex_name)
                if cur is None or rm > cur['rm']:
                    records[ex_name] = {'exercise': ex_name, 'rm': rm, 'weight': s['weight'],
                                        'reps': s['reps'], 'date': d}
    return sorted(records.values(), key=lambda x: -x['rm'])[:top_n]


def _body_series(api_get):
    chars_data = api_get('/body/characteristics', {'offset': 0, 'limit': 100})
    chars = chars_data.get('items', []) if isinstance(chars_data, dict) else chars_data
    chars = [c for c in chars if c.get('name') != 'Вес' and not c.get('isDeleted')]
    stamps = []
    offset = 0
    while True:
        page = api_get('/body/stamps', {'offset': offset, 'limit': 200})
        items = page.get('items', []) if isinstance(page, dict) else page
        stamps.extend(items)
        if not items or len(items) < 200:
            break
        offset += len(items)
    char_by_id = {c['id']: c for c in chars}
    valid = []
    for s in stamps:
        if s.get('isDeleted') or s['userCharacteristicId'] not in char_by_id:
            continue
        d = (s.get('measuredAt') or s.get('createdAt', ''))[:10]
        v = s.get('value')
        if v is None or not d:
            continue
        valid.append((s, d, v))
    return chars, valid


def register_core_tools(mcp, api_get, api_url):
    cache: dict[str, dict] = {}

    def exercises() -> dict[str, dict]:
        if cache:
            return cache
        offset = 0
        while True:
            data = api_get('/exercises', {'offset': offset, 'limit': 200})
            items = data.get('items', []) if isinstance(data, dict) else data
            for e in items:
                cache[e['id']] = e
            if not items or len(items) < 200:
                break
            offset += len(items)
        return cache

    @mcp.tool()
    def gym_me() -> dict:
        """Профиль пользователя GymAssistant (id, name, username, signup date)."""
        return api_get('/auth/me')

    @mcp.tool()
    def gym_workouts(n: int = 10) -> list[dict]:
        """Последние N тренировок (свёрнуто): дата, упражнения, подходов, объём.
        n: количество (default 10, max 50). Дата — локальная в часовом поясе пользователя."""
        n = max(1, min(int(n), 50))
        tz, _ = user_time_zone(api_get)
        data = api_get('/workouts', {'offset': 0, 'limit': max(n, 30)})
        items = _items(data)
        ex_idx = exercises()
        summaries = [summarize_workout(w, ex_idx, tz) for w in items]
        summaries = [s for s in summaries if s['sets_count'] > 0]
        summaries.sort(key=lambda s: s.get('date') or '', reverse=True)
        return summaries[:n]

    @mcp.tool()
    def gym_workout(workout_date: str) -> dict:
        """Детальная тренировка за конкретную дату.
        workout_date: YYYY-MM-DD — локальная дата в часовом поясе пользователя
        (timeZoneId из настроек, иначе UTC). Дата тренировки берётся из startedAt,
        затем scheduledDateLocal; поиск идёт по всей истории (до 5000 тренировок).
        Если за дату несколько тренировок, остальные ID — в other_workout_ids."""
        target = date.fromisoformat(workout_date)
        if target.isoformat() != workout_date:
            raise ValueError('Укажите дату в формате YYYY-MM-DD.')
        tz, tz_name = user_time_zone(api_get)
        items, complete = load_workouts(api_get)
        matches = [w for w in items if not w.get('isDeleted') and local_workout_date(w, tz) == workout_date]
        if not matches:
            where = 'во всей истории' if complete else f'в последних {len(items)} тренировках'
            return {'error': f'Не найдено за {workout_date} {where} (часовой пояс {tz_name})'}
        ex_idx = exercises()
        summaries = [summarize_workout(w, ex_idx, tz) for w in matches]
        chosen = next((s for s in summaries if s['sets_count'] > 0), summaries[0])
        others = [s['id'] for s in summaries if s is not chosen]
        return {**chosen, 'other_workout_ids': others} if others else chosen

    @mcp.tool()
    def gym_records(top_n: int = 25) -> list[dict]:
        """Действующие est. 1RM по упражнениям среди последних 200 тренировок.
        Формула Эпли: вес × (1 + повторы / 30), 1 повтор — сам вес.
        Разминка исключается по флагу подхода isWarmup; для старых подходов без
        флага — эвристика: меньше 60% максимума упражнения и больше 12 повторов.
        top_n: количество (default 25)."""
        tz, _ = user_time_zone(api_get)
        data = api_get('/workouts', {'offset': 0, 'limit': RECORDS_WINDOW})
        return find_records(_items(data), exercises(), tz, top_n)

    @mcp.tool()
    def gym_body_latest() -> list[dict]:
        """Последние значения замеров тела (талия/грудь/бицепс/etc., БЕЗ веса).
        Вес исключён — primary источник Apple Health."""
        chars, stamps = _body_series(api_get)
        series: dict[tuple[str, int], list[tuple[str, float]]] = defaultdict(list)
        for s, d, v in stamps:
            series[(s['userCharacteristicId'], s.get('side', 0))].append((d, v))
        out = []
        for c in sorted(chars, key=lambda x: (x.get('sortOrder', 999), x.get('name', ''))):
            sides = [0, 1] if c.get('isDual') else [0]
            for side in sides:
                arr = sorted(series.get((c['id'], side), []))
                if not arr:
                    continue
                last_d, last_v = arr[-1]
                prev_v = arr[-2][1] if len(arr) >= 2 else None
                delta = round(last_v - prev_v, 1) if prev_v is not None else None
                out.append({
                    'name': c['name'],
                    'side': 'L' if (c.get('isDual') and side == 1) else ('R' if c.get('isDual') else None),
                    'value': last_v,
                    'date': last_d,
                    'delta_to_previous': delta,
                })
        return out

    @mcp.tool()
    def gym_body_history(n_dates: int = 12) -> dict:
        """История последних N замеров тела (transposed: метрики × даты).
        n_dates: количество последних уникальных дат замеров (default 12)."""
        chars, stamps = _body_series(api_get)
        series_by_date: dict[str, dict[tuple[str, int], float]] = defaultdict(dict)
        for s, d, v in stamps:
            series_by_date[d][(s['userCharacteristicId'], s.get('side', 0))] = v
        all_dates = sorted(series_by_date.keys(), reverse=True)[:n_dates]
        all_dates.sort()
        rows = {}
        for c in sorted(chars, key=lambda x: (x.get('sortOrder', 999), x.get('name', ''))):
            sides = [0, 1] if c.get('isDual') else [0]
            for side in sides:
                label = c['name']
                if c.get('isDual'):
                    label += ' ' + ('L' if side == 1 else 'R')
                row = []
                has_any = False
                for d in all_dates:
                    v = series_by_date.get(d, {}).get((c['id'], side))
                    if v is not None:
                        has_any = True
                    row.append(v)
                if has_any:
                    rows[label] = row
        return {'dates': all_dates, 'metrics': rows}

    @mcp.tool()
    def gym_status() -> dict:
        """Здоровье сервера и токена: возвращает me + API URL + кол-во упражнений в каталоге."""
        try:
            me = api_get('/auth/me')
        except Exception as e:
            return {'ok': False, 'error': str(e), 'api': api_url}
        return {
            'ok': True,
            'api': api_url,
            'user': me.get('username'),
            'exercises_in_catalog': len(exercises()),
        }

