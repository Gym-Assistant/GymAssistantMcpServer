"""Чтение профиля, тренировок, рекордов и замеров тела для локального MCP.

Логика перенесена из установленного server.py без изменений поведения.
"""
from __future__ import annotations

from collections import defaultdict


def _items(response):
    return response.get('items', []) if isinstance(response, dict) else response


def first_set_date(w: dict) -> str | None:
    earliest = None
    for ts in w.get('trainSessions', []):
        for s in ts.get('sets', []):
            ca = s.get('createdAt')
            if ca and (earliest is None or ca < earliest):
                earliest = ca
    return earliest[:10] if earliest else None


def epley_1rm(weight: float, reps: int) -> float:
    if reps <= 0:
        return 0.0
    if reps == 1:
        return float(weight)
    return round(weight * (1 + reps / 30.0), 1)


def summarize_workout(w: dict, ex_idx: dict) -> dict:
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
        'date': first_set_date(w),
        'exercises_count': len(by_ex),
        'sets_count': total_sets,
        'volume_kg': round(total_volume, 1),
        'exercises': by_ex,
    }


def find_records(items: list[dict], ex_idx: dict, top_n: int) -> list[dict]:
    # max weight per exercise (для warmup-detection)
    max_w = defaultdict(float)
    for w in items:
        for ts in w.get('trainSessions', []):
            for s in ts.get('sets', []):
                if s.get('isDone') and s['weight'] > max_w[ts.get('exerciseId', '')]:
                    max_w[ts.get('exerciseId', '')] = s['weight']
    records = {}
    for w in items:
        d = first_set_date(w)
        for ts in w.get('trainSessions', []):
            ex_id = ts.get('exerciseId', '')
            ex_name = ex_idx.get(ex_id, {}).get('name', '?')
            for s in ts.get('sets', []):
                if not s.get('isDone'):
                    continue
                # exclude warmup (<60% of max + >12 reps)
                if max_w[ex_id] > 0 and (s['weight'] / max_w[ex_id]) < 0.6 and s['reps'] > 12:
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
        n: количество (default 10, max 50)."""
        n = max(1, min(int(n), 50))
        data = api_get('/workouts', {'offset': 0, 'limit': max(n, 30)})
        items = _items(data)
        ex_idx = exercises()
        summaries = [summarize_workout(w, ex_idx) for w in items]
        summaries = [s for s in summaries if s['sets_count'] > 0]
        summaries.sort(key=lambda s: s.get('date') or '', reverse=True)
        return summaries[:n]

    @mcp.tool()
    def gym_workout(workout_date: str) -> dict:
        """Детальная тренировка за конкретную дату.
        workout_date: YYYY-MM-DD."""
        items = _items(api_get('/workouts', {'offset': 0, 'limit': 50}))
        ex_idx = exercises()
        for w in items:
            if first_set_date(w) == workout_date:
                return summarize_workout(w, ex_idx)
        return {'error': f'Не найдено за {workout_date} в последних 50 тренировках'}

    @mcp.tool()
    def gym_records(top_n: int = 25) -> list[dict]:
        """Действующие est. 1RM (по Epley), исключая разогревочные подходы.
        top_n: количество (default 25)."""
        data = api_get('/workouts', {'offset': 0, 'limit': 200})
        return find_records(_items(data), exercises(), top_n)

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

