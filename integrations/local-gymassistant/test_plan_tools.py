"""Контракт планов MCP: только синтетические данные, без сети и production."""
import asyncio
import copy
from http.client import IncompleteRead
import json
import unittest
import urllib.error
from unittest.mock import patch
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from plan_tools import PlanDay, register_plan_tools, make_plan_writer


OWNER = '00000000-0000-4000-8000-000000000001'
PERSONAL = '00000000-0000-4000-8000-000000000002'
GLOBAL = '00000000-0000-4000-8000-000000000003'
DEFAULT = '00000000-0000-4000-8000-000000000004'
OTHER = '00000000-0000-4000-8000-000000000005'


class Registry:
    def __init__(self):
        self.functions = {}
        self.annotations = {}

    def tool(self, **kwargs):
        def register(fn):
            self.functions[fn.__name__] = fn
            self.annotations[fn.__name__] = kwargs['annotations']
            return fn
        return register


def day(exercise_id=PERSONAL, source='personal', sets=None, title='День А', comment='По самочувствию'):
    return {
        'title': title,
        'description': 'Согласованный план',
        'exercises': [{
            'user_exercise_id' if source == 'personal' else 'default_exercise_id': exercise_id,
            'comment': comment,
            'sets': sets if sets is not None else [{'reps': 8, 'weight': 40}],
        }],
    }


class PlanToolsTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.calls = []
        self.posts = []
        self.error = None
        self.data = {
            '/plans': [],
            '/exercises': [{'id': PERSONAL, 'globalId': GLOBAL, 'name': 'Личный жим', 'isDeleted': False}],
            '/exercises/defaults': [{'globalId': DEFAULT, 'name': 'Подтягивания'}],
        }
        # GET /plans/{id}: backend не фильтрует владельца, поэтому здесь есть и чужие планы.
        self.by_id = {}
        register_plan_tools(self.registry, self.get, self.post)

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == '/auth/me':
            return {'id': OWNER}
        if path.startswith('/exercises/defaults/'):
            return copy.deepcopy(next(item for item in self.data['/exercises/defaults']
                                      if item['globalId'] == path.rsplit('/', 1)[1]))
        if path.startswith('/plans/'):
            plan_id = path.removeprefix('/plans/')
            if plan_id not in self.by_id:
                raise urllib.error.HTTPError(f'https://example.invalid/api{path}', 404, 'Not Found', {}, None)
            return copy.deepcopy(self.by_id[plan_id])
        items = self.data[path]
        offset = params['offset']
        return {'items': copy.deepcopy(items[offset:offset + params['limit']]), 'total': len(items)}

    def post(self, body):
        self.posts.append(copy.deepcopy(body))
        if self.error:
            raise self.error

    def create(self, **kwargs):
        args = {'name': '  План возвращения  ', 'days': [day()]}
        args.update(kwargs)
        return self.registry.functions['gym_create_plan'](**args)

    def test_fresh_hierarchy_ids_and_relationships(self):
        result = self.create(days=[day(), day(title='День Б')])
        plan = self.posts[0]
        self.assertEqual(result, {'status': 'created', 'plan_id': plan['id'],
                                 'name': 'План возвращения', 'days': 2, 'sets': 2})
        self.assertFalse(plan['isPublished'])
        self.assertFalse(plan['isDeleted'])
        self.assertEqual(plan['revision'], 1)
        self.assertEqual(plan['authorUserId'], OWNER)
        self.assertEqual(len(plan['exercises']), 1)
        nodes = [plan, *plan['exercises']]
        for index, template in enumerate(plan['templates']):
            self.assertEqual(template['sortOrder'], index)
            self.assertEqual(template['planId'], plan['id'])
            nodes.append(template)
            for ex_index, exercise in enumerate(template['exercises']):
                self.assertEqual(exercise['planTemplateId'], template['id'])
                self.assertEqual(exercise['planExerciseId'], plan['exercises'][0]['id'])
                self.assertEqual(exercise['sortOrder'], ex_index)
                nodes.append(exercise)
                for number, entry in enumerate(exercise['sets'], 1):
                    self.assertEqual(entry['number'], number)
                    self.assertEqual(entry['planTemplateExerciseId'], exercise['id'])
                    nodes.append(entry)
        ids = {node['id'] for node in nodes}
        self.assertEqual(len(ids), len(nodes))
        self.assertTrue(ids.isdisjoint({OWNER, PERSONAL, GLOBAL, DEFAULT}))
        for node in nodes:
            UUID(node['id'])
            self.assertEqual(node['createdById'], OWNER)
            self.assertEqual(node['createdAt'], plan['createdAt'])
            self.assertEqual(node['updatedAt'], plan['updatedAt'])
        self.assertEqual(self.calls.count(('/auth/me', None)), 1)

    def test_preserves_own_exercise_name_and_global_reference(self):
        self.create()
        entry = self.posts[0]['exercises'][0]
        self.assertEqual(entry['userExerciseId'], PERSONAL)
        self.assertEqual(entry['defaultExerciseGlobalId'], GLOBAL)
        self.assertEqual(entry['displayName'], 'Личный жим')

    def test_default_reference_requires_no_personal_exercise_creation(self):
        self.create(days=[day(DEFAULT, 'default')])
        plan = self.posts[0]
        self.assertIsNone(plan['exercises'][0]['userExerciseId'])
        self.assertEqual(plan['exercises'][0]['defaultExerciseGlobalId'], DEFAULT)
        self.assertEqual(plan['exercises'][0]['displayName'], 'Подтягивания')
        self.assertEqual([path for path, _ in self.calls], ['/exercises/defaults', '/auth/me'])
        self.assertEqual(len(self.posts), 1)

    def test_same_exercise_reuses_pool_but_preserves_each_occurrence(self):
        first = day(comment='Первое упражнение')
        first['exercises'].append(copy.deepcopy(first['exercises'][0]))
        first['exercises'][1]['comment'] = 'Повтор упражнения'
        self.create(days=[first, day(title='День Б', comment='Другой день')])
        plan = self.posts[0]
        self.assertEqual(len(plan['exercises']), 1)
        exercises = [e for t in plan['templates'] for e in t['exercises']]
        self.assertEqual([e['sortOrder'] for e in exercises], [0, 1, 0])
        self.assertEqual([e['comment'] for e in exercises],
                         ['Первое упражнение', 'Повтор упражнения', 'Другой день'])
        self.assertEqual(len({e['id'] for e in exercises}), 3)
        self.assertEqual(len({e['planExerciseId'] for e in exercises}), 1)

    def test_set_order_warmup_units_rest_rpe_and_null_are_preserved(self):
        self.create(work_rest_seconds=120, warmup_rest_seconds=0, days=[day(sets=[
            {'reps': 20, 'weight': 0, 'warmup': True, 'rest_seconds': 0},
            {'reps': 9, 'weight': 80.5, 'unit': 'lb', 'rpe': 7.5, 'rest_seconds': 90},
            {'reps': 8, 'weight_percent': 70},
            {'reps': 7},
        ])])
        plan = self.posts[0]
        self.assertEqual(plan['restDefaults'], {'0': 120, '1': 0})
        sets = plan['templates'][0]['exercises'][0]['sets']
        self.assertEqual([s['number'] for s in sets], [1, 2, 3, 4])
        self.assertEqual([s['setType'] for s in sets], [1, 0, 0, 0])
        self.assertEqual([s['targetWeight'] for s in sets], [0, 80.5, None, None])
        self.assertEqual([s['targetWeightPercent'] for s in sets], [None, None, 70, None])
        self.assertEqual([s['weightUnit'] for s in sets], ['kg', 'lb', 'kg', 'kg'])
        self.assertEqual([s['restSecondsOverride'] for s in sets], [0, 90, None, None])
        self.assertEqual([s['targetRpe'] for s in sets], [None, 7.5, None, None])

    def test_unset_plan_rest_stays_null(self):
        self.create()
        self.assertIsNone(self.posts[0]['restDefaults'])

    def test_rejects_unknown_or_deleted_exercise_before_any_post(self):
        for deleted, reference in [(False, OTHER), (True, PERSONAL)]:
            with self.subTest(deleted=deleted):
                self.data['/exercises'][0]['isDeleted'] = deleted
                with self.assertRaises(ValueError):
                    self.create(days=[day(reference)])
        self.assertEqual(self.posts, [])
        self.assertNotIn(('/auth/me', None), self.calls)

    def test_scans_all_pages_before_resolving_exercises(self):
        self.data['/exercises'] = [
            {'id': str(UUID(int=index + 10)), 'name': f'Упражнение {index}'}
            for index in range(101)
        ] + self.data['/exercises']
        self.create()
        calls = [params for path, params in self.calls if path == '/exercises']
        self.assertEqual(calls, [{'offset': 0, 'limit': 100}, {'offset': 100, 'limit': 100}])

    def test_read_plan_uses_id_endpoint_once_and_checks_author(self):
        self.data['/plans'] = [{'id': str(UUID(int=index + 10))} for index in range(101)]
        self.by_id[PERSONAL] = {'id': PERSONAL, 'authorUserId': OWNER.upper(), 'name': 'Нужный план'}
        result = self.registry.functions['gym_plan'](UUID(PERSONAL))
        self.assertEqual(result['name'], 'Нужный план')
        # Без перебора страниц /plans: один профиль и один GET по ID.
        self.assertEqual(self.calls, [('/auth/me', None), (f'/plans/{PERSONAL}', None)])

    def test_foreign_plan_from_unscoped_id_endpoint_is_not_returned(self):
        self.by_id[PERSONAL] = {'id': PERSONAL, 'authorUserId': OTHER, 'isPublished': True, 'name': 'Чужой'}
        with self.assertRaisesRegex(ValueError, 'не найден'):
            self.registry.functions['gym_plan'](UUID(PERSONAL))
        for broken in [{'id': PERSONAL}, {'id': PERSONAL, 'authorUserId': 'not-a-guid'},
                       {'id': OTHER, 'authorUserId': OWNER}, []]:
            self.by_id[PERSONAL] = broken
            with self.subTest(plan=broken), self.assertRaises(ValueError):
                self.registry.functions['gym_plan'](UUID(PERSONAL))

    def test_missing_plan_404_is_not_found(self):
        with self.assertRaisesRegex(ValueError, 'не найден'):
            self.registry.functions['gym_plan'](UUID(OTHER))

    def test_other_http_errors_are_not_masked_as_not_found(self):
        def denied(path, params=None):
            if path == '/auth/me':
                return {'id': OWNER}
            raise urllib.error.HTTPError('https://example.invalid/api/plans', 403, 'Forbidden', {}, None)
        registry = Registry()
        register_plan_tools(registry, denied, self.post)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            registry.functions['gym_plan'](UUID(PERSONAL))
        caught.exception.close()
        self.assertEqual(caught.exception.code, 403)

    def test_deleted_plan_is_not_returned(self):
        self.by_id[PERSONAL] = {'id': PERSONAL, 'authorUserId': OWNER, 'isDeleted': True}
        with self.assertRaises(ValueError):
            self.registry.functions['gym_plan'](UUID(PERSONAL))

    def test_read_tools_preserve_pagination_and_data(self):
        self.registry.functions['gym_plans'](offset=20, limit=5)
        self.registry.functions['gym_exercises'](source='default', offset=10, limit=20)
        self.registry.functions['gym_exercises'](source='personal', offset=1, limit=3)
        self.assertEqual(self.calls, [
            ('/plans', {'offset': 20, 'limit': 5}),
            ('/exercises/defaults', {'offset': 10, 'limit': 20}),
            ('/exercises', {'offset': 1, 'limit': 3}),
        ])
        self.assertEqual(self.posts, [])

    def test_http_403_is_explicit_rejection_with_no_retry(self):
        self.error = urllib.error.HTTPError('https://example.invalid/plans', 403, 'Denied', {}, None)
        self.addCleanup(self.error.close)
        with self.assertRaisesRegex(ValueError, 'HTTP 403'):
            self.create()
        self.assertEqual(len(self.posts), 1)

    def test_timeout_and_server_error_remain_unknown_with_original_id_no_retry(self):
        errors = [TimeoutError('timed out'), urllib.error.URLError('offline'), IncompleteRead(b'partial'),
                  urllib.error.HTTPError('https://example.invalid/plans', 500, 'Error', {}, None)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                if isinstance(error, urllib.error.HTTPError):
                    self.addCleanup(error.close)
                self.posts.clear()
                self.error = error
                result = self.create()
                self.assertEqual(result['status'], 'unknown')
                self.assertEqual(result['plan_id'], self.posts[0]['id'])
                self.assertEqual(len(self.posts), 1)

    def test_generated_ids_are_not_reused_between_intentional_calls(self):
        first, second = self.create(), self.create()
        self.assertNotEqual(first['plan_id'], second['plan_id'])

    def test_invalid_weight_modes_units_and_references_rejected_before_network(self):
        examples = [day(sets=[{'reps': 8, 'weight': 10, 'weight_percent': 50}]),
                    day(sets=[{'reps': 0}]), day(sets=[{'reps': 8, 'unit': 'stone'}]),
                    day(sets=[{'reps': 8, 'weight': float('nan')}]),
                    day(sets=[{'reps': 8, 'weight': -1}]),
                    day(sets=[{'reps': 8, 'rest_seconds': -1}])]
        both = day()
        both['exercises'][0]['default_exercise_id'] = DEFAULT
        examples.append(both)
        neither = day()
        del neither['exercises'][0]['user_exercise_id']
        examples.append(neither)
        for invalid in examples:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.create(days=[invalid])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.posts, [])

    def test_caller_cannot_supply_entity_ids_or_publication_flags(self):
        for location, field in [('day', 'id'), ('exercise', 'plan_id'), ('set', 'id')]:
            invalid = day()
            target = {'day': invalid, 'exercise': invalid['exercises'][0],
                      'set': invalid['exercises'][0]['sets'][0]}[location]
            target[field] = PERSONAL
            with self.subTest(location=location), self.assertRaises(ValidationError):
                PlanDay.model_validate(invalid)
        with self.assertRaises(TypeError):
            self.create(plan_id=PERSONAL)
        with self.assertRaises(TypeError):
            self.create(isPublished=True)
        self.assertEqual(self.posts, [])

    def test_registered_schema_has_no_caller_plan_identity_and_correct_annotations(self):
        mcp = FastMCP('synthetic-plan-tests')
        register_plan_tools(mcp, self.get, self.post)
        tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
        create = tools['gym_create_plan']
        self.assertNotIn('id', create.inputSchema['properties'])
        self.assertNotIn('plan_id', create.inputSchema['properties'])
        self.assertFalse(create.annotations.readOnlyHint)
        self.assertFalse(create.annotations.destructiveHint)
        self.assertFalse(create.annotations.idempotentHint)
        for name in ['gym_plans', 'gym_plan', 'gym_exercises', 'gym_default_exercise']:
            self.assertTrue(tools[name].annotations.readOnlyHint)
        self.assertEqual(self.calls, [])

    def test_catalog_read_preserves_metadata_and_hidden_identity(self):
        item = self.data['/exercises/defaults'][0]
        item.update({'nameEn': 'Pull-up', 'descriptionEn': 'Controlled movement',
                     'templateRevision': 'ga043-2026-10-22-v1',
                     'aliasesEn': ['Pull up'], 'groupCode': 'back', 'loadConvention': 'total',
                     'isUnilateral': False, 'isHidden': True, 'canonicalId': GLOBAL,
                     'muscles': [{'muscleCode': 'lats', 'role': 'primary', 'loadPercent': 70}],
                     'media': [{'kind': 'image', 'url': 'https://example.invalid/pull-up.webp',
                                'frames': ['https://example.invalid/pull-up-start.webp']}],
                     'futureMetadata': {'retain': True}})
        result = self.registry.functions['gym_exercises'](source='default', include_hidden=True)
        self.assertEqual(result['items'][0], item)
        self.assertEqual(self.calls[-1], ('/exercises/defaults',
                                         {'offset': 0, 'limit': 50, 'includeHidden': 'true'}))
        result = self.registry.functions['gym_default_exercise'](UUID(DEFAULT))
        self.assertEqual(result, item)
        self.assertEqual(self.calls[-1], ('/exercises/defaults/' + DEFAULT, None))
        self.assertEqual(result['globalId'], DEFAULT)
        self.assertEqual(self.posts, [])

    def test_personal_provenance_roundtrip_keeps_identity_and_legacy_absence(self):
        item = self.data['/exercises'][0]
        legacy = copy.deepcopy(item)
        result = self.registry.functions['gym_exercises'](source='personal')
        self.assertEqual(result['items'][0], legacy)
        self.assertNotIn('templateRevision', result['items'][0])
        self.assertNotIn('templateOverrides', result['items'][0])
        for overrides in (None, [], ['name', 'loadConvention']):
            item.update({'templateRevision': 'ga043-2026-10-22-v1', 'templateOverrides': overrides,
                         'loadConvention': None, 'oneRepMax': 97.5, 'gymIds': ['fixture-gym']})
            with self.subTest(overrides=overrides):
                result = self.registry.functions['gym_exercises'](source='personal')['items'][0]
                self.assertEqual(result, item)
                self.assertEqual(result['id'], PERSONAL)
                self.assertEqual(result['globalId'], GLOBAL)
        self.assertEqual(self.posts, [])

    def test_catalog_default_call_remains_compatible_and_hidden_option_is_not_ignored(self):
        self.registry.functions['gym_exercises']()
        self.assertEqual(self.calls, [('/exercises', {'offset': 0, 'limit': 50})])
        with self.assertRaisesRegex(ValueError, 'include_hidden'):
            self.registry.functions['gym_exercises'](source='personal', include_hidden=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.posts, [])


class PlanWriterTests(unittest.TestCase):
    def test_posts_utf8_json_once_to_expected_route_and_ignores_empty_response(self):
        body = {'name': 'План', 'id': PERSONAL}
        with patch('plan_tools.urllib.request.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b''
            make_plan_writer('https://example.invalid/api/', 'synthetic-token')(body)
            urlopen.assert_called_once()
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, 'https://example.invalid/api/plans')
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(json.loads(request.data.decode('utf-8')), body)
            self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-token')
            self.assertEqual(urlopen.call_args.kwargs['timeout'], 30)

    def test_writer_does_not_retry_network_error(self):
        with patch('plan_tools.urllib.request.urlopen', side_effect=TimeoutError) as urlopen:
            with self.assertRaises(TimeoutError):
                make_plan_writer('https://example.invalid/api', 'synthetic-token')({'id': PERSONAL})
            urlopen.assert_called_once()


if __name__ == '__main__':
    unittest.main()
