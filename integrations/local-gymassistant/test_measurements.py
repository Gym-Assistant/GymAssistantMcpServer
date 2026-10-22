"""Новые форматы планов/чтения MCP; синтетические данные, без сервера."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from plan_tools import PlanSet
from workout_tools import summarize_workout, build_records
import test_plan_tools as plans
import test_append_tools as append_tests
from test_plan_tools import day
from install_plans import install, measurement_source

MEASUREMENTS = [
    {'trackingType': 'weight_reps', 'side': 'left'},
    {'trackingType': 'bodyweight_reps', 'heightCm': 40},
    {'trackingType': 'assisted_reps', 'assistanceWeight': 12.5},
    {'trackingType': 'band_reps', 'resistanceLevel': 'red'},
    {'trackingType': 'duration', 'durationSeconds': 45},
    {'trackingType': 'cardio', 'durationSeconds': 120, 'distanceMeters': 500, 'inclinePercent': 3},
    {'trackingType': 'weight_distance', 'distanceMeters': 25},
    {'trackingType': 'interval', 'rounds': 5, 'workSeconds': 30, 'recoverySeconds': 60},
]


def typed_sets():
    return [{'measurement': deepcopy(value), **({'reps': 8} if index < 4 else {})}
            for index, value in enumerate(MEASUREMENTS)]


class TypedCreationTests(unittest.TestCase):
    def setUp(self):
        self.harness = plans.PlanToolsTests()
        self.harness.setUp()
        self.create, self.posts = self.harness.create, self.harness.posts

    def test_all_formats_are_sent_and_legacy_fields_keep_their_values(self):
        values = typed_sets() + [{'reps': 12, 'weight': 82.5, 'unit': 'lb'}]
        self.create(days=[day(sets=values)])
        actual = self.posts[0]['templates'][0]['exercises'][0]['sets']
        self.assertEqual([s['measurement'] for s in actual[:-1]], MEASUREMENTS)
        self.assertEqual([s['reps'] for s in actual], [8, 8, 8, 8, 0, 0, 0, 0, 12])
        self.assertNotIn('measurement', actual[-1])
        self.assertEqual((actual[-1]['targetWeight'], actual[-1]['weightUnit']), (82.5, 'lb'))

    def test_invalid_measurements_are_rejected_before_post(self):
        for measurement in [
            {'trackingType': 'cardio'},
            {'trackingType': 'cardio', 'durationSeconds': -1},
            {'trackingType': 'cardio', 'durationSeconds': 1.5},
            {'trackingType': 'duration', 'distanceMeters': 1},
            {'trackingType': 'cardio', 'distanceMeters': float('nan')},
            {'trackingType': 'interval', 'rounds': 1, 'workSeconds': 0},
            {'trackingType': 'weight_reps', 'assistanceWeight': 1},
            {'trackingType': 'unknown'},
        ]:
            with self.subTest(measurement=measurement), self.assertRaises(ValidationError):
                self.create(days=[day(sets=[{'reps': 8, 'measurement': measurement}])])
        self.assertEqual(self.posts, [])


class TypedAppendTests(unittest.TestCase):
    def setUp(self):
        self.harness = append_tests.AppendTests()
        self.harness.setUp()
        self.plan, self.posts, self.backups = self.harness.plan, self.harness.posts, self.harness.backups
        self.call = self.harness.call

    def test_append_preserves_old_typed_tree_and_new_measurements(self):
        self.plan['templates'][0]['exercises'][0]['sets'][0]['measurement'] = {
            'trackingType': 'cardio', 'durationSeconds': 60, 'futureField': {'a': 1}}
        before = deepcopy(self.plan)
        result = self.call(days=[day(sets=typed_sets())])
        self.assertEqual(result['status'], 'appended')
        self.assertEqual(self.plan, before)
        self.assertEqual(self.backups[0][0], before)
        sets = self.posts[0][1]['templates'][0]['exercises'][0]['sets']
        self.assertEqual([s['measurement'] for s in sets], MEASUREMENTS)


class WorkoutMeasurementTests(unittest.TestCase):
    def fixture(self):
        old = {'weight': 80, 'reps': 10, 'isDone': True, 'number': 1}
        cardio = {'weight': 200, 'reps': 100, 'isDone': True, 'number': 2,
                  'measurement': {'trackingType': 'cardio', 'durationSeconds': 120,
                                  'distanceMeters': 500, 'futureField': {'samples': [1, 2]}}}
        return {'id': 'w', 'trainSessions': [{'exerciseId': 'e', 'sets': [old, cardio]}]}

    def test_summary_keeps_measurement_but_does_not_reinterpret_history_from_current_exercise(self):
        workout = self.fixture()
        original = deepcopy(workout)
        result = summarize_workout(workout, {'e': {'name': 'Exercise', 'trackingType': 'cardio'}}, lambda _: '2026-10-22')
        self.assertEqual(result['volume_kg'], 800)
        self.assertEqual(result['sets_count'], 2)
        self.assertEqual(result['exercises'][0]['trackingType'], 'cardio')
        self.assertEqual(result['exercises'][0]['sets'][1]['measurement'], workout['trainSessions'][0]['sets'][1]['measurement'])
        self.assertEqual(result['exercises'][0]['top'], {'weight': 80, 'reps': 10})
        result['exercises'][0]['sets'][1]['measurement']['futureField']['samples'].append(3)
        self.assertEqual(workout, original)

    def test_records_ignore_explicit_non_strength_without_changing_old_estimate(self):
        records = build_records([self.fixture()], {'e': {'name': 'Exercise', 'trackingType': 'cardio'}},
                                25, lambda _: '2026-10-22', lambda w, r: round(w * (1 + r / 30), 1))
        self.assertEqual(records, [{'exercise': 'Exercise', 'weight': 80, 'reps': 10, 'rm': 106.7, 'date': '2026-10-22'}])

    def test_unknown_measurement_is_retained_without_strength_guess(self):
        workout = self.fixture()
        workout['trainSessions'][0]['sets'] = [dict(workout['trainSessions'][0]['sets'][1], measurement={'trackingType': 'future'})]
        result = summarize_workout(workout, {}, lambda _: None)
        self.assertEqual(result['volume_kg'], 0)
        self.assertIsNone(result['exercises'][0]['top'])
        self.assertEqual(result['exercises'][0]['sets'][0]['measurement'], {'trackingType': 'future'})


class InstallerMeasurementTests(unittest.TestCase):
    def test_idempotent_install_backs_up_source_and_keeps_launcher_health_unchanged(self):
        source = '''from pathlib import Path
register_health_tools(mcp, _api_get)
def _summarize_workout(w, ex_idx):
    return {"old": True}
@mcp.tool()
def gym_records(top_n: int = 25) -> list[dict]:
    """Existing public description."""
    return []
if __name__ == "__main__":
    mcp.run()
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'server.py').write_text(source)
            (root / 'run.sh').write_text('original launcher')
            (root / 'health_tools.py').write_text('original health')
            with patch('builtins.print'):
                install(root)
                first = (root / 'server.py').read_text()
                install(root)
            self.assertEqual((root / 'server.py').read_text(), first)
            self.assertEqual((root / 'run.sh').read_text(), 'original launcher')
            self.assertEqual((root / 'health_tools.py').read_text(), 'original health')
            copies = list((root / '.backups').glob('*/server.py'))
            self.assertEqual(len(copies), 2)
            self.assertIn(source, [p.read_text() for p in copies])
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in copies))
            self.assertIn('Existing public description.', first)
            self.assertEqual(first.count('from workout_tools import'), 1)
            self.assertTrue((root / 'workout_tools.py').exists())

    def test_unknown_signature_is_rejected(self):
        with self.assertRaises(ValueError):
            measurement_source('def _summarize_workout(w):\n    pass\n')
