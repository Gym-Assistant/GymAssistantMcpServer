"""Проверка настоящего stdio MCP на синтетическом backend; production не используется."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
from threading import Thread

TOKEN = 'gma_' + 'a' * 40
requests = []
posts = []
PLAN_ID = '11111111-1111-1111-1111-111111111111'
MEASUREMENT = {'trackingType':'interval','rounds':5,'workSeconds':30,'recoverySeconds':60}
PLAN = {'id':PLAN_ID,'updatedAt':'2026-10-22T09:00:00Z','templates':[
    {'title':'Интервалы','exercises':[{'sets':[{'number':1,'measurement':MEASUREMENT},
                                             {'number':2,'reps':10,'targetWeight':80}]}]}]}

class Backend(BaseHTTPRequestHandler):
    def respond(self, status, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b''
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        requests.append((self.path, self.headers.get('Authorization')))
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            self.respond(401); return
        if self.path == '/api/auth/me':
            payload = {'id':PLAN_ID,'username':'runtime-fixture'}
        elif self.path == '/api/health/apple/daily?from=2026-10-16&to=2026-10-17':
            payload = [{'snapshot': {'day':'2026-10-17','timeZone':'Asia/Krasnoyarsk','readAt':'2026-10-17T12:00:00Z','values':{'steps':1234,'protein':None}},'deviceId':PLAN_ID,'receivedAt':'2026-10-17T12:01:00Z'}]
        elif self.path == f'/api/plans/{PLAN_ID}':
            payload = PLAN
        else:
            self.respond(404); return
        self.respond(200, payload)
    def do_POST(self):
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            self.respond(401); return
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        posts.append((self.path, payload))
        if self.path == '/api/plans':
            self.respond(200)
        elif self.path == f'/api/plans/{PLAN_ID}/days':
            self.respond(200, PLAN)
        else:
            self.respond(404)
    def log_message(self,*args): pass

async def verify(command, url):
    env = {**os.environ, 'GYM_API_TOKEN':TOKEN,'GYM_API_URL':url,'GYM_LOG_LEVEL':'Warning'}
    process = await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,
              stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
    stderr = asyncio.create_task(process.stderr.read())
    async def send(value):
        process.stdin.write((json.dumps(value)+'\n').encode()); await process.stdin.drain()
    async def call(number,method,params):
        await send({'jsonrpc':'2.0','id':number,'method':method,'params':params})
        while True:
            line = await asyncio.wait_for(process.stdout.readline(),30)
            assert line, 'MCP process ended before response'
            message = json.loads(line)
            assert message.get('jsonrpc')=='2.0', 'Invalid MCP stdout'
            if message.get('id')==number:
                assert 'error' not in message, 'JSON-RPC error'
                return message['result']
    try:
        initialized = await call(1,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},
                  'clientInfo':{'name':'gymassistant-runtime-check','version':'1.0'}})
        assert initialized['protocolVersion']=='2025-03-26'
        await send({'jsonrpc':'2.0','method':'notifications/initialized'})
        listed = await call(2,'tools/list',{})
        names = {t['name'] for t in listed['tools']}
        root = Path(__file__).resolve().parents[1]
        expected = set()
        for source in (root/'src/GymAssistant.McpServer/Tools').glob('*.cs'):
            expected.update(re.findall(r'McpServerTool\(Name\s*=\s*"([^"]+)"',source.read_text()))
        assert names==expected, 'Runtime tools differ from declared tools'
        health = await call(3,'tools/call',{'name':'health_check','arguments':{}})
        assert not health.get('isError',False), 'health_check failed; fixture paths: '+str([p for p,_ in requests])
        content = [x['text'] for x in health['content'] if x['type']=='text']
        payload = next(json.loads(x) for x in content if x.startswith('{'))
        assert payload['ok'] is True and payload['user']=='runtime-fixture', 'Wrong health result'
        assert requests==[('/api/auth/me','Bearer '+TOKEN)], 'Unexpected backend traffic'
        daily = await call(4,'tools/call',{'name':'get_apple_health_daily','arguments':{'from':'2026-10-16','to':'2026-10-17'}})
        assert not daily.get('isError',False), 'Health call failed'
        daily_text = ' '.join(x['text'] for x in daily['content'] if x['type']=='text')
        assert '1234' in daily_text and 'Asia/Krasnoyarsk' in daily_text and '2026-10-17' in daily_text
        assert requests[-1]==('/api/health/apple/daily?from=2026-10-16&to=2026-10-17','Bearer '+TOKEN)
        schemas = {t['name']: t['inputSchema'] for t in listed['tools']}
        for name in ('create_plan', 'append_plan_days', 'create_workout', 'update_set'):
            schema = json.dumps(schemas[name]).lower()
            assert 'measurement' in schema and 'trackingtype' in schema, name + ' lacks typed measurement'
        created = await call(5,'tools/call',{'name':'create_plan','arguments':{'body':PLAN}})
        assert not created.get('isError',False), 'Typed plan creation failed'
        assert posts[-1][0] == '/api/plans'
        sets = posts[-1][1]['templates'][0]['exercises'][0]['sets']
        assert sets[0]['measurement'] == MEASUREMENT
        assert sets[1]['reps'] == 10 and sets[1]['targetWeight'] == 80
        assert 'measurement' not in sets[1]
        addition = {'expectedUpdatedAt':PLAN['updatedAt'],'templates':PLAN['templates']}
        appended = await call(6,'tools/call',{'name':'append_plan_days','arguments':{'id':PLAN_ID,'body':addition}})
        assert not appended.get('isError',False), 'Typed append failed'
        assert posts[-1][0] == f'/api/plans/{PLAN_ID}/days'
        assert len(posts[-1][1]['templates']) == 1
        assert posts[-1][1]['templates'][0]['exercises'][0]['sets'][0]['measurement'] == MEASUREMENT
        assert 'expectedUpdatedAt' in posts[-1][1]
        read = await call(7,'tools/call',{'name':'get_plan','arguments':{'id':PLAN_ID}})
        assert not read.get('isError',False)
        read_text = json.dumps(read).lower()
        assert all(field in read_text for field in ('trackingtype','interval','workseconds','recoveryseconds','targetweight'))
        assert len(posts)==2, 'Unexpected write or retry'
        await call(8,'ping',{})
        print(json.dumps({'initialize':True,'tools':len(names),'health_check':True,
                          'health_daily':True,'typed_create_append_read':True,'legacy_sets_preserved':True,'profile_pat_forwarded':True,'stdout_jsonrpc':True,'backend':'synthetic'}))
    finally:
        process.stdin.close()
        try: await asyncio.wait_for(process.wait(),10)
        except TimeoutError:
            process.terminate(); await process.wait()
        await stderr

if __name__=='__main__':
    command = sys.argv[1:]
    assert command, 'Pass the executable command after this script'
    docker = command[0]=='docker'
    backend = ThreadingHTTPServer(('0.0.0.0' if docker else '127.0.0.1',0),Backend)
    Thread(target=backend.serve_forever,daemon=True).start()
    host='host.docker.internal' if docker else '127.0.0.1'
    url=f'http://{host}:{backend.server_port}/api'
    if docker:
        command = ['docker','run','--rm','-i','--add-host','host.docker.internal:host-gateway',
                    '-e','GYM_API_TOKEN','-e','GYM_API_URL','-e','GYM_LOG_LEVEL',*command[1:]]
    try: asyncio.run(verify(command,url))
    finally: backend.shutdown(); backend.server_close()
