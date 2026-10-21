"""Добавление дней: сохранность прежнего плана и однократная запись."""
import copy
from datetime import datetime, timezone
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from uuid import UUID

from plan_tools import register_plan_tools, _backup_plan, make_plan_appender
from test_plan_tools import Registry, OWNER, PERSONAL, GLOBAL, DEFAULT, OTHER, day

PLAN = '10000000-0000-4000-8000-000000000001'
STAMP = '2026-10-21T09:00:00+00:00'


class AppendTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.posts, self.backups = [], []
        self.error = None
        self.plan = {'id': PLAN, 'authorUserId': OWNER, 'name': 'Возвращение',
                     'description': 'Существующее описание', 'createdById': OWNER,
                     'createdAt': STAMP, 'updatedAt': STAMP, 'revision': 3,
                     'isPublished': False, 'isDeleted': False, 'restDefaults': {'0': 120},
                     'exercises': [{'id': OTHER, 'planId': PLAN, 'userExerciseId': PERSONAL,
                                    'defaultExerciseGlobalId': GLOBAL, 'displayName': 'Особый жим',
                                    'notes': 'Старая заметка'}],
                     'templates': [{'id': GLOBAL, 'planId': PLAN, 'sortOrder': 5, 'title': 'День 1',
                                    'exercises': [{'id': DEFAULT, 'planExerciseId': OTHER,
                                                   'comment': 'Осторожно', 'sets': [{'id': PERSONAL,
                                                       'number': 1, 'reps': 10, 'targetWeight': 14,
                                                       'weightUnit': 'kg', 'setType': 1}]}]}]}
        register_plan_tools(self.registry, self.get, lambda body: self.fail('Нельзя полное сохранение'),
                            self.append, lambda old, body: self.backups.append(copy.deepcopy((old, body))))

    def get(self, path, params=None):
        if path == '/auth/me': return {'id': OWNER}
        if path == '/plans': return {'items': [copy.deepcopy(self.plan)], 'total': 1}
        if path == '/exercises': return {'items': [{'id': PERSONAL, 'globalId': GLOBAL, 'name': 'Жим'}], 'total': 1}
        if path == '/exercises/defaults': return {'items': [{'globalId': DEFAULT, 'name': 'Присед'}], 'total': 1}
        raise AssertionError(path)

    def append(self, plan_id, body):
        self.posts.append(copy.deepcopy((plan_id, body)))
        if self.error: raise self.error
        saved = copy.deepcopy(self.plan)
        saved['exercises'] += copy.deepcopy(body['exercises'])
        start = max(t['sortOrder'] for t in saved['templates']) + 1
        for i, t in enumerate(body['templates']):
            added = copy.deepcopy(t); added['sortOrder'] = start + i
            saved['templates'].append(added)
        saved['updatedAt'] = '2026-10-21T09:01:00+00:00'
        return saved

    def call(self, **extra):
        args = {'plan_id': UUID(PLAN), 'expected_updated_at': STAMP,
                'days': [day(title=f'День {i}') for i in range(2, 9)]}
        args.update(extra)
        return self.registry.functions['gym_append_plan_days'](**args)

    def test_one_to_eight_preserves_old_tree_and_reuses_existing_pool(self):
        before = copy.deepcopy(self.plan)
        result = self.call()
        self.assertEqual(result['status'], 'appended')
        self.assertEqual((result['added_days'], result['total_days']), (7, 8))
        self.assertEqual(self.plan, before)
        self.assertEqual(self.backups[0][0], before)
        self.assertEqual(len(self.posts), 1)
        plan_id, addition = self.posts[0]
        self.assertEqual(plan_id, PLAN)
        self.assertEqual(set(addition), {'expectedUpdatedAt', 'exercises', 'templates'})
        self.assertEqual(addition['exercises'], [])
        self.assertEqual(len(set(result['added_day_ids'])), 7)
        for t in addition['templates']:
            self.assertEqual(t['planId'], PLAN)
            self.assertNotEqual(t['id'], GLOBAL)
            self.assertEqual(t['exercises'][0]['planExerciseId'], OTHER)
            self.assertEqual(t['exercises'][0]['displayName'], 'Особый жим')

    def test_new_default_adds_only_new_pool_reference(self):
        self.call(days=[day(DEFAULT, 'default')])
        addition = self.posts[0][1]
        self.assertEqual(len(addition['exercises']), 1)
        self.assertEqual(addition['exercises'][0]['defaultExerciseGlobalId'], DEFAULT)
        self.assertEqual(addition['templates'][0]['exercises'][0]['planExerciseId'], addition['exercises'][0]['id'])

    def test_stale_or_foreign_plan_never_written(self):
        with self.assertRaises(ValueError): self.call(expected_updated_at='2026-10-20T00:00:00Z')
        self.plan['authorUserId'] = OTHER
        with self.assertRaises(ValueError): self.call()
        self.assertEqual(self.posts, [])
        self.assertEqual(self.backups, [])

    def test_missing_timezone_rejected(self):
        with self.assertRaises(ValueError): self.call(expected_updated_at='2026-10-21T09:00:00')
        self.assertEqual(self.posts, [])

    def test_server_conflict_after_read_is_not_retried(self):
        self.error = urllib.error.HTTPError('http://localhost/plans', 409, 'Conflict', {}, None)
        self.addCleanup(self.error.close)
        with self.assertRaisesRegex(ValueError, '409'): self.call()
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.backups), 1)

    def test_unconfirmed_response_keeps_added_ids_and_does_not_retry(self):
        for error in [TimeoutError(), IncompleteRead(b''), ValueError('invalid JSON'),
                      urllib.error.HTTPError('http://localhost/plans', 500, 'Error', {}, None)]:
            if isinstance(error, urllib.error.HTTPError): self.addCleanup(error.close)
            self.error = error; self.posts.clear()
            result = self.call()
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['added_day_ids'], [t['id'] for t in self.posts[0][1]['templates']])
            self.assertEqual(len(self.posts), 1)

    def test_unexpected_loss_is_not_reported_as_success(self):
        def broken(plan_id, body):
            saved = self.append(plan_id, body)
            saved['templates'][0]['exercises'][0]['sets'] = []
            return saved
        register_plan_tools(self.registry, self.get, None, broken, lambda old, body: None)
        self.assertEqual(self.call()['status'], 'unknown')

    def test_malformed_success_keeps_ids_for_manual_verification(self):
        for result in [{'id': PLAN, 'templates': None}, {**self.plan, 'templates': [{}]}]:
            register_plan_tools(self.registry, self.get, None, lambda p, body: result, lambda old, body: None)
            self.assertEqual(self.call()['status'], 'unknown')

    def test_backup_failure_blocks_write(self):
        def fail(old, body): raise OSError('disk full')
        register_plan_tools(self.registry, self.get, None, self.append, fail)
        with self.assertRaises(OSError): self.call()
        self.assertEqual(self.posts, [])

    def test_private_backup_is_restorable(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GYM_PLAN_BACKUP_DIR': directory}):
            _backup_plan(self.plan, {'templates': []})
            paths = list(Path(directory).glob('*.json'))
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(paths[0].read_text())['before'], self.plan)

    def test_writer_uses_append_endpoint_and_returns_plan(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({'id': PLAN}).encode()
        with patch('plan_tools.urllib.request.urlopen', return_value=Response()) as call:
            result = make_plan_appender('http://127.0.0.1:4321/api', 'fixture')(PLAN, {'templates': []})
            request = call.call_args.args[0]
            self.assertEqual(request.full_url, f'http://127.0.0.1:4321/api/plans/{PLAN}/days')
            self.assertEqual(request.method, 'POST')
            self.assertEqual(result, {'id': PLAN})
            self.assertEqual(call.call_count, 1)


if __name__ == '__main__': unittest.main()
