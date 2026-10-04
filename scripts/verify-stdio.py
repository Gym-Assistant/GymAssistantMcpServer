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

class Backend(BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append((self.path, self.headers.get('Authorization')))
        if self.path != '/api/auth/me' or self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            self.send_response(404); self.end_headers(); return
        body = json.dumps({'id':'11111111-1111-1111-1111-111111111111','username':'runtime-fixture'}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
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
        await call(4,'ping',{})
        print(json.dumps({'initialize':True,'tools':len(names),'health_check':True,
                          'profile_pat_forwarded':True,'stdout_jsonrpc':True,'backend':'synthetic'}))
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
