"""Представление тренировок локального MCP без потери новых измерений.

Только явный weight_reps или прежний подход без measurement участвует в
силовом объёме/1RM. Текущий формат упражнения не переосмысляет старые подходы.
"""
from collections import defaultdict
from copy import deepcopy


def strength_set(entry):
    measurement = entry.get('measurement')
    return measurement is None or (isinstance(measurement, dict) and measurement.get('trackingType') == 'weight_reps')


def set_result(entry):
    result = {'weight': entry.get('weight', 0), 'reps': entry.get('reps', 0)}
    for field in ('id', 'number', 'isDone', 'isWarmup', 'comment'):
        if field in entry:
            result[field] = entry[field]
    if 'measurement' in entry:
        result['measurement'] = deepcopy(entry['measurement'])
    return result


def summarize_workout(workout, exercises, workout_date):
    total_sets, total_volume = 0, 0.0
    by_ex = []
    for session in workout.get('trainSessions') or []:
        exercise = exercises.get(session.get('exerciseId', ''), {})
        sets = sorted((s for s in session.get('sets') or [] if s.get('isDone')),
                      key=lambda s: s.get('number') or 0)
        if not sets:
            continue
        strength = [s for s in sets if strength_set(s)]
        volume = lambda s: (s.get('weight') or 0) * (s.get('reps') or 0)
        exercise_volume = sum(volume(s) for s in strength)
        total_sets += len(sets)
        total_volume += exercise_volume
        top = max(strength, key=volume) if strength else None
        item = {
            'session_id': session.get('id'), 'exercise_id': session.get('exerciseId'),
            'name': exercise.get('name', '?'), 'sets': [set_result(s) for s in sets],
            'volume_kg': exercise_volume, 'top': set_result(top) if top else None,
        }
        if exercise.get('trackingType') is not None:
            item['trackingType'] = exercise['trackingType']
        by_ex.append(item)
    return {
        'id': workout.get('id'), 'date': workout_date(workout),
        'comment': workout.get('comment'),
        'set_comments': [
            {'session_id': session.get('id'), 'exercise_id': session.get('exerciseId'),
             'exercise': exercises.get(session.get('exerciseId', ''), {}).get('name', '?'),
             'set_id': entry.get('id'), 'number': entry.get('number'),
             'is_done': entry.get('isDone', False), 'comment': entry['comment']}
            for session in workout.get('trainSessions') or []
            for entry in session.get('sets') or [] if entry.get('comment')
        ],
        'exercises_count': len(by_ex), 'sets_count': total_sets,
        'volume_kg': round(total_volume, 1), 'exercises': by_ex,
    }


def build_records(workouts, exercises, top_n, workout_date, epley):
    max_weight = defaultdict(float)
    for workout in workouts:
        for session in workout.get('trainSessions') or []:
            for entry in session.get('sets') or []:
                if entry.get('isDone') and entry.get('isWarmup') is not True and strength_set(entry):
                    key = session.get('exerciseId', '')
                    max_weight[key] = max(max_weight[key], entry.get('weight') or 0)
    records = {}
    for workout in workouts:
        for session in workout.get('trainSessions') or []:
            exercise_id = session.get('exerciseId', '')
            name = exercises.get(exercise_id, {}).get('name', '?')
            for entry in session.get('sets') or []:
                if not entry.get('isDone') or entry.get('isWarmup') is True or not strength_set(entry):
                    continue
                weight, reps = entry.get('weight') or 0, entry.get('reps') or 0
                # Явный флаг разминки важнее эвристики; отсутствие флага сохраняет прежнее поведение.
                if entry.get('isWarmup') is None and max_weight[exercise_id] > 0 and weight / max_weight[exercise_id] < 0.6 and reps > 12:
                    continue
                rm = epley(weight, reps)
                current = records.get(name)
                if current is None or rm > current['rm']:
                    records[name] = {'exercise': name, 'rm': rm, 'weight': weight,
                                     'reps': reps, 'date': workout_date(workout)}
    return sorted(records.values(), key=lambda x: -x['rm'])[:top_n]
