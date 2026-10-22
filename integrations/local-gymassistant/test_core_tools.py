"""Даты тренировок, поиск по истории и рекорды: синтетические данные, без сети."""
from datetime import timezone
import unittest
import urllib.error
from zoneinfo import ZoneInfo

from core_tools import (epley_1rm, is_warmup, load_workouts, local_workout_date,
                        register_core_tools, user_time_zone)


BENCH = '00000000-0000-4000-8000-0000000000b1'
SQUAT = '00000000-0000-4000-8000-0000000000b2'
DEADLIFT = '00000000-0000-4000-8000-0000000000b3'
KRSK = 'Asia/Krasnoyarsk'  # UTC+7 без перехода на летнее время


class Registry:
    def __init__(self):
        self.functions = {}

    def tool(self, **kwargs):
        def register(fn):
            self.functions[fn.__name__] = fn
            return fn
        return register


def workout(index, started=None, scheduled=None, set_created='2026-01-01T10:00:00Z', sets=None,
            exercise=BENCH, created='2026-01-01T09:00:00Z'):
    return {
        'id': f'00000000-0000-4000-8000-{index:012d}', 'startedAt': started,
        'scheduledDateLocal': scheduled, 'createdAt': created, 'isDeleted': False,
        'trainSessions': [{'exerciseId': exercise, 'sets': sets if sets is not None else [
            {'number': 1, 'weight': 50, 'reps': 5, 'isDone': True, 'createdAt': set_created}]}],
    }


class Backend:
    def __init__(self, workouts, time_zone=KRSK, settings_error=None):
        self.workouts = workouts
        self.time_zone = time_zone
        self.settings_error = settings_error
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == '/user/settings':
            if self.settings_error:
                raise self.settings_error
            return {'timeZoneId': self.time_zone}
        if path == '/workouts':
            offset, limit = params['offset'], params['limit']
            return {'items': self.workouts[offset:offset + limit], 'total': len(self.workouts)}
        if path == '/exercises':
            return {'items': [{'id': BENCH, 'name': 'Жим'}, {'id': SQUAT, 'name': 'Присед'},
                              {'id': DEADLIFT, 'name': 'Тяга'}]}
        raise AssertionError(path)


def tools(backend):
    registry = Registry()
    register_core_tools(registry, backend.get, 'http://127.0.0.1:9/api')
    return registry.functions


class WorkoutDateTests(unittest.TestCase):
    def test_started_at_is_converted_to_user_zone(self):
        late = workout(1, started='2026-10-20T18:30:00+00:00')
        self.assertEqual(local_workout_date(late, ZoneInfo(KRSK)), '2026-10-21')
        self.assertEqual(local_workout_date(late, timezone.utc), '2026-10-20')

    def test_started_at_wins_over_set_created_at(self):
        # Старое поведение брало UTC createdAt первого подхода (синхронизация позже).
        w = workout(1, started='2026-10-19T08:00:00Z', set_created='2026-10-22T01:00:00Z')
        self.assertEqual(local_workout_date(w, ZoneInfo(KRSK)), '2026-10-19')

    def test_scheduled_local_date_used_without_started_at(self):
        w = workout(1, scheduled='2026-10-18', set_created='2026-10-19T23:00:00Z')
        self.assertEqual(local_workout_date(w, ZoneInfo(KRSK)), '2026-10-18')

    def test_legacy_workout_falls_back_to_earliest_set_in_user_zone(self):
        w = workout(1, sets=[
            {'number': 2, 'weight': 50, 'reps': 5, 'isDone': True, 'createdAt': '2026-10-20T19:00:00.1234567+00:00'},
            {'number': 1, 'weight': 50, 'reps': 5, 'isDone': True, 'createdAt': '2026-10-20T17:30:00Z'},
        ])
        self.assertEqual(local_workout_date(w, ZoneInfo(KRSK)), '2026-10-21')
        self.assertEqual(local_workout_date(w, timezone.utc), '2026-10-20')

    def test_empty_legacy_workout_uses_workout_created_at(self):
        w = workout(1, sets=[], created='2026-10-20T20:00:00')
        self.assertEqual(local_workout_date(w, ZoneInfo(KRSK)), '2026-10-21')


class TimeZoneTests(unittest.TestCase):
    def test_settings_zone_or_utc_fallback(self):
        self.assertEqual(user_time_zone(Backend([]).get)[1], KRSK)
        for backend in [Backend([], time_zone='Mars/Olympus'), Backend([], time_zone=''),
                        Backend([], time_zone=None),
                        Backend([], settings_error=urllib.error.URLError('offline')),
                        Backend([], settings_error=ValueError('invalid json'))]:
            with self.subTest(zone=backend.time_zone, error=backend.settings_error):
                zone, name = user_time_zone(backend.get)
                self.assertIs(zone, timezone.utc)
                self.assertEqual(name, 'UTC')

    def test_forbidden_settings_fall_back_to_utc(self):
        error = urllib.error.HTTPError('http://127.0.0.1/api/user/settings', 403, 'Forbidden', {}, None)
        self.addCleanup(error.close)
        self.assertEqual(user_time_zone(Backend([], settings_error=error).get)[1], 'UTC')


class LoadWorkoutsTests(unittest.TestCase):
    def test_pages_until_total_and_reports_complete(self):
        backend = Backend([workout(i) for i in range(230)])
        items, complete = load_workouts(backend.get)
        self.assertEqual(len(items), 230)
        self.assertTrue(complete)
        self.assertEqual([p for _, p in backend.calls], [
            {'offset': 0, 'limit': 100}, {'offset': 100, 'limit': 100}, {'offset': 200, 'limit': 100}])

    def test_cap_is_reported_as_incomplete(self):
        backend = Backend([workout(i) for i in range(230)])
        items, complete = load_workouts(backend.get, max_items=150)
        self.assertEqual((len(items), complete), (150, False))
        self.assertEqual([p['limit'] for _, p in backend.calls], [100, 50])

    def test_list_response_without_total_stops_on_short_page(self):
        calls = []
        def get(path, params):
            calls.append(params)
            return [workout(1)] if params['offset'] == 0 else []
        self.assertEqual(load_workouts(get), ([workout(1)], True))
        self.assertEqual(len(calls), 1)


class GymWorkoutTests(unittest.TestCase):
    def test_finds_workout_older_than_last_fifty(self):
        history = [workout(i, started=f'2026-09-{1 + i % 28:02d}T05:00:00Z') for i in range(180)]
        history.append(workout(500, started='2026-03-10T20:00:00Z'))
        backend = Backend(history)
        result = tools(backend)['gym_workout']('2026-03-11')
        self.assertEqual(result['id'], history[-1]['id'])
        self.assertEqual(result['date'], '2026-03-11')
        self.assertEqual(result['exercises'][0]['name'], 'Жим')
        self.assertNotIn('other_workout_ids', result)
        self.assertEqual(backend.calls[0], ('/user/settings', None))

    def test_local_date_not_utc_date(self):
        backend = Backend([workout(1, started='2026-10-20T20:00:00Z')])
        functions = tools(backend)
        self.assertEqual(functions['gym_workout']('2026-10-21')['sets_count'], 1)
        missing = functions['gym_workout']('2026-10-20')
        self.assertIn('error', missing)
        self.assertIn(KRSK, missing['error'])
        self.assertIn('во всей истории', missing['error'])

    def test_settings_unavailable_uses_utc(self):
        backend = Backend([workout(1, started='2026-10-20T20:00:00Z')],
                          settings_error=urllib.error.URLError('offline'))
        self.assertEqual(tools(backend)['gym_workout']('2026-10-20')['date'], '2026-10-20')

    def test_several_workouts_same_day_prefers_done_sets_and_lists_others(self):
        empty = workout(1, started='2026-10-20T02:00:00Z', sets=[])
        done = workout(2, started='2026-10-20T10:00:00Z')
        result = tools(Backend([empty, done, workout(3, started='2026-10-01T10:00:00Z')]))['gym_workout']('2026-10-20')
        self.assertEqual(result['id'], done['id'])
        self.assertEqual(result['other_workout_ids'], [empty['id']])

    def test_invalid_date_rejected_before_network(self):
        backend = Backend([])
        for value in ['20261020', '2026-02-30', '2026-10-20T00:00:00']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                tools(backend)['gym_workout'](value)
        self.assertEqual(backend.calls, [])

    def test_recent_list_uses_local_dates(self):
        backend = Backend([workout(1, started='2026-10-20T20:00:00Z'), workout(2, started='2026-10-19T01:00:00Z')])
        result = tools(backend)['gym_workouts'](2)
        self.assertEqual([w['date'] for w in result], ['2026-10-21', '2026-10-19'])


class RecordsTests(unittest.TestCase):
    def test_epley_formula(self):
        self.assertEqual(epley_1rm(100, 5), 116.7)
        self.assertEqual(epley_1rm(100, 1), 100.0)
        self.assertEqual(epley_1rm(100, 0), 0.0)
        self.assertEqual(epley_1rm(60, 10), 80.0)

    def test_flag_wins_and_heuristic_only_for_null(self):
        self.assertTrue(is_warmup({'isWarmup': True, 'weight': 100, 'reps': 1}, 100))
        self.assertFalse(is_warmup({'isWarmup': False, 'weight': 20, 'reps': 20}, 100))
        self.assertTrue(is_warmup({'isWarmup': None, 'weight': 20, 'reps': 20}, 100))
        self.assertTrue(is_warmup({'weight': 20, 'reps': 20}, 100))
        self.assertFalse(is_warmup({'isWarmup': None, 'weight': 20, 'reps': 12}, 100))
        self.assertFalse(is_warmup({'isWarmup': None, 'weight': 70, 'reps': 20}, 100))

    def test_records_use_set_warmup_flag(self):
        bench = [
            # Отмеченная разминка не попадает в рекорд и не задаёт максимум эвристики.
            {'number': 1, 'weight': 140, 'reps': 3, 'isDone': True, 'isWarmup': True},
            {'number': 2, 'weight': 100, 'reps': 5, 'isDone': True, 'isWarmup': False},
        ]
        squat = [
            {'number': 1, 'weight': 100, 'reps': 1, 'isDone': True, 'isWarmup': None},
            # Рабочий многоповторный подход: эвристика выбросила бы его, флаг сохраняет.
            {'number': 2, 'weight': 50, 'reps': 40, 'isDone': True, 'isWarmup': False},
            {'number': 3, 'weight': 200, 'reps': 5, 'isDone': False, 'isWarmup': False},
        ]
        deadlift = [
            {'number': 1, 'weight': 100, 'reps': 1, 'isDone': True},
            # Старый подход без флага: меньше 60% максимума и больше 12 повторов — разминка.
            {'number': 2, 'weight': 50, 'reps': 40, 'isDone': True, 'isWarmup': None},
        ]
        backend = Backend([workout(1, started='2026-10-20T20:00:00Z', sets=bench),
                           workout(2, started='2026-10-10T08:00:00Z', sets=squat, exercise=SQUAT),
                           workout(3, started='2026-10-05T08:00:00Z', sets=deadlift, exercise=DEADLIFT)])
        records = {r['exercise']: r for r in tools(backend)['gym_records']()}
        self.assertEqual(records['Жим'], {'exercise': 'Жим', 'rm': 116.7, 'weight': 100, 'reps': 5,
                                          'date': '2026-10-21'})
        self.assertEqual((records['Присед']['weight'], records['Присед']['reps'], records['Присед']['rm']),
                         (50, 40, 116.7))
        self.assertEqual((records['Тяга']['weight'], records['Тяга']['reps'], records['Тяга']['rm']),
                         (100, 1, 100.0))
        self.assertEqual([p for path, p in backend.calls if path == '/workouts'], [{'offset': 0, 'limit': 200}])

if __name__ == '__main__':
    unittest.main()
