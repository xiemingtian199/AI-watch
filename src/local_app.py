import argparse
import hashlib
import json
import mimetypes
import os
import re
import threading
import uuid
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from workbench import Workbench

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / 'app'
PRIVATE_DIR = Path(os.environ.get('AI_WATCH_DATA_DIR', ROOT / 'data' / 'private'))


class LocalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        super().end_headers()

    def send_json(self, payload, status=200, filename=None):
        body = json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def valid_origin(self):
        host = self.headers.get('Host','')
        expected = {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return host in expected and (not origin or origin in {f'http://{h}' for h in expected})

    def do_GET(self):
        if not self.valid_origin():
            return self.send_json({'error':'请求来源不受支持'},403)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            dataset = self.server.store.dataset(query.get('dataset',['personal'])[0])
            if parsed.path == '/api/overview':
                return self.send_json(self.server.store.overview(dataset))
            if parsed.path in {'/api/day','/api/export'}:
                report = self.server.store.daily(dataset,query.get('date',[''])[0])
                filename = f'ai-watch-{dataset}-{report["date"]}.json' if parsed.path == '/api/export' else None
                return self.send_json(report, filename=filename)
            if parsed.path == '/api/imports':
                return self.send_json({'imports':self.server.store.imports()})
            if parsed.path == '/api/status':
                return self.send_json({'ok':True,'mode':'local'})
            if parsed.path.startswith('/api/media/'):
                return self.send_media(self.server.store.media(parsed.path.rsplit('/',1)[1]))
            if parsed.path == '/api/template':
                text = 'timestamp,end_timestamp,source,modality,value,unit,activity,summary\n2026-09-12T09:00:00+08:00,,apple_watch,heart_rate,72,count/min,,\n2026-09-12T14:00:00+08:00,2026-09-12T15:00:00+08:00,manual_context,focus_session,,,deep_work,整理项目方案\n'
                data = ('\ufeff'+text).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/csv; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="ai-watch-template.csv"')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            relative = unquote(parsed.path).lstrip('/') or 'index.html'
            target = (APP_DIR/relative).resolve()
            if not target.is_relative_to(APP_DIR.resolve()) or not target.is_file():
                return self.send_error(404)
            return super().do_GET()
        except (ValueError,KeyError,FileNotFoundError) as exc:
            return self.send_json({'error':str(exc)},400)

    def send_media(self,path):
        size = path.stat().st_size
        start,end,status = 0,size-1,200
        requested = self.headers.get('Range','')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
            if not match or not any(match.groups()):
                return self.send_error(416)
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]),size-1) if match[2] else size-1
            else:
                start = max(0,size-int(match[2]))
            if start>end or start>=size:
                return self.send_error(416)
            status = 206
        self.send_response(status)
        self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        if status==206:
            self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as stream:
            stream.seek(start)
            remaining = end-start+1
            while remaining:
                data = stream.read(min(65536,remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)

    def read_payload(self):
        length = int(self.headers.get('Content-Length','0'))
        if not 0 < length <= 2_000_000:
            raise ValueError('请求大小无效')
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def upload(self):
        name = Path(unquote(self.headers.get('X-Filename',''))).name
        if not name or len(name)>250:
            raise ValueError('文件名无效')
        suffix = Path(name).suffix.lower()
        length = int(self.headers.get('Content-Length','0'))
        limit = 1024*1024*1024 if suffix not in {'.json','.jsonl','.csv'} else 64*1024*1024
        if not 0 < length <= limit:
            raise ValueError(f'文件为空或超过 {limit//1024//1024} MB 限制')
        folder = self.server.store.directory/'uploads'
        folder.mkdir(exist_ok=True)
        path = folder/(uuid.uuid4().hex+suffix)
        digest = hashlib.sha256()
        remaining = length
        try:
            with path.open('wb') as output:
                while remaining:
                    part = self.rfile.read(min(1024*1024,remaining))
                    if not part:
                        raise ValueError('文件传输中断，请重试')
                    digest.update(part)
                    output.write(part)
                    remaining-=len(part)
            result = self.server.store.import_file(path,name,digest.hexdigest(),
                unquote(self.headers.get('X-Start','')) or None,
                unquote(self.headers.get('X-Summary','')))
            if result['duplicate']:
                path.unlink(missing_ok=True)
            return result
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def do_POST(self):
        if not self.valid_origin():
            return self.send_json({'error':'请求来源不受支持'},403)
        try:
            route = urlparse(self.path).path
            if route == '/api/upload':
                return self.send_json(self.upload())
            payload = self.read_payload()
            dataset = self.server.store.dataset(payload.get('dataset','personal'))
            if route == '/api/profile':
                return self.send_json(self.server.store.save_profile(dataset,payload))
            if route == '/api/note':
                return self.send_json(self.server.store.note(dataset,payload))
            if route == '/api/checkin':
                self.server.store.checkin(dataset,payload)
                return self.send_json({'ok':True})
            if route == '/api/feedback':
                self.server.store.set_feedback(dataset,payload)
                return self.send_json({'ok':True})
            return self.send_json({'error':'接口不存在'},404)
        except Exception as exc:
            self.send_json({'error':str(exc)},400)


def create_server(port=4180,directory=None):
    server = ThreadingHTTPServer(('127.0.0.1',port),LocalHandler)
    server.store = Workbench(directory or PRIVATE_DIR)
    return server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=4180)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    server=create_server(args.port)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'AI Watch 工作台: {url}',flush=True)
    if not args.no_browser:
        threading.Timer(0.8,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
