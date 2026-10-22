"""Изолированная приёмка планов через настоящий stdio локального MCP.

Запуск окружением с зависимостями из requirements.txt:
  python integrations/local-gymassistant/verify_plans_stdio.py              # код из репозитория
  python integrations/local-gymassistant/verify_plans_stdio.py /путь/к/установке
Проверяется временная копия server.py и модулей; исходный каталог не меняется.
API — синтетический loopback, токен — тестовый, env-файл — пустой временный.
"""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Thread
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SOURCE = Path(__file__).resolve().parent
MODULES = ['server.py', 'core_tools.py', 'health_tools.py', 'plan_tools.py']
TOKEN = 'gma_synthetic_fixture_only'
OWNER = '11111111-1111-4111-8111-111111111111'
PERSONAL = '22222222-2222-4222-8222-222222222222'
DEFAULT = '33333333-3333-4333-8333-333333333333'
EXISTING = {
    'gym_me', 'gym_workouts', 'gym_workout', 'gym_records', 'gym_body_latest',
    'gym_body_history', 'gym_status', 'gym_health_daily', 'gym_health_metrics',
}
CREATION_TOOLS = {'gym_plans', 'gym_plan', 'gym_exercises', 'gym_create_plan'}
ADDED = CREATION_TOOLS | {'gym_append_plan_days'}
HEALTH = [{
    'snapshot': {
        'day': '2026-10-20', 'timeZone': 'Asia/Krasnoyarsk',
        'readAt': '2026-10-20T21:00:00Z',
        'values': {'steps': 7307, 'protein': None, 'sleepTotal': 7.5},
        'valueReadAt': {'steps': '2026-10-20T21:00:00Z'},
        'valueDeviceIds': {'steps': ['fixture-watch']},
    },
    'receivedAt': '2026-10-20T21:01:00Z', 'deviceId': 'fixture-phone',
}]
METRICS = {'metrics': [{'key': 'steps', 'unit': 'count', 'aggregation': 'sum'}]}


class Fixture:
    def __init__(self):
        self.requests = []
        self.posts = []
        self.plans = []
        self.next_post_status = 200
        self.append_posts = []
        self.backup_dir = None
        self.backups_verified = []
        self.next_append_status = 200
        self.next_append_malformed = False

    def handler(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def authorized(self):
                fixture.requests.append((self.command, self.path, self.headers.get('Authorization')))
                if self.headers.get('Authorization') == f'Bearer {TOKEN}':
                    return True
                self.send_response(401)
                self.end_headers()
                return False

            def respond(self, status, body=b''):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not self.authorized():
                    return
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                if parsed.path == '/api/auth/me':
                    result = {'id': OWNER, 'username': 'synthetic'}
                elif parsed.path in ('/api/exercises', '/api/exercises/defaults', '/api/plans'):
                    items = {
                        '/api/exercises': [{'id': PERSONAL, 'name': 'Личное упражнение', 'isDeleted': False}],
                        '/api/exercises/defaults': [{'globalId': DEFAULT, 'name': 'Базовое упражнение'}],
                        '/api/plans': fixture.plans,
                    }[parsed.path]
                    offset, limit = int(query.get('offset', [0])[0]), int(query.get('limit', [100])[0])
                    result = {'items': items[offset:offset + limit], 'total': len(items)}
                elif parsed.path == '/api/health/apple/daily':
                    assert query == {'from': ['2026-10-20'], 'to': ['2026-10-20']}
                    result = HEALTH
                elif parsed.path == '/api/health/apple/metrics':
                    result = METRICS
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if not self.authorized():
                    return
                assert self.headers.get_content_type() == 'application/json'
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/plans':
                    fixture.posts.append(deepcopy(body))
                    # Даже ответ 500 может прийти после сохранения: клиент не должен повторять POST.
                    fixture.plans.append(deepcopy(body))
                    status = fixture.next_post_status
                    fixture.next_post_status = 200
                    self.respond(status)
                    return
                parts = self.path.split('/')
                assert len(parts) == 5 and parts[1:3] == ['api', 'plans'] and parts[4] == 'days'
                plan = next(p for p in fixture.plans if p['id'] == parts[3])
                fixture.append_posts.append(deepcopy(body))
                # Проверяется прямо при получении POST: резервная копия уже существует
                # и содержит исходное дерево и ровно отправляемое добавление.
                backups = list(fixture.backup_dir.glob(f"plan-{plan['id']}-*.json"))
                matching = [p for p in backups if json.loads(p.read_text()) == {
                    'before': plan, 'addition': body}]
                assert len(matching) == 1
                assert matching[0].stat().st_mode & 0o777 == 0o600
                assert fixture.backup_dir.stat().st_mode & 0o777 == 0o700
                fixture.backups_verified.append(matching[0])
                status = fixture.next_append_status
                fixture.next_append_status = 200
                expected = datetime.fromisoformat(body['expectedUpdatedAt'].replace('Z', '+00:00'))
                actual = datetime.fromisoformat(plan['updatedAt'].replace('Z', '+00:00'))
                if status == 409 or expected != actual:
                    self.respond(409)
                    return
                prior_ids = {node['id'] for node in plan['templates'] + plan['exercises']}
                assert not prior_ids.intersection(node['id'] for node in body['templates'] + body['exercises'])
                # Синтетический контракт append: прежние узлы не переписываются.
                # Сервер определяет порядок новых дней и время изменения корня.
                start = max((day['sortOrder'] for day in plan['templates']), default=-1) + 1
                for index, template in enumerate(body['templates']):
                    day = deepcopy(template)
                    day['sortOrder'] = start + index
                    plan['templates'].append(day)
                plan['exercises'].extend(deepcopy(body['exercises']))
                plan['updatedAt'] = (actual + timedelta(seconds=1)).isoformat()
                plan['revision'] += 1
                malformed = fixture.next_append_malformed
                fixture.next_append_malformed = False
                response = b'{not-json' if malformed else json.dumps(plan, ensure_ascii=False).encode()
                self.respond(status, response)

        return Handler


def unpack(result):
    assert not result.isError, result
    value = result.structuredContent
    if value is None:
        value = json.loads(result.content[0].text)
    return value['result'] if isinstance(value, dict) and set(value) == {'result'} else value


@asynccontextmanager
async def connection(server_path, port, error_log):
    # Не наследуем реальные токены процесса; env-файл копии — пустой временный.
    parameters = StdioServerParameters(
        command=sys.executable, args=[str(server_path)],
        env={'PATH': os.defpath, 'GYM_API_TOKEN': TOKEN,
             'GYM_API_URL': f'http://127.0.0.1:{port}/api', 'PYTHONUNBUFFERED': '1',
             'GYM_MCP_ENV_FILE': str(server_path.with_name('fixture.env')),
             'GYM_PLAN_BACKUP_DIR': str(server_path.parent / 'backups')},
    )
    async with stdio_client(parameters, errlog=error_log) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def assert_payload(plan, request, returned_id):
    assert plan['id'] == returned_id
    UUID(returned_id)
    assert plan['authorUserId'] == OWNER
    assert plan['name'] == request['name']
    assert plan['description'] == request['description']
    assert plan['isPublished'] is False and plan['isDeleted'] is False
    assert plan['revision'] == 1
    assert plan['restDefaults'] == {'0': 150, '1': 45}
    assert len(plan['exercises']) == 2  # Повтор личного упражнения не создаёт второй элемент пула.
    pool = {entry['id']: entry for entry in plan['exercises']}
    all_nodes = [plan, *plan['exercises']]
    assert len(plan['templates']) == len(request['days'])
    for day_index, (template, day) in enumerate(zip(plan['templates'], request['days'])):
        all_nodes.append(template)
        assert template['planId'] == plan['id'] and template['sortOrder'] == day_index
        assert template['title'] == day['title'] and template['description'] == day['description']
        assert len(template['exercises']) == len(day['exercises'])
        for exercise_index, (nested, exercise) in enumerate(zip(template['exercises'], day['exercises'])):
            all_nodes.append(nested)
            assert nested['planTemplateId'] == template['id'] and nested['sortOrder'] == exercise_index
            assert nested['comment'] == exercise['comment']
            entry = pool[nested['planExerciseId']]
            assert entry['planId'] == plan['id']
            assert nested['userExerciseId'] == entry['userExerciseId'] == exercise.get('user_exercise_id')
            assert nested['defaultExerciseGlobalId'] == entry['defaultExerciseGlobalId'] == exercise.get('default_exercise_id')
            assert nested['displayName'] == entry['displayName'] == (
                'Личное упражнение' if exercise.get('user_exercise_id') else 'Базовое упражнение')
            assert len(nested['sets']) == len(exercise['sets'])
            for number, (actual, expected) in enumerate(zip(nested['sets'], exercise['sets']), 1):
                all_nodes.append(actual)
                assert actual['planTemplateExerciseId'] == nested['id'] and actual['number'] == number
                assert actual['reps'] == expected['reps']
                assert actual['targetWeight'] == expected.get('weight')
                assert actual['targetWeightPercent'] == expected.get('weight_percent')
                assert actual['weightUnit'] == expected.get('unit', 'kg')
                assert actual['targetRpe'] == expected.get('rpe')
                assert actual['setType'] == (1 if expected.get('warmup') else 0)
                assert actual['restSecondsOverride'] == expected.get('rest_seconds')
    ids = [node['id'] for node in all_nodes]
    assert len(ids) == len(set(ids))
    for node in all_nodes:
        UUID(node['id'])
        assert node['createdById'] == OWNER
        assert node['createdAt'] == node['updatedAt'] == plan['createdAt']
        assert datetime.fromisoformat(node['createdAt']).utcoffset().total_seconds() == 0


async def verify(server_path, port, fixture, error_log):
    async with connection(server_path, port, error_log) as session:
        listed = {tool.name: tool.model_dump() for tool in (await session.list_tools()).tools}
        assert set(listed) == EXISTING | ADDED
        for name in ('gym_plans', 'gym_plan', 'gym_exercises', 'gym_health_daily', 'gym_health_metrics'):
            assert listed[name]['annotations']['readOnlyHint'] is True
        health_before = unpack(await session.call_tool('gym_health_daily', {
            'from_date': '2026-10-20', 'to_date': '2026-10-20'}))
        metrics_before = unpack(await session.call_tool('gym_health_metrics'))
        assert health_before == HEALTH and metrics_before == METRICS
        assert listed['gym_create_plan']['annotations']['readOnlyHint'] is False
        assert listed['gym_create_plan']['annotations']['idempotentHint'] is False
        assert listed['gym_append_plan_days']['annotations']['readOnlyHint'] is False
        assert listed['gym_append_plan_days']['annotations']['idempotentHint'] is False
        assert listed['gym_append_plan_days']['annotations']['destructiveHint'] is False
        schema = listed['gym_create_plan']['inputSchema']
        assert {'PlanDay', 'PlanExercise', 'PlanSet'} <= set(schema['$defs'])
        assert schema['$defs']['PlanExercise']['additionalProperties'] is False
        assert unpack(await session.call_tool('gym_exercises'))['items'][0]['id'] == PERSONAL
        assert unpack(await session.call_tool('gym_exercises', {'source': 'default'}))['items'][0]['globalId'] == DEFAULT
        assert unpack(await session.call_tool('gym_plans'))['items'] == []

        request = {
            'name': 'Синтетический план', 'description': 'Только изолированная проверка',
            'work_rest_seconds': 150, 'warmup_rest_seconds': 45,
            'days': [
                {'title': 'День А', 'description': 'Первый день', 'exercises': [
                    {'user_exercise_id': PERSONAL, 'comment': 'Личный вариант', 'sets': [
                        {'reps': 12, 'weight': 20, 'warmup': True, 'rest_seconds': 45, 'rpe': 5},
                        {'reps': 8, 'weight': 60, 'rest_seconds': 120, 'rpe': 8},
                    ]},
                    {'default_exercise_id': DEFAULT, 'comment': 'Общий каталог', 'sets': [
                        {'reps': 10, 'weight': 30, 'unit': 'lb', 'rest_seconds': 0},
                        {'reps': 6, 'weight_percent': 75, 'rpe': 8.5},
                    ]},
                ]},
                {'title': 'День Б', 'description': '', 'exercises': [
                    {'user_exercise_id': PERSONAL, 'comment': 'Повтор упражнения', 'sets': [
                        {'reps': 15, 'weight': 0}, {'reps': 12},
                    ]},
                ]},
            ],
        }
        created = unpack(await session.call_tool('gym_create_plan', request))
        assert created['status'] == 'created' and created['days'] == 2 and created['sets'] == 6
        assert len(fixture.posts) == 1
        assert_payload(fixture.posts[0], request, created['plan_id'])
        loaded = unpack(await session.call_tool('gym_plan', {'plan_id': created['plan_id']}))
        assert loaded == fixture.posts[0]

        # Некорректный ввод не должен дойти до записи даже через MCP-обвязку.
        cases = []
        for field, value in [('name', '   '), ('days', []), ('work_rest_seconds', -1)]:
            bad = deepcopy(request)
            bad[field] = value
            cases.append(bad)
        for field, value in [
            ('reps', 0), ('weight', -1), ('unit', 'stone'), ('rpe', 11),
            ('rest_seconds', -1), ('weight_percent', 80), ('unknown_field', True),
        ]:
            bad = deepcopy(request)
            bad['days'][0]['exercises'][0]['sets'][0][field] = value
            cases.append(bad)
        for value in ['invalid-uuid', '44444444-4444-4444-8444-444444444444']:
            bad = deepcopy(request)
            bad['days'][0]['exercises'][0]['user_exercise_id'] = value
            cases.append(bad)
        bad = deepcopy(request)
        bad['days'][0]['exercises'][0]['default_exercise_id'] = DEFAULT
        cases.append(bad)
        for bad in cases:
            rejected = await session.call_tool('gym_create_plan', bad)
            assert rejected.isError
            assert len(fixture.posts) == 1

        fixture.next_post_status = 500
        unknown = unpack(await session.call_tool('gym_create_plan', request))
        assert unknown['status'] == 'unknown'
        assert unknown['plan_id'] != created['plan_id']
        assert len(fixture.posts) == 2
        assert unpack(await session.call_tool('gym_plan', {'plan_id': unknown['plan_id']})) == fixture.posts[1]
        assert len(fixture.posts) == 2

        original = unpack(await session.call_tool('gym_plan', {'plan_id': created['plan_id']}))
        append_request = {
            'plan_id': created['plan_id'], 'expected_updated_at': original['updatedAt'],
            'days': [dict(deepcopy(request['days'][0]), title=f'Новый день {index}')
                     for index in range(1, 8)],
        }
        appended = unpack(await session.call_tool('gym_append_plan_days', append_request))
        assert appended['status'] == 'appended'
        assert appended['added_days'] == 7 and appended['total_days'] == 9
        assert len(fixture.posts) == 2 and len(fixture.append_posts) == 1
        addition = fixture.append_posts[0]
        assert len(addition['templates']) == 7 and addition['exercises'] == []
        saved = unpack(await session.call_tool('gym_plan', {'plan_id': created['plan_id']}))
        assert saved['templates'][:2] == original['templates']
        assert saved['exercises'] == original['exercises']
        assert {k: v for k, v in saved.items() if k not in {'templates', 'updatedAt', 'revision'}} == {
            k: v for k, v in original.items() if k not in {'templates', 'updatedAt', 'revision'}}
        assert [day['sortOrder'] for day in saved['templates']] == list(range(9))
        assert appended['added_day_ids'] == [day['id'] for day in saved['templates'][2:]]
        pool_ids = {exercise['id'] for exercise in original['exercises']}
        for index, template in enumerate(saved['templates'][2:]):
            assert template['title'] == append_request['days'][index]['title']
            assert {exercise['planExerciseId'] for exercise in template['exercises']} == pool_ids
            for exercise, before in zip(template['exercises'], original['templates'][0]['exercises']):
                assert exercise['comment'] == before['comment']
                for actual, expected in zip(exercise['sets'], before['sets']):
                    for field in ('number', 'reps', 'targetWeight', 'targetWeightPercent',
                                  'weightUnit', 'targetRpe', 'setType', 'restSecondsOverride'):
                        assert actual[field] == expected[field]
        assert len(fixture.backups_verified) == 1

        # Старый expectedUpdatedAt отклоняется уже до POST, без повторного добавления.
        rejected = await session.call_tool('gym_append_plan_days', append_request)
        assert rejected.isError and len(fixture.append_posts) == 1
        assert unpack(await session.call_tool('gym_plan', {'plan_id': created['plan_id']})) == saved

        # Конфликт между предварительным GET и записью также не повторяет запрос.
        next_request = deepcopy(append_request)
        next_request['days'] = next_request['days'][:1]
        next_request['expected_updated_at'] = saved['updatedAt']
        fixture.next_append_status = 409
        rejected = await session.call_tool('gym_append_plan_days', next_request)
        assert rejected.isError and len(fixture.append_posts) == 2
        assert unpack(await session.call_tool('gym_plan', {'plan_id': created['plan_id']})) == saved

        # Повреждённый ответ и 500 могут прийти после сохранения. Статус unknown
        # содержит ID новых дней, чтобы их проверить; автоматического POST-повтора нет.
        for failure in ('malformed', 'server-error'):
            next_request['expected_updated_at'] = saved['updatedAt']
            fixture.next_append_malformed = failure == 'malformed'
            fixture.next_append_status = 500 if failure == 'server-error' else 200
            count = len(fixture.append_posts)
            uncertain = unpack(await session.call_tool('gym_append_plan_days', next_request))
            assert uncertain['status'] == 'unknown'
            assert len(fixture.append_posts) == count + 1
            checked = unpack(await session.call_tool('gym_plan', {'plan_id': created['plan_id']}))
            assert checked['templates'][:-1] == saved['templates']
            assert checked['exercises'] == saved['exercises']
            assert uncertain['added_day_ids'] == [checked['templates'][-1]['id']]
            assert len(fixture.append_posts) == count + 1
            saved = checked
        assert len(fixture.backups_verified) == len(fixture.append_posts) == 4

        for field, value in [('days', []), ('expected_updated_at', '2026-10-21T12:00:00')]:
            bad = deepcopy(next_request)
            bad[field] = value
            rejected = await session.call_tool('gym_append_plan_days', bad)
            assert rejected.isError and len(fixture.append_posts) == 4

        assert unpack(await session.call_tool('gym_health_daily', {
            'from_date': '2026-10-20', 'to_date': '2026-10-20'})) == health_before
        assert unpack(await session.call_tool('gym_health_metrics')) == metrics_before
        before = len(fixture.requests)
        rejected = await session.call_tool('gym_health_daily', {
            'from_date': '2026-09-01', 'to_date': '2026-10-20'})
        assert rejected.isError and len(fixture.requests) == before
        assert all(auth == f'Bearer {TOKEN}' for _, _, auth in fixture.requests)
        assert all(method in ('GET', 'POST') and path.startswith('/api/')
                   for method, path, _ in fixture.requests)
        return {'result': 'PASS', 'transport': 'real stdio', 'api': 'loopback synthetic',
                'tools': len(listed), 'plan_tools': len(ADDED),
                'created_days': 2, 'created_sets': 6, 'invalid_requests_blocked': len(cases),
                'http_200_empty_accepted': True, 'http_500_no_retry': True,
                'appended_days': 7, 'old_plan_tree_preserved': True, 'exercise_pool_reused': True,
                'backup_before_every_append': True, 'append_backups_verified': len(fixture.backups_verified),
                'stale_append_blocked_before_post': True, 'append_409_no_retry': True,
                'append_malformed_and_500_no_retry': True,
                'health_unchanged': True, 'production_requests': 0}


def main():
    fixture = Fixture()
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.handler())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='gym-plans-stdio-') as directory:
            temporary = Path(directory)
            fixture.backup_dir = temporary / 'backups'
            source = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else SOURCE
            for name in MODULES:
                shutil.copyfile(source / name, temporary / name)
            (temporary / 'fixture.env').write_text('')
            server_path = temporary / 'server.py'
            with (temporary / 'stderr.log').open('w+') as error_log:
                result = asyncio.run(asyncio.wait_for(
                    verify(server_path, server.server_port, fixture, error_log), timeout=60))
            print(json.dumps(result, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
