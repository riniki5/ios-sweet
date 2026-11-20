#!/usr/bin/env python3
"""Install SweetNativeMetal over the opt-in USB file service, keeping a backup.

Run only after booting with sweetfiles=1. The old Metal plugin is not touched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket

REMOTE = "/System/Library/Extensions/SweetNativeMetal.bundle"
FILES = (
    ("SweetNativeMetal", 0o755),
    ("libSweetNativeBackend.dylib", 0o755),
    ("Info.plist", 0o644),
    ("_CodeSignature/CodeResources", 0o644),
    ("Licenses/Mesa.txt", 0o644),
    ("Licenses/HakiOS.txt", 0o644),
)


class Phone:
    def __init__(self, host, port=2223):
        self.host, self.port = host, port

    def request(self, header, body=b"", allow_missing=False):
        sock = socket.create_connection((self.host, self.port), timeout=30)
        try:
            sock.settimeout(60)
            sock.sendall(header + body)
            line = bytearray()
            while not line.endswith(b"\n"):
                chunk = sock.recv(1)
                if not chunk:
                    raise RuntimeError("phone closed the connection without a reply")
                line += chunk
            reply = line.decode().strip()
            if reply.startswith("ERR "):
                code = int(reply.split()[1])
                if allow_missing and code == 2:
                    sock.close()
                    return None
                raise RuntimeError(f"phone: {reply}")
            if not reply.startswith("OK"):
                raise RuntimeError(f"unexpected phone reply: {reply}")
            return sock, reply
        except Exception:
            sock.close()
            raise

    def get(self, path):
        response = self.request(f"GET {path}\n".encode(), allow_missing=True)
        if response is None:
            return None
        sock, reply = response
        size = int(reply.split()[1])
        try:
            data = bytearray()
            while len(data) < size:
                chunk = sock.recv(min(65536, size - len(data)))
                if not chunk:
                    raise RuntimeError(f"short read for {path}: {len(data)} of {size}")
                data += chunk
            return bytes(data)
        finally:
            sock.close()

    def put(self, path, data, mode):
        header = f"PUT {path} {mode:o} {len(data)}\n".encode()
        response = self.request(header, data)
        if response is None:
            raise RuntimeError("unexpected empty PUT response")
        sock, reply = response
        try:
            if int(reply.split()[1]) != len(data):
                raise RuntimeError(f"short PUT confirmation for {path}: {reply}")
        finally:
            sock.close()

    def command(self, command):
        response = self.request((command + "\n").encode())
        if response is not None:
            response[0].close()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install", help="install a bundle and save a rollback copy")
    install.add_argument("bundle", type=Path)
    install.add_argument("backup", type=Path)
    restore = commands.add_parser("restore", help="restore the bundle saved by install")
    restore.add_argument("backup", type=Path)
    for command in (install, restore):
        command.add_argument("--host", default=os.environ.get("PHONE_FILES_HOST", "192.168.7.2"))
        command.add_argument("--port", type=int, default=2223)
    args = parser.parse_args()
    phone = Phone(args.host, args.port)
    if args.command == "restore":
        manifest_path = args.backup / "manifest.json"
        if not manifest_path.is_file():
            parser.error(f"backup manifest is missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        for rel, mode in reversed(FILES):
            path = f"{manifest['remote']}/{rel}"
            backup = args.backup / rel
            if backup.is_file():
                old = backup.read_bytes()
                phone.put(path, old, mode)
                actual = phone.get(path)
                if actual is None or digest(actual) != digest(old):
                    raise RuntimeError(f"restore readback hash mismatch: {rel}")
                print(f"restored: {rel}")
            else:
                current = phone.get(path)
                if current is not None:
                    phone.command(f"RM {path}")
                    print(f"removed newly added: {rel}")
        phone.command("SYNC")
        return
    if (args.backup / "manifest.json").exists():
        parser.error(f"backup already contains a manifest: {args.backup}")
    sources = []
    for rel, mode in FILES:
        source = args.bundle / rel
        if not source.is_file():
            parser.error(f"bundle is missing {rel}")
        sources.append((rel, mode, source.read_bytes()))

    args.backup.mkdir(parents=True, exist_ok=True)
    previous = {}
    changed = []
    try:
        # Snapshot and persist the rollback set before changing the phone.
        for rel, mode, new in sources:
            path = f"{REMOTE}/{rel}"
            old = phone.get(path)
            previous[rel] = old
            if old is not None:
                saved = args.backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                if saved.exists() and saved.read_bytes() != old:
                    raise RuntimeError(f"refusing to overwrite different backup {saved}")
                saved.write_bytes(old)
        manifest = {
            "remote": REMOTE,
            "host": args.host,
            "installed": {rel: digest(data) for rel, _, data in sources},
            "backup": {rel: digest(data) if data is not None else None for rel, data in previous.items()},
        }
        (args.backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        phone.command(f"MKDIR {REMOTE} 755")
        phone.command(f"MKDIR {REMOTE}/_CodeSignature 755")
        phone.command(f"MKDIR {REMOTE}/Licenses 755")
        for rel, mode, new in sources:
            path = f"{REMOTE}/{rel}"
            old = previous[rel]
            if old is not None and digest(old) == digest(new):
                print(f"same: {rel}")
                continue
            changed.append(rel)
            phone.put(path, new, mode)
            actual = phone.get(path)
            if actual is None or digest(actual) != digest(new):
                raise RuntimeError(f"readback hash mismatch: {rel}")
            print(f"installed: {rel} sha256={digest(new)}")
        phone.command("SYNC")
    except Exception:
        for rel in reversed(changed):
            path = f"{REMOTE}/{rel}"
            old = previous[rel]
            try:
                if old is None:
                    phone.command(f"RM {path}")
                else:
                    mode = dict(FILES)[rel]
                    phone.put(path, old, mode)
            except Exception as rollback_error:
                print(f"ROLLBACK FAILED for {rel}: {rollback_error}")
        try:
            phone.command("SYNC")
        except Exception as sync_error:
            print(f"ROLLBACK SYNC FAILED: {sync_error}")
        raise

    print(f"backup and manifest: {args.backup}")
    print("the running image must have SWEET_NATIVE_METAL=1; install before GPU discovery restarts backboardd")


if __name__ == "__main__":
    main()
