#!/usr/bin/env python3
"""Install or restore the sweet Wi-Fi userspace over the opt-in USB file service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import socket

LAUNCHD = "/System/Library/xpc/launchd.plist"
JOB = "/System/Library/LaunchDaemons/org.ios-sweet.wland.plist"
LABEL = "org.ios-sweet.wland"
DIRECTORIES = (
    "/var/local/bin",
    "/var/local/fw",
    "/var/local/fw/modem",
    "/var/local/fw/rw",
    "/var/local/fw/rmtfs",
)
FIRMWARE_PATTERNS = ("modem.*", "modemr.jsn", "wlanmdsp.mbn", "modemuw.jsn", "bdwlan.*")
RMTFS_FILES = ("modemst1.img", "modemst2.img", "fsg.img", "fsc.img")
DONOR_COMMIT = "f09fdb58a2c074d131072947b247240532b7d97d"
REPOSITORY = Path(__file__).resolve().parents[1]
PATCH_DIRECTORY = REPOSITORY / "userspace/wifi/wland-0239"


class Phone:
    def __init__(self, host, port):
        self.host = host
        self.port = port

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
            raise RuntimeError(f"unexpected empty PUT response for {path}")
        sock, reply = response
        try:
            if int(reply.split()[1]) != len(data):
                raise RuntimeError(f"short PUT confirmation for {path}: {reply}")
        finally:
            sock.close()

    def command(self, command, allow_error=False):
        try:
            response = self.request((command + "\n").encode())
        except RuntimeError:
            if allow_error:
                return
            raise
        if response is not None:
            response[0].close()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def backup_path(root, remote):
    path = root / remote.lstrip("/")
    path.resolve().relative_to(root.resolve())
    return path


def verify_build(binaries):
    metadata_path = binaries / "wifi-build.json"
    sums_path = binaries / "SHA256SUMS"
    if not metadata_path.is_file() or not sums_path.is_file():
        raise RuntimeError(f"missing Wi-Fi build metadata in {binaries}")
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid Wi-Fi build metadata: {error}") from error
    if metadata.get("donor_commit") != DONOR_COMMIT:
        raise RuntimeError("Wi-Fi binaries were not built from the pinned ios-flame donor commit")
    expected_patches = {
        path.relative_to(REPOSITORY).as_posix(): digest(path.read_bytes().replace(b"\r\n", b"\n"))
        for path in sorted(PATCH_DIRECTORY.glob("*.patch"))
    }
    if metadata.get("patches") != expected_patches:
        raise RuntimeError("Wi-Fi build patch hashes do not match this repository")
    expected_files = {"wland", "netsvc"}
    if set(metadata.get("files", {})) != expected_files:
        raise RuntimeError("Wi-Fi build metadata must describe exactly wland and netsvc")
    sums = {}
    for line in sums_path.read_text().splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise RuntimeError(f"invalid SHA256SUMS line: {line}")
        checksum, name = fields[0], fields[1].lstrip("*")
        if name not in expected_files or name in sums:
            raise RuntimeError(f"unexpected or duplicate SHA256SUMS entry: {name}")
        sums[name] = checksum
    if set(sums) != expected_files:
        raise RuntimeError("SHA256SUMS must contain exactly wland and netsvc")
    for name in sorted(expected_files):
        path = binaries / name
        if not path.is_file():
            raise RuntimeError(f"missing userspace binary: {path}")
        actual = digest(path.read_bytes())
        if actual != metadata["files"][name] or actual != sums[name]:
            raise RuntimeError(f"Wi-Fi binary hash mismatch: {name}")


def sources(args):
    verify_build(args.binaries)
    result = []
    for name in ("wland", "netsvc"):
        path = args.binaries / name
        if not path.is_file():
            raise RuntimeError(f"missing userspace binary: {path}")
        result.append((path, f"/var/local/bin/{name}", 0o755))
    firmware = {}
    for pattern in FIRMWARE_PATTERNS:
        for path in sorted(args.firmware.glob(pattern)):
            if path.is_file():
                firmware[path.name] = path
    required = {"modem.mdt", "modemr.jsn", "wlanmdsp.mbn", "modemuw.jsn"}
    missing = sorted(name for name in required if name not in firmware)
    if not any(name.startswith("modem.b") for name in firmware):
        missing.append("modem.bNN")
    if not any(name.startswith("bdwlan.") for name in firmware):
        missing.append("bdwlan.*")
    if missing:
        raise RuntimeError(f"missing modem/WLAN firmware in {args.firmware}: {', '.join(missing)}")
    for name, path in sorted(firmware.items()):
        result.append((path, f"/var/local/fw/modem/{name}", 0o644))
    for name in RMTFS_FILES:
        path = args.rmtfs / name
        if not path.is_file():
            raise RuntimeError(f"missing RMTFS image: {path}")
        result.append((path, f"/var/local/fw/rmtfs/{name}", 0o600))
    return result


def launchd_data(current):
    plist = plistlib.loads(current)
    jobs = plist.setdefault("LaunchDaemons", {})
    jobs[JOB] = {
        "Label": LABEL,
        "ProgramArguments": ["/var/local/bin/wland", "auto"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "UserName": "root",
        "EnvironmentVariables": {
            "PATH": "/var/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "SWEET_WLAND_LAUNCHD": "1"
        },
    }
    return plistlib.dumps(plist, fmt=plistlib.FMT_BINARY)


def install(args, phone):
    if (args.backup / "manifest.json").exists():
        raise RuntimeError(f"backup already contains a manifest: {args.backup}")
    files = sources(args)
    current_launchd = phone.get(LAUNCHD)
    if current_launchd is None:
        raise RuntimeError(f"missing {LAUNCHD}")
    new_launchd = launchd_data(current_launchd)
    records = [(remote, mode, path.read_bytes()) for path, remote, mode in files]
    records.append((LAUNCHD, 0o644, new_launchd))
    args.backup.mkdir(parents=True, exist_ok=True)
    manifest = {"host": args.host, "port": args.port, "files": []}
    for remote, mode, data in records:
        old = current_launchd if remote == LAUNCHD else phone.get(remote)
        rel = remote.lstrip("/")
        saved = backup_path(args.backup, remote)
        if old is not None:
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and saved.read_bytes() != old:
                raise RuntimeError(f"refusing to overwrite different backup {saved}")
            saved.write_bytes(old)
        manifest["files"].append({
            "remote": remote,
            "relative": rel,
            "mode": mode,
            "installed": digest(data),
            "backup": digest(old) if old is not None else None,
        })
    (args.backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    changed = []
    try:
        for directory in DIRECTORIES:
            phone.command(f"MKDIR {directory} 755", allow_error=True)
        for remote, mode, data in records:
            phone.put(remote, data, mode)
            changed.append(remote)
            actual = phone.get(remote)
            if actual is None or digest(actual) != digest(data):
                raise RuntimeError(f"readback hash mismatch: {remote}")
            print(f"installed: {remote} sha256={digest(data)}")
        phone.command("SYNC")
    except Exception:
        for remote in reversed(changed):
            entry = next(item for item in manifest["files"] if item["remote"] == remote)
            try:
                current = phone.get(remote)
                current_hash = digest(current) if current is not None else None
                if current_hash is None and entry["backup"] is None:
                    continue
                if current_hash is not None and current_hash != entry["installed"] and current_hash != entry["backup"]:
                    print(f"ROLLBACK SKIPPED modified file: {remote}")
                    continue
                if current_hash == entry["backup"]:
                    continue
                saved = backup_path(args.backup, remote)
                if saved.is_file():
                    data = saved.read_bytes()
                    if digest(data) != entry["backup"]:
                        raise RuntimeError("backup hash mismatch")
                    phone.put(remote, data, entry["mode"])
                else:
                    phone.command(f"RM {remote}", allow_error=True)
            except Exception as error:
                print(f"ROLLBACK FAILED for {remote}: {error}")
        try:
            phone.command("SYNC")
        except Exception as error:
            print(f"ROLLBACK SYNC FAILED: {error}")
        raise
    print(f"backup and manifest: {args.backup}")
    print("reboot with SWEET_WIFI=1; logs: /var/local/wland.log and /var/local/wland.log.prev")


def restore(args, phone):
    manifest_path = args.backup / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"backup manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid backup manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("host") != args.host or manifest.get("port") != args.port:
        raise RuntimeError("backup manifest does not match this phone host and port")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("backup manifest does not contain a file list")

    required = {LAUNCHD, "/var/local/bin/wland", "/var/local/bin/netsvc"}
    required.update(f"/var/local/fw/rmtfs/{name}" for name in RMTFS_FILES)
    required.update(f"/var/local/fw/modem/{name}" for name in ("modem.mdt", "modemr.jsn", "wlanmdsp.mbn", "modemuw.jsn"))
    seen = set()
    previous = {}
    current = {}
    expected_backups = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("backup manifest contains an invalid file entry")
        remote = entry.get("remote")
        if not isinstance(remote, str) or not remote.startswith("/") or any(part in ("", ".", "..") for part in remote.split("/")[1:]):
            raise RuntimeError(f"invalid remote path in backup manifest: {remote!r}")
        if remote != LAUNCHD and not remote.startswith(("/var/local/bin/", "/var/local/fw/modem/", "/var/local/fw/rmtfs/")):
            raise RuntimeError(f"unexpected remote path in backup manifest: {remote}")
        if remote in {"/var/local/bin/wland", "/var/local/bin/netsvc"}:
            pass
        elif remote.startswith("/var/local/bin/"):
            raise RuntimeError(f"unexpected binary path in backup manifest: {remote}")
        elif remote.startswith("/var/local/fw/modem/"):
            if "/" in remote.removeprefix("/var/local/fw/modem/"):
                raise RuntimeError(f"unexpected nested firmware path in backup manifest: {remote}")
        elif remote.startswith("/var/local/fw/rmtfs/"):
            if remote not in {f"/var/local/fw/rmtfs/{name}" for name in RMTFS_FILES}:
                raise RuntimeError(f"unexpected RMTFS path in backup manifest: {remote}")
        elif remote != LAUNCHD:
            raise RuntimeError(f"unexpected remote path in backup manifest: {remote}")
        if remote in seen or entry.get("relative") != remote.lstrip("/"):
            raise RuntimeError(f"duplicate or inconsistent backup entry: {remote}")
        seen.add(remote)
        mode = entry.get("mode")
        if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 0o7777:
            raise RuntimeError(f"invalid mode in backup manifest: {remote}")
        installed_hash = entry.get("installed")
        backup_hash = entry.get("backup")
        if not valid_digest(installed_hash) or (backup_hash is not None and not valid_digest(backup_hash)):
            raise RuntimeError(f"invalid hash in backup manifest: {remote}")
        saved = backup_path(args.backup, remote)
        if backup_hash is None:
            if saved.exists():
                raise RuntimeError(f"unexpected backup file for newly added {remote}")
            previous[remote] = None
        else:
            if not saved.is_file():
                raise RuntimeError(f"backup file is missing: {saved}")
            data = saved.read_bytes()
            if digest(data) != backup_hash:
                raise RuntimeError(f"backup hash mismatch: {saved}")
            previous[remote] = data
            expected_backups.add(remote.lstrip("/"))

    missing = required - seen
    if missing or not any(remote.startswith("/var/local/fw/modem/modem.b") for remote in seen) or not any(remote.startswith("/var/local/fw/modem/bdwlan.") for remote in seen):
        raise RuntimeError(f"backup manifest is incomplete: {', '.join(sorted(missing)) or 'modem.bNN/bdwlan.*'}")
    actual_backups = {
        path.relative_to(args.backup).as_posix()
        for path in args.backup.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual_backups != expected_backups:
        raise RuntimeError("backup directory contains missing or unexpected files")

    for entry in entries:
        remote = entry["remote"]
        data = phone.get(remote)
        current[remote] = data
        if data is not None:
            current_hash = digest(data)
            if current_hash != entry["installed"] and current_hash != entry["backup"]:
                raise RuntimeError(f"refusing to overwrite modified file: {remote}")

    for entry in reversed(entries):
        remote = entry["remote"]
        old = previous[remote]
        if old is None:
            if current[remote] is not None:
                phone.command(f"RM {remote}")
                print(f"removed newly added: {remote}")
            continue
        if current[remote] == old:
            print(f"same: {remote}")
            continue
        phone.put(remote, old, entry["mode"])
        actual = phone.get(remote)
        if actual is None or digest(actual) != digest(old):
            raise RuntimeError(f"restore readback hash mismatch: {remote}")
        print(f"restored: {remote}")
    phone.command("SYNC")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    install_parser = commands.add_parser("install", help="install userspace, firmware, RMTFS and launchd job")
    install_parser.add_argument("--binaries", type=Path, required=True)
    install_parser.add_argument("--firmware", type=Path, required=True)
    install_parser.add_argument("--rmtfs", type=Path, required=True)
    install_parser.add_argument("--backup", type=Path, required=True)
    restore_parser = commands.add_parser("restore", help="restore a previous Wi-Fi installation")
    restore_parser.add_argument("--backup", type=Path, required=True)
    for command in (install_parser, restore_parser):
        command.add_argument("--host", default=os.environ.get("PHONE_FILES_HOST", "192.168.7.2"))
        command.add_argument("--port", type=int, default=2223)
    args = parser.parse_args()
    phone = Phone(args.host, args.port)
    if args.command == "install":
        install(args, phone)
    else:
        restore(args, phone)


if __name__ == "__main__":
    main()
