"""Bounded subprocess execution, private artifact IO, hashing and typed errors.

No shell, no credential logging, no implicit privilege escalation or networking.
Root state writes reject symlink components and use exclusive or atomic writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .models import CommandResult, Failure, TriageResult, ValidationIssue

ROOT = Path(__file__).resolve().parent.parent
STATE = Path('/var/lib/ubuntu-service-privacy')
T = TypeVar('T', bound=BaseModel)


class Blocked(RuntimeError):
    """A closed-world local failure; the reason contains no command output."""
    def __init__(self, reason: str):
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}', reason):
            raise ValueError('invalid local reason')
        self.reason = reason
        super().__init__(reason)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(model: BaseModel) -> bytes:
    # Producer side round-trip ensures cross-field validators have actually run.
    validated = type(model).model_validate(model.model_dump())
    return json.dumps(validated.model_dump(mode='json'), sort_keys=True,
                      separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise Blocked('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def parse_json(text: str, model: type[T]) -> T:
    if len(text.encode()) > 4_000_000:
        raise Blocked('INPUT_TOO_LARGE')
    value = json.loads(text, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(Blocked('NONFINITE_JSON')))
    return model.model_validate(value)


def read_private(path: Path, require_root: bool = False) -> bytes:
    if path.is_symlink():
        raise Blocked('SYMLINK_INPUT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4_000_000 or info.st_nlink != 1:
            raise Blocked('UNSAFE_INPUT_FILE')
        if require_root and (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o077):
            raise Blocked('ROOT_PRIVATE_INPUT_REQUIRED')
        chunks = []
        size = 0
        while True:
            data = os.read(fd, 65536)
            if not data:
                break
            size += len(data)
            if size > 4_000_000:
                raise Blocked('INPUT_TOO_LARGE')
            chunks.append(data)
        return b''.join(chunks)
    finally:
        os.close(fd)


def load(path: Path, model: type[T], require_root: bool = False) -> T:
    return parse_json(read_private(path, require_root).decode('utf-8'), model)


def secure_dir(path: Path, require_root: bool = False) -> None:
    if not path.is_absolute() or '..' in path.parts:
        raise Blocked('ABSOLUTE_STATE_PATH_REQUIRED')
    cursor = Path('/')
    for part in path.parts[1:]:
        cursor = cursor / part
        if not cursor.exists() and not cursor.is_symlink():
            cursor.mkdir(mode=0o700)
        info = cursor.lstat()
        if not stat.S_ISDIR(info.st_mode) or cursor.is_symlink():
            raise Blocked('UNSAFE_DIRECTORY_COMPONENT')
        if require_root and (info.st_uid != 0 or (info.st_mode & 0o022)):
            raise Blocked('ROOT_DIRECTORY_NOT_TRUSTED')
    if path.stat().st_mode & 0o077:
        # Never chmod an existing shared tree automatically.
        raise Blocked('PRIVATE_DIRECTORY_REQUIRED')


def write_new(path: Path, data: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise Blocked('ZERO_PROGRESS_WRITE')
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def replace_private(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        read_private(path, require_root=(os.geteuid() == 0))
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def tool(name: str) -> str:
    result = shutil.which(name, path='/usr/sbin:/usr/bin:/sbin:/bin')
    if not result:
        raise Blocked('MISSING_TOOL_' + name.upper().replace('-', '_'))
    return result


def command(argv: list[str], timeout: int = 30) -> CommandResult:
    if not argv or not Path(argv[0]).is_absolute():
        raise Blocked('ABSOLUTE_EXECUTABLE_REQUIRED')
    # Output is spooled and bounded, not accumulated unboundedly in RAM.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   start_new_session=True,
                                   env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C',
                                        'SYSTEMD_PAGER': 'cat', 'SYSTEMD_COLORS': '0',
                                        'SERVICE_PRIVACY_PYTHON': sys.executable,
                                        'UV_OFFLINE': '1', 'UV_NO_SYNC': '1', 'PIP_NO_INDEX': '1'})
        try:
            returncode = process.wait(timeout=timeout)
        except BaseException as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            if isinstance(error, subprocess.TimeoutExpired):
                raise Blocked('SUBPROCESS_TIMEOUT') from None
            raise
        out.seek(0); err.seek(0)
        stdout = out.read(2_000_001); stderr = err.read(2_000_001)
        if len(stdout) > 2_000_000 or len(stderr) > 2_000_000:
            raise Blocked('SUBPROCESS_OUTPUT_TOO_LARGE')
        return CommandResult(argv=argv, returncode=returncode,
                             stdout=stdout.decode('utf-8'), stderr=stderr.decode('utf-8'))


def checked(argv: list[str], timeout: int = 30) -> CommandResult:
    result = command(argv, timeout)
    if result.returncode != 0:
        raise Blocked('COMMAND_FAILED_' + Path(argv[0]).name.upper().replace('-', '_'))
    return result


def root_required() -> None:
    if os.geteuid() != 0:
        raise Blocked('EXPLICIT_ROOT_INVOCATION_REQUIRED')


def host_binding() -> str:
    machine = Path('/etc/machine-id').read_bytes().strip()
    boot = Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
    return sha(machine + b'\x00' + boot)


def make_failure(error: Exception) -> Failure:
    issues = []
    if isinstance(error, ValidationError):
        for item in error.errors(include_input=False, include_url=False):
            context = {k: (v if isinstance(v, (str, int, float, bool)) or v is None else type(v).__name__)
                       for k, v in item.get('ctx', {}).items()}
            issues.append(ValidationIssue(type=item['type'], loc=list(item['loc']),
                                          msg=item['msg'], ctx=context))
    else:
        # Never echo native output, file contents, process arguments, or rejected inputs.
        issues.append(ValidationIssue(type=type(error).__name__, loc=[],
                                      msg=error.reason if isinstance(error, Blocked) else 'operation failed; inspect locally'))
    reason = error.reason if isinstance(error, Blocked) else ('SCHEMA_REJECTED' if isinstance(error, ValidationError) else 'LOCAL_OPERATION_FAILED')
    runner = ROOT.parent / 'triage-error' / 'run.sh'
    status = 'UNAVAILABLE'
    triage = []
    if runner.is_file() and os.access(runner, os.X_OK):
        try:
            result = command([str(runner), 'classify', '--text', reason, '--layer', 'ubuntu_service_privacy'], 15)
            if result.returncode:
                status = 'CALL_FAILED'
            else:
                triage.append(parse_json(result.stdout, TriageResult))
                status = 'CLASSIFIED'
        except (ValueError, ValidationError):
            status = 'CONTRACT_REJECTED'
        except Exception:
            status = 'CALL_FAILED'
    recovery = ROOT / 'run.sh'
    if not recovery.is_file() or not os.access(recovery, os.X_OK):
        raise RuntimeError('recovery front door is not executable')
    return Failure(reason=reason, validation_errors=issues, triage_status=status,
                   triage_errors=triage, recovery_argv=[str(recovery), 'doctor'])
