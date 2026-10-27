"""Short-lived local parser child. Input is private bytes over stdin, never a path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading

# -I deliberately removes the working directory from sys.path. Only the
# application checkout is added back; no imported sample code is executable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def emit(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
    sys.stdout.flush()


def main():
    # If the parent crashes, this fixed deadline bounds the orphan's lifetime.
    timer = threading.Timer(15.0, lambda: os._exit(124))
    timer.daemon = True
    timer.start()
    try:
        from app.report_layout import sample_byte_limit, parse_layout_sample
        raw = sys.stdin.buffer.read(sample_byte_limit(sys.argv[1]) + 1)
        result = parse_layout_sample(raw, sys.argv[1], progress=lambda stage: emit({'event':'stage','stage':stage}))
        emit({'event':'result','result':result})
    except ValueError as error:
        code = str(error)
        emit({'event':'failure','code':code if code.startswith('layout_') and len(code)<120 else 'layout_invalid_document'})
    except Exception:
        # The exception or input is never returned in a stream or log.
        emit({'event':'failure','code':'layout_parser_internal'})


if __name__ == '__main__':
    main()
