"""Execution-feedback hook of the 20-unit check run."""
import atexit
import json
import os
import sys
import traceback

_FILE = os.environ.get('COREDB_DIAG_FILE')
_ROOT = os.path.abspath(os.environ.get('COREDB_DIAG_ROOT') or '.')
_COUNTS = {}


def _frames(tb):
    frames = traceback.extract_tb(tb)
    own = [f for f in frames if os.path.abspath(f.filename).startswith(_ROOT)]
    return [{'file': os.path.relpath(f.filename, os.path.dirname(_ROOT)), 'line': f.lineno, 'function': f.name,
             'code': (f.line or '')[:200]} for f in (own or frames)[-4:]]


def _write(entry):
    try:
        with open(_FILE, 'a') as handle:
            handle.write(json.dumps(entry) + '\n')
    except OSError:
        pass


_LAST = []


def _record(exc_type, exc, tb, how):
    if not _FILE or exc_type is None or tb is None:
        return
    if _LAST and _LAST[0] is exc:
        return
    _LAST[:] = [exc]
    frames = _frames(tb)
    key = (exc_type.__name__, tuple((f['file'], f['line']) for f in frames))
    if key not in _COUNTS:
        _write({'event': 'first', 'how': how, 'exception': exc_type.__name__, 'message': repr(exc)[:300],
                'frames': frames})
    _COUNTS[key] = _COUNTS.get(key, 0) + 1


class _Stream:
    """stdout / stderr wrapper: a write while an exception is being handled records its location."""

    def __init__(self, stream):
        self._stream = stream
        self._busy = False

    def write(self, text):
        if not self._busy:
            self._busy = True
            try:
                info = sys.exc_info()
                if info[0] is not None:
                    _record(*info, how='reported while handled')
            finally:
                self._busy = False
        return self._stream.write(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _hook(exc_type, exc, tb):
    _record(exc_type, exc, tb, how='uncaught')
    _previous(exc_type, exc, tb)


def _counts():
    for (name, location), count in _COUNTS.items():
        _write({'event': 'count', 'exception': name, 'location': [list(x) for x in location], 'count': count})


if _FILE:
    sys.stdout, sys.stderr = _Stream(sys.stdout), _Stream(sys.stderr)
    _previous, sys.excepthook = sys.excepthook, _hook
    atexit.register(_counts)
