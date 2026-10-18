"""Small stdlib-only client for the V2 loopback session broker."""
from __future__ import annotations
import argparse, http.client, json, re, sys

HANDLE_RE=re.compile(r"[A-Za-z0-9_-]{32,256}")
def call(port, handle, request, timeout=95):
    if not HANDLE_RE.fullmatch(handle): raise ValueError("invalid session handle")
    if not isinstance(request,dict): raise ValueError("request must be a JSON object")
    body=json.dumps(request,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=timeout)
    try:
        connection.request("POST","/tool",body=body,headers={"Content-Type":"application/json; charset=utf-8","X-Bench-Session":handle})
        response=connection.getresponse(); response_body=response.read()
        sys.stdout.buffer.write(response_body); sys.stdout.buffer.flush()
        if response.status>=400: raise SystemExit(2)
        return response.status,response_body
    finally: connection.close()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--port",type=int,required=True); parser.add_argument("--handle",required=True); parser.add_argument("--request",required=True,help="JSON object for list/read/search")
    args=parser.parse_args()
    try: request=json.loads(args.request)
    except json.JSONDecodeError as exc: raise SystemExit(f"invalid --request JSON: {exc}")
    call(args.port,args.handle,request)
if __name__=="__main__": main()
