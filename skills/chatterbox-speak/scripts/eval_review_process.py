"""Process probes for the retained terminal review eval; no human selections.

Runs the actual CLI in a PTY and checks pre-render rejection via the public CLI.
"""
import os
import pty
import select
import struct
import subprocess
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def tty_cancel(run: Path, rows: int = 70, columns: int = 160):
    """Actual public CLI; compact navigation probes cancel without submitting."""
    master, slave = pty.openpty()
    import fcntl
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
    process = subprocess.Popen([str(ROOT / 'run.sh'), 'review', 'celebration'], stdin=slave, stdout=slave, stderr=slave,
                               env={**os.environ, 'TERM': 'xterm-256color'}, start_new_session=True)
    os.close(slave)
    received = bytearray(); deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], .2)[0]:
                try: received.extend(os.read(master, 65536))
                except OSError: break
            if (b'RELEVANT TURNS' if rows < 15 else b'PROVISIONAL AGENT') in received:
                break
        if rows < 15:
            check(b'CONTEXT' in received and b'RELEVANT TURNS' in received, 'compact PTY context is hidden')
            for key, marker in [(b'2', b'C02'), (b'\x12', b'Rationale (required)')]:
                os.write(master, key)
                update = bytearray(); deadline = time.monotonic() + 10
                while marker not in update and time.monotonic() < deadline:
                    if select.select([master], [], [], .2)[0]:
                        chunk = os.read(master, 65536); update.extend(chunk); received.extend(chunk)
                check(marker in update, f'compact PTY navigation did not display {marker!r}')
        else:
            check(b'Embry Reply Interview' in received and b'PROVISIONAL AGENT' in received, 'actual terminal command did not render context/recommendation')
        os.write(master, b'\x1b')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and process.poll() is None:
            if select.select([master], [], [], .2)[0]:
                try: received.extend(os.read(master, 65536))
                except OSError: break
        process.wait(timeout=10)
        check(process.returncode == 0, 'terminal cancellation failed')
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=5)
        os.close(master)
        (run / 'actual-terminal.ansi').write_bytes(received)
    return str(run / 'actual-terminal.ansi')



def reject_missing_target_render(run: Path):
    destination = run / 'must-not-render.jsonl'
    command = subprocess.run([str(ROOT / 'run.sh'), 'compare', 'render', str(ROOT / 'fixtures/reply_variants.jsonl'),
                              'celebration', str(destination)], capture_output=True, text=True, timeout=45)
    (run / 'render-rejected.stdout').write_text(command.stdout);(run / 'render-rejected.stderr').write_text(command.stderr)
    check(command.returncode != 0 and 'missing_expected_response' in command.stdout and not destination.exists(), 'public render bypassed expected-target gate')
