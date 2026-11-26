#!/usr/bin/env python3
"""Fetch and decode the last persistent SWEETLOG over the USB file service.

  sweet-log-usb.py OUT.txt

Boot with sweetfiles=1 and sweetlog=0 to preserve the previous boot's log.
The raw area is saved as OUT.txt.bin before it is decoded by sweet-log.py.
"""
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HOST = os.environ.get('PHONE_FILES_HOST', '192.168.7.2')
PORT = 2223
MAX_LOG_AREA = 4 * 1024 * 1024 + 4096


def reply(s):
    line = bytearray()
    while len(line) < 128:
        char = s.recv(1)
        if not char:
            raise RuntimeError('connection closed without a reply')
        line += char
        if char == b'\n':
            return bytes(line)
    raise RuntimeError('oversized reply from phone')


def fetch(host, port, out):
    out = Path(out)
    raw = out.with_name(out.name + '.bin')
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with socket.create_connection((host, port), timeout=30) as s:
            s.settimeout(60)
            s.sendall(b'GETLOG\n')
            line = reply(s)
            fields = line.decode('ascii').strip().split()
            if len(fields) != 2 or fields[0] != 'OK':
                raise RuntimeError(f'phone: {line.decode("ascii", "replace").strip()}')
            try:
                size = int(fields[1])
            except ValueError:
                raise RuntimeError(f'phone: invalid log size in {line!r}') from None
            if size <= 0 or size > MAX_LOG_AREA:
                raise RuntimeError(f'phone: invalid log size {size}')
            fd, temporary = tempfile.mkstemp(prefix=raw.name + '.', suffix='.tmp', dir=raw.parent)
            with os.fdopen(fd, 'wb') as f:
                left = size
                while left:
                    chunk = s.recv(min(65536, left))
                    if not chunk:
                        raise RuntimeError(f'short log read: {size - left} of {size} bytes')
                    f.write(chunk)
                    left -= len(chunk)
        os.replace(temporary, raw)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return raw


def main(argv):
    if len(argv) != 1:
        raise SystemExit(__doc__)
    out = Path(argv[0])
    raw = fetch(HOST, PORT, out)
    decoder = Path(__file__).with_name('sweet-log.py')
    try:
        subprocess.run([sys.executable, str(decoder), str(raw), str(out)], check=True)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f'decode failed; raw log kept at {raw} (exit {error.returncode})') from None
    print(f'{raw.stat().st_size} bytes -> {raw}; decoded -> {out}')


if __name__ == '__main__':
    main(sys.argv[1:])
