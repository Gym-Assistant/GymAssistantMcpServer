"""Проверка локального MCP через настоящий stdio: тренировки, рекорды и Apple Health.

Запуск окружением с зависимостями из requirements.txt:
  python integrations/local-gymassistant/verify_stdio.py               # server.py из репозитория
  python integrations/local-gymassistant/verify_stdio.py /путь/к/run.sh  # установленный сервер
API — синтетический loopback, токен — тестовый, env-файл — пустой временный
(GYM_MCP_ENV_FILE). Реальные токены процесса не наследуются, production не вызывается.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


TOKEN = 'gma_synthetic_fixture_only'
OWNER = '11111111-1111-4111-8111-111111111111'
BENCH = '22222222-2222-4222-8222-222222222222'
EXPECTED_TOOLS = {
    'gym_me', 'gym_workouts', 'gym_workout', 'gym_records', 'gym_body_latest',
    'gym_body_history', 'gym_status', 'gym_health_daily', 'gym_health_metrics',
    'gym_plans', 'gym_plan', 'gym_exercises', 'gym_create_plan', 'gym_append_plan_days',
}
HEALTH = [{'snapshot': {'day': '2026-10-17', 'timeZone': 'Asia/Krasnoyarsk', 'readAt': '2026-10-17T12:00:00Z',
                        'values': {'steps': 1234, 'protein': None}},
           'receivedAt': '2026-10-17T12:01:00Z', 'deviceId': '33333333-3333-4333-8333-333333333333'}]
METRICS = {'metrics': [{'key': 'steps', 'unit': 'count', 'aggregation': 'sum'}]}


def synthetic_workouts():
    """120 свежих тренировок и одна старая: её не было среди последних 50."""
    def build(index, started, sets):
        return {'id': f'00000000-0000-4000-8000-{index:012d}', 'startedAt': started, 'isDeleted': False,
                'createdAt': '2026-01-01T00:00:00Z',
                'trainSessions': [{'exerciseId': BENCH, 'sets': sets}]}
    work = [{'number': 1, 'weight': 60, 'reps': 5, 'isDone': True, 'isWarmup': False,
             'createdAt': '2026-10-01T00:00:00Z'}]
    items = [build(i, f'2026-09-{1 + i % 28:02d}T05:00:00Z', work) for i in range(120)]
    # 20:30 UTC 10 марта — это уже 11 марта в Красноярске (UTC+7).
    items.append(build(999, '2026-03-10T20:30:00Z', [
        {'number': 1, 'weight': 150, 'reps': 2, 'isDone': True, 'isWarmup': True,
         'createdAt': '2026-03-12T00:00:00Z'},
        {'number': 2, 'weight': 100, 'reps': 5, 'isDone': True, 'isWarmup': False,
         'createdAt': '2026-03-12T00:00:00Z'},
    ]))
    return items


class Fixture:
    def __init__(self):
        self.requests = []
        self.workouts = synthetic_workouts()

    def handler(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                fixture.requests.append((self.command, self.path, self.headers.get('Authorization')))
                if self.headers.get('Authorization') != f'Bearer {TOKEN}':
                    self.send_response(401)
                    self.end_headers()
                    return
                parsed = urlsplit(self.path)
                query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                if parsed.path == '/api/auth/me':
                    result = {'id': OWNER, 'username': 'synthetic'}
                elif parsed.path == '/api/user/settings':
                    result = {'timeZoneId': 'Asia/Krasnoyarsk', 'language': 'ru'}
                elif parsed.path == '/api/workouts':
                    offset, limit = int(query['offset']), int(query['limit'])
                    result = {'items': fixture.workouts[offset:offset + limit], 'total': len(fixture.workouts)}
                elif parsed.path == '/api/exercises':
                    result = {'items': [{'id': BENCH, 'name': 'Жим лёжа'}], 'total': 1}
                elif parsed.path == '/api/health/apple/daily':
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

        return Handler


def unpack(result):
    assert not result.isError, result
    value = result.structuredContent
    if value is None:
        value = json.loads(result.content[0].text)
    return value['result'] if isinstance(value, dict) and set(value) == {'result'} else value


def server_command():
    if len(sys.argv) > 1:
        return str(Path(sys.argv[1]).expanduser().resolve()), []
    return sys.executable, [str(Path(__file__).resolve().with_name('server.py'))]


async def verify(port, fixture, temporary):
    command, args = server_command()
    env_file = temporary / 'fixture.env'
    env_file.write_text('')
    parameters = StdioServerParameters(command=command, args=args, env={
        'PATH': os.defpath, 'PYTHONUNBUFFERED': '1', 'GYM_API_TOKEN': TOKEN,
        'GYM_API_URL': f'http://127.0.0.1:{port}/api', 'GYM_MCP_ENV_FILE': str(env_file),
        'GYM_PLAN_BACKUP_DIR': str(temporary / 'backups'), 'XDG_CONFIG_HOME': str(temporary / 'config'),
    })
    with (temporary / 'stderr.log').open('w+') as error_log:
        async with stdio_client(parameters, errlog=error_log) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert names == EXPECTED_TOOLS, sorted(names ^ EXPECTED_TOOLS)

                daily = unpack(await session.call_tool('gym_health_daily', {
                    'from_date': '2026-10-17', 'to_date': '2026-10-17'}))
                assert daily == HEALTH and daily[0]['snapshot']['values']['protein'] is None
                assert unpack(await session.call_tool('gym_health_metrics')) == METRICS
                before = len(fixture.requests)
                bad = await session.call_tool('gym_health_daily', {'from_date': '2026-09-01', 'to_date': '2026-10-17'})
                assert bad.isError and len(fixture.requests) == before

                found = unpack(await session.call_tool('gym_workout', {'workout_date': '2026-03-11'}))
                assert found['id'] == fixture.workouts[-1]['id'] and found['date'] == '2026-03-11'
                missing = unpack(await session.call_tool('gym_workout', {'workout_date': '2026-03-10'}))
                assert 'error' in missing and 'Asia/Krasnoyarsk' in missing['error']
                pages = [path for _, path, _ in fixture.requests if path.startswith('/api/workouts?')]
                assert pages[:2] == ['/api/workouts?offset=0&limit=100', '/api/workouts?offset=100&limit=100']

                records = unpack(await session.call_tool('gym_records'))
                bench = next(r for r in records if r['exercise'] == 'Жим лёжа')
                # Подход 150 кг отмечен разминкой; рекорд — рабочие 100 x 5 по Эпли.
                assert (bench['weight'], bench['reps'], bench['rm'], bench['date']) == (100, 5, 116.7, '2026-03-11')

    assert all(auth == f'Bearer {TOKEN}' for _, _, auth in fixture.requests)
    assert all(method == 'GET' and path.startswith('/api/') for method, path, _ in fixture.requests)
    return {'result': 'PASS', 'transport': 'real stdio', 'api': 'loopback synthetic', 'tools': len(names),
            'health_null_preserved': True, 'bad_dates_blocked': True, 'workout_local_date': True,
            'workout_beyond_last_50': True, 'records_use_warmup_flag': True, 'production_requests': 0}


def main():
    fixture = Fixture()
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.handler())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='gym-core-stdio-') as directory:
            result = asyncio.run(asyncio.wait_for(
                verify(server.server_port, fixture, Path(directory)), timeout=60))
        print(json.dumps(result, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
