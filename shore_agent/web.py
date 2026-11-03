"""Loopback-only research console. Run: python -m shore_agent.web --port 8765.

The browser gets a bounded application API, never filesystem or simulator access.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from shore_worlds import DEFAULT_WORLD_ID, public_worlds

PROJECT = Path(__file__).resolve().parents[1]
MAX_BODY = 64 * 1024
RUN_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/index.html': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/styles.css': ('styles.css', 'text/css; charset=utf-8')}


class WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_close(self):
        try:
            manager = getattr(self, 'manager', None)
            if manager is not None:
                manager.close()
        finally:
            super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'ShoreLocal/1.0'

    def log_message(self, *_args):
        # Never persist request bodies, credentials, arbitrary URLs or model text.
        pass

    def _reply(self, status, payload, content_type='application/json; charset=utf-8', extra=None):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, status, code):
        self._reply(status, {'error': code})

    def _trusted_request(self):
        port = self.server.server_port
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host', '').lower()
        if host not in allowed:
            self._error(403, 'invalid_host')
            return False
        if self.headers.get('Sec-Fetch-Site', '') == 'cross-site':
            self._error(403, 'cross_site_request')
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin.lower() != 'http://' + host:
            self._error(403, 'invalid_origin')
            return False
        return True

    def _route(self):
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            return None
        # Encoded separators/traversal never become filesystem paths.
        if parsed.scheme or parsed.netloc or '%' in parsed.path or '..' in parsed.path:
            return None
        return parsed.path

    def do_GET(self):
        if not self._trusted_request():
            return
        path = self._route()
        try:
            if path in STATIC:
                filename, mime = STATIC[path]
                file = PROJECT / 'web' / filename
                if not file.is_file():
                    return self._error(404, 'page_not_found')
                return self._reply(200, file.read_bytes(), mime)
            if path == '/api/bootstrap':
                listing = self.server.manager.list_runs()
                return self._reply(200, dict(listing, token=self.server.session_token,
                    api_key_configured=bool(os.environ.get('DEEPSEEK_API_KEY')),
                    worlds=public_worlds(),
                    defaults={'model': 'deepseek-flash', 'noise': False, 'seed': 42, 'world_id': DEFAULT_WORLD_ID,
                              'max_calls': None, 'max_total_tokens': 2000000,
                              'max_tokens_per_call': 65536, 'thinking': True}))
            if path == '/api/runs':
                return self._reply(200, self.server.manager.list_runs())
            pieces = (path or '').strip('/').split('/')
            if len(pieces) in (3, 4) and pieces[:2] == ['api', 'runs'] and RUN_ID.fullmatch(pieces[2]):
                if len(pieces) == 4 and pieces[3] != 'export':
                    return self._error(404, 'not_found')
                snapshot = self.server.manager.snapshot(pieces[2])
                if len(pieces) == 4:
                    return self._reply(200, snapshot, extra={
                        'Content-Disposition': f'attachment; filename="{pieces[2]}.json"'})
                return self._reply(200, snapshot)
            self._error(404, 'not_found')
        except (FileNotFoundError, KeyError):
            self._error(404, 'run_not_found')
        except ValueError:
            self._error(400, 'invalid_request')
        except Exception:
            self._error(500, 'server_error')

    def do_POST(self):
        self.close_connection = True
        if not self._trusted_request():
            return
        token = self.headers.get('X-Session-Token', '')
        if not token.isascii() or not secrets.compare_digest(token, self.server.session_token):
            return self._error(403, 'invalid_session_token')
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            return self._error(415, 'json_required')
        try:
            lengths = self.headers.get_all('Content-Length') or []
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                return self._error(400, 'invalid_content_length')
            try:
                length = int(lengths[0])
            except ValueError:
                return self._error(400, 'invalid_content_length')
            if length < 0:
                return self._error(400, 'invalid_content_length')
            if length > MAX_BODY:
                return self._error(413, 'request_too_large')
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                return self._error(400, 'json_object_required')
            json.dumps(body, allow_nan=False)
        except (ValueError, UnicodeError, OSError, RecursionError):
            return self._error(400, 'invalid_json')
        path = self._route()
        try:
            if path == '/api/runs':
                return self._reply(202, {'run_id': self.server.manager.start(body)})
            parts = (path or '').strip('/').split('/')
            if (len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[-1] in {'stop', 'delete', 'restore'}
                    and RUN_ID.fullmatch(parts[2])):
                action = parts[-1]
                if body:
                    return self._error(400, action + '_takes_no_arguments')
                result = getattr(self.server.manager, action)(parts[2])
                return self._reply(200, {'ok': True} if action == 'stop' else result)
            return self._error(404, 'not_found')
        except (FileNotFoundError, KeyError):
            self._error(404, 'run_not_found')
        except ValueError as exc:
            # Only locally generated validation codes; never echo arbitrary exception text.
            code = getattr(exc, 'code', None)
            self._error(400, code if isinstance(code, str) and re.fullmatch('[a-z_]{1,80}', code) else 'invalid_run_configuration')
        except RuntimeError as exc:
            code = getattr(exc, 'code', None)
            self._error(409, code if isinstance(code, str) and re.fullmatch('[a-z_]{1,80}', code) else 'run_already_active')
        except Exception:
            self._error(500, 'server_error')
        finally:
            body.pop('api_key', None)

    def do_OPTIONS(self):
        self._error(403, 'cross_origin_access_disabled')


def make_server(host='127.0.0.1', port=0, manager=None):
    if host not in ('127.0.0.1', 'localhost'):
        raise ValueError('The research console must bind to loopback')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Port must be an integer from 0 through 65535')
    if manager is None:
        from .web_jobs import RunManager
        manager = RunManager(PROJECT)
    server = WebServer((host, port), Handler)
    server.manager = manager
    server.session_token = secrets.token_urlsafe(32)
    return server


def main():
    parser = argparse.ArgumentParser(description='Local physical-law discovery console')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(port=args.port)
    print(f'彼岸研究台已启动：http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
