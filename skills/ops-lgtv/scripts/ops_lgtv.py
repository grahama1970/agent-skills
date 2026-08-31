"""ops-lgtv: LG webOS TV sound-path control and gain-staging diagnostics.

LAN-only CLI over the SSAP WebSocket API (bscpylgtv), the same interface the
LG mobile app uses. Mutations are gated behind --execute. `gain-staging`
composes the ops-wiim skill to merge TV-side and amp-side state.

Exit codes: 0 ok, 2 TV unreachable/unpaired, 3 mutation without --execute.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()  # repo-root/skill .env (LGTV_IP); run.sh also sources repo .env

app = typer.Typer(add_completion=False, help=__doc__)

OPS_WIIM_RUN = Path(__file__).resolve().parents[2] / "ops-wiim" / "run.sh"
TIMEOUT = 10.0


def _lg_ip(ip: str | None) -> str:
    ip = ip or os.environ.get("LGTV_IP", "")
    if not ip:
        typer.echo("error: no TV IP. Pass --ip or set LGTV_IP.", err=True)
        raise typer.Exit(2)
    return ip


async def _client(ip: str, timeout: float = TIMEOUT):
    from bscpylgtv import WebOsClient

    client = await WebOsClient.create(ip, ping_interval=None)
    try:
        await asyncio.wait_for(client.connect(), timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"timed out after {timeout}s waiting for the TV ({ip}) — accept the pairing prompt on the TV screen"
        ) from None
    return client


def _down(ip: str, exc: Exception) -> None:
    typer.echo(json.dumps({"status": "down", "ip": ip, "error": str(exc)}), err=True)
    raise typer.Exit(2)


@app.command()
def pair(ip: str = typer.Option(None, "--ip"),
         attempts: int = typer.Option(12, "--attempts", help="how many times to raise the on-TV prompt"),
         wait: int = typer.Option(25, "--wait", help="seconds between prompt attempts")) -> None:
    """Pair with the TV. Accept the prompt ON THE TV. Re-raises the prompt until accepted."""
    ip = _lg_ip(ip)
    import time

    last_err: Exception | None = None
    for i in range(max(1, attempts)):
        async def go():
            client = await _client(ip, timeout=90)
            out = {"paired": True, "ip": ip, "attempt": i + 1,
                   "sound_output": await client.get_sound_output()}
            await client.disconnect()
            return out

        try:
            typer.echo(json.dumps(asyncio.run(go()), default=str))
            return
        except Exception as exc:  # noqa: BLE001 - probe loop, classified below
            last_err = exc
            if "refused" in str(exc).lower() or "unreachable" in str(exc).lower():
                break  # TV is off/unreachable; retrying will not help
        if i < attempts - 1:
            time.sleep(wait)

    hint = ""
    if last_err and "refused" in str(last_err).lower():
        hint = "TV unreachable - power it on first"
    else:
        hint = ("no acceptance within the windows - if NO prompt appeared on the TV, "
                "enable Settings > Network > LG Connect Apps and check network device restrictions")
    typer.echo(json.dumps({"paired": False, "ip": ip, "attempts": attempts,
                           "error": str(last_err) if last_err else "unknown", "hint": hint}), err=True)
    raise typer.Exit(2)


@app.command()
def sound(ip: str = typer.Option(None, "--ip"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Read the TV's sound output route and volume (read-only)."""
    ip = _lg_ip(ip)

    async def go():
        client = await _client(ip)
        out = {
            "schema": "ops_lgtv.sound.v1",
            "ip": ip,
            "sound_output": await client.get_sound_output(),
            "volume": await client.get_volume(),
            "not_observable": [
                "Digital Sound Out PCM/Pass Through (change in Settings -> Sound)",
                "Auto Volume / AI Sound state",
            ],
        }
        await client.disconnect()
        return out

    try:
        typer.echo(json.dumps(asyncio.run(go()), indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)


@app.command("set-sound-output")
def set_sound_output(output: str = typer.Argument(..., help="e.g. external_arc, tv_speaker, optical"),
                     ip: str = typer.Option(None, "--ip"),
                     execute: bool = typer.Option(False, "--execute")) -> None:
    """Change the TV's sound output route (gated behind --execute; read back afterwards)."""
    ip = _lg_ip(ip)
    if not execute:
        typer.echo(json.dumps({"refused": True, "reason": "set-sound-output is a mutation; pass --execute"}), err=True)
        raise typer.Exit(3)

    async def go():
        client = await _client(ip)
        await client.change_sound_output(output)
        readback = await client.get_sound_output()
        await client.disconnect()
        return {"requested": output, "readback": readback}

    try:
        typer.echo(json.dumps(asyncio.run(go()), default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)


@app.command("power-state")
def power_state(ip: str = typer.Option(None, "--ip")) -> None:
    """Read the TV's power state (read-only)."""
    ip = _lg_ip(ip)

    async def go():
        client = await _client(ip)
        out = {"schema": "ops_lgtv.power_state.v1", "ip": ip,
               "power_state": await client.get_power_state()}
        await client.disconnect()
        return out

    try:
        typer.echo(json.dumps(asyncio.run(go()), default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)


@app.command("power-off")
def power_off(ip: str = typer.Option(None, "--ip"),
              execute: bool = typer.Option(False, "--execute")) -> None:
    """Turn the TV off (gated behind --execute; power state read back afterwards)."""
    ip = _lg_ip(ip)
    if not execute:
        typer.echo(json.dumps({"refused": True, "reason": "power-off is a mutation; pass --execute"}), err=True)
        raise typer.Exit(3)

    async def go():
        client = await _client(ip)
        before = await client.get_power_state()
        await client.power_off()
        await asyncio.sleep(2)
        try:
            after = await client.get_power_state()
        except Exception:  # noqa: BLE001 - screen-off disconnects the WS session
            after = "disconnected_after_power_off"
        return {"before": before, "after": after}

    try:
        typer.echo(json.dumps(asyncio.run(go()), default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)


@app.command("power-on")
def power_on(ip: str = typer.Option(None, "--ip"),
            execute: bool = typer.Option(False, "--execute")) -> None:
    """Wake the TV (gated behind --execute; requires 'Mobile TV On'/WoWLAN enabled)."""
    ip = _lg_ip(ip)
    if not execute:
        typer.echo(json.dumps({"refused": True, "reason": "power-on is a mutation; pass --execute"}), err=True)
        raise typer.Exit(3)

    async def go():
        client = await _client(ip)
        await client.power_on()
        await asyncio.sleep(4)
        try:
            state = await client.get_power_state()
        except Exception:  # noqa: BLE001
            state = "unanswered_after_wake"
        return {"requested": "on", "power_state": state}

    try:
        typer.echo(json.dumps(asyncio.run(go()), default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)


@app.command("audio-settings")
def audio_settings(ip: str = typer.Option(None, "--ip"), json_out: bool = typer.Option(False, "--json")) -> None:
    """Enumerate the TV's sound settings via SSAP/luna (read-only, raw key dump)."""
    ip = _lg_ip(ip)

    async def go():
        client = await _client(ip)
        out = {"schema": "ops_lgtv.audio_settings.v1", "ip": ip,
               "audio_status": await client.get_audio_status()}
        for cat in ("sound", "option"):
            try:
                res = await client.luna_request(
                    "ssap://com.webos.service.settings/getSettings", {"category": cat})
                out[f"settings_{cat}"] = res
            except Exception as exc:  # noqa: BLE001 - keep enumerating other categories
                out[f"settings_{cat}"] = {"error": str(exc)}
        await client.disconnect()
        return out

    try:
        typer.echo(json.dumps(asyncio.run(go()), indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)


@app.command("gain-staging")
def gain_staging(ip: str = typer.Option(None, "--ip"),
                 wiim_ip: str = typer.Option(None, "--wiim-ip"),
                 json_out: bool = typer.Option(False, "--json")) -> None:
    """Merged TV-vs-amp gain-staging report. Composes the ops-wiim skill for the amp side."""
    ip = _lg_ip(ip)
    report: dict = {"schema": "ops_lgtv.gain_staging.v1", "tv_ip": ip}

    async def tv_side():
        client = await _client(ip)
        out = {"sound_output": await client.get_sound_output(), "volume": await client.get_volume()}
        await client.disconnect()
        return out

    try:
        report["tv"] = json.loads(json.dumps(asyncio.run(tv_side()), default=str))
    except Exception as exc:  # noqa: BLE001
        _down(ip, exc)

    wiim_cmd = [str(OPS_WIIM_RUN), "diagnose", "--json"]
    if wiim_ip:
        wiim_cmd += ["--ip", wiim_ip]
    proc = subprocess.run(wiim_cmd, capture_output=True, text=True, timeout=60)
    try:
        report["amp"] = json.loads(proc.stdout)
    except ValueError:
        report["amp"] = {"status": "down", "error": proc.stdout or proc.stderr}

    findings = []
    tv_out = str(report["tv"].get("sound_output", ""))
    if "arc" not in tv_out.lower() and "external" not in tv_out.lower():
        findings.append({"finding": "tv_not_routed_to_amp",
                         "detail": f"TV sound_output is {tv_out!r}, not an external/ARC route",
                         "next": "run set-sound-output external_arc --execute"})
    amp = report.get("amp", {})
    if amp.get("status") == "up":
        player = amp.get("snapshot", {}).get("player", {})
        if str(player.get("mute")) == "0" and int(player.get("vol", 0)) >= 60 and not findings:
            findings.append({"finding": "amp_config_healthy_tv_routed",
                             "detail": f"amp vol={player.get('vol')} unmuted; TV routed to {tv_out!r}",
                             "next": "remaining quiet output points at TV Digital Sound Out (set PCM) or Auto Volume — not observable via API"})
    report["findings"] = findings
    typer.echo(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
