"""Desktop bridge for native hosts.

Supports both:
- native length-prefixed JSON desktop commands: {"id": 1, "cmd": "...", "args": {...}}
- legacy line-delimited JSON pseudo-HTTP requests used by older experiments
"""
from __future__ import annotations

import json
import os
import struct
import sys
import traceback
import urllib.parse
from typing import Any, Dict, Literal


_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from api.routes import handle_api_request  # noqa: E402
from desktop_api import dispatch_command  # noqa: E402


WireMode = Literal['line', 'length']


def _emit(payload: dict, wire_mode: WireMode) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    if wire_mode == 'length':
        sys.stdout.buffer.write(struct.pack('<I', len(raw)))
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        return
    sys.stdout.write(raw.decode('utf-8') + '\n')
    sys.stdout.flush()


def _normalize_body(raw_body):
    if raw_body is None:
        return None
    if isinstance(raw_body, (dict, list)):
        return json.dumps(raw_body).encode('utf-8')
    if isinstance(raw_body, str):
        return raw_body.encode('utf-8')
    if isinstance(raw_body, bytes):
        return raw_body
    return json.dumps(raw_body).encode('utf-8')


def _read_exact(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        block = stream.read(size - len(chunks))
        if not block:
            raise EOFError
        chunks.extend(block)
    return bytes(chunks)


def _read_request():
    stream = sys.stdin.buffer
    while True:
        first = stream.read(1)
        if not first:
            raise EOFError
        if first in b' \r\n\t':
            continue
        break

    if first in (b'{', b'['):
        line = first + stream.readline()
        return json.loads(line.decode('utf-8')), 'line'

    prefix = first + _read_exact(stream, 3)
    size = struct.unpack('<I', prefix)[0]
    payload = _read_exact(stream, size)
    return json.loads(payload.decode('utf-8')), 'length'


def _handle_typed_command(request: Dict[str, Any]) -> Dict[str, Any]:
    request_id = request.get('id')
    command = str(request.get('cmd') or '').strip()
    args = request.get('args') or {}
    if not command:
        raise ValueError('Missing command')
    result = dispatch_command(command, dict(args))
    return {
        'id': request_id,
        'ok': True,
        'result': result,
        'error': None,
    }


def _handle_legacy_http(request: Dict[str, Any]) -> Dict[str, Any]:
    request_id = request.get('id')
    url = str(request.get('url') or '')
    method = str(request.get('method') or 'GET').upper()
    split = urllib.parse.urlsplit(url)
    path = split.path or str(request.get('path') or '')
    query = split.query or str(request.get('query') or '')
    body = _normalize_body(request.get('body'))
    result = handle_api_request(method, path, query, body)
    return {
        'id': request_id,
        'status': 200,
        'json': result,
    }


def main() -> int:
    while True:
        try:
            request, wire_mode = _read_request()
        except EOFError:
            break

        try:
            if isinstance(request, dict) and request.get('cmd'):
                response = _handle_typed_command(request)
            else:
                response = _handle_legacy_http(request if isinstance(request, dict) else {})
        except Exception as exc:
            request_id = request.get('id') if isinstance(request, dict) else None
            if isinstance(request, dict) and request.get('cmd'):
                response = {
                    'id': request_id,
                    'ok': False,
                    'result': None,
                    'error': str(exc),
                    'traceback': traceback.format_exc(),
                }
            else:
                response = {
                    'id': request_id,
                    'status': 500,
                    'error': str(exc),
                    'traceback': traceback.format_exc(),
                    'json': {'error': str(exc)},
                }

        _emit(response, wire_mode)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
