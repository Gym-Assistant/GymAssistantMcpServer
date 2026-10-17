import asyncio, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
seen=[]
class Fake(BaseHTTPRequestHandler):
 def do_GET(self):
  seen.append((self.path,self.headers.get('Authorization')))
  body=json.dumps([{'snapshot':{'day':'2026-10-17','timeZone':'Asia/Krasnoyarsk','readAt':'2026-10-17T12:00:00Z','values':{'steps':1234,'protein':None}},'receivedAt':'2026-10-17T12:01:00Z','deviceId':'11111111-1111-1111-1111-111111111111'}]).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
async def main(port):
 from mcp import ClientSession, StdioServerParameters
 from mcp.client.stdio import stdio_client
 env={**os.environ,'GYM_API_URL':f'http://127.0.0.1:{port}/api','GYM_API_TOKEN':'gma_fixture','GYM_HEALTH_API_TOKEN':''}
 async with stdio_client(StdioServerParameters(command=sys.argv[1],env=env)) as (r,w):
  async with ClientSession(r,w) as s:
   await s.initialize(); listed=await s.list_tools()
   names=[x.name for x in listed.tools]
   assert len(names)==8 and 'gym_health_daily' in names
   result=await s.call_tool('gym_health_daily',{'from_date':'2026-10-17','to_date':'2026-10-17'})
   assert not result.isError
   body=result.structuredContent or json.loads(result.content[0].text)
   if isinstance(body,dict) and 'result' in body:body=body['result']
   assert body[0]['snapshot']['values']['protein'] is None
   assert body[0]['snapshot']['values']['steps']==1234
   assert seen==[('/api/health/apple/daily?from=2026-10-17&to=2026-10-17','Bearer gma_fixture')]
   bad=await s.call_tool('gym_health_daily',{'from_date':'2026-09-01','to_date':'2026-10-17'})
   assert bad.isError and len(seen)==1
   print(json.dumps({'tools':len(names),'health_tool':True,'real_stdio':True,'owner_pat_forwarded':True,'null_preserved':True,'bad_dates_blocked':True,'backend':'synthetic'}))
srv=ThreadingHTTPServer(('127.0.0.1',0),Fake);Thread(target=srv.serve_forever,daemon=True).start()
try:asyncio.run(main(srv.server_port))
finally:srv.shutdown()
