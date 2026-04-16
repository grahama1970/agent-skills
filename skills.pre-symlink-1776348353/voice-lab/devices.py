"""PipeWire device enumeration and selection.

Parses wpctl/pw-cli output to list audio sources and sinks with
IDs, names, volumes, and default markers.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class AudioDevice:
    """Represents a PipeWire audio device."""

    id: int
    name: str
    device_type: str  # "source" or "sink"
    is_default: bool = False
    volume: Optional[float] = None
    muted: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.device_type,
            "is_default": self.is_default,
            "volume": self.volume,
            "muted": self.muted,
        }


def _run_wpctl_status() -> str:
    """Run wpctl status and return output."""
    result = subprocess.run(
        ["wpctl", "status"], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"wpctl status failed (rc={result.returncode}): {result.stderr}")
    return result.stdout


def _parse_section(output: str, section_name: str) -> list[AudioDevice]:
    """Parse a section (Sources or Sinks) from wpctl status output."""
    devices = []
    in_section = False
    in_audio = False
    device_type = "source" if "Source" in section_name or "source" in section_name.lower() else "sink"

    for line in output.splitlines():
        stripped = line.strip()

        # Detect Audio section
        if "Audio" in stripped and not in_audio:
            in_audio = True
            continue

        if not in_audio:
            continue

        # Detect start of target section (Sources or Sinks)
        if section_name in stripped:
            in_section = True
            continue

        # End section on next header or empty indentation break
        if in_section:
            # New section header (not indented enough or different section)
            if stripped and not stripped.startswith("│") and not stripped.startswith("*") and not re.match(r'^\d+\.', stripped):
                # Check if this is a different section header
                if any(s in stripped for s in ["Sinks:", "Sources:", "Filters:", "Streams:", "Video"]):
                    in_section = False
                    continue

            # Parse device lines like:
            #  *   47. Jabra SPEAK 510 USB Analog Stereo [vol: 1.00]
            #      55. USB Audio Microphone Analog Stereo [vol: 0.74]
            match = re.match(
                r'[\s│]*(\*?)\s*(\d+)\.\s+(.+?)(?:\s+\[vol:\s*([\d.]+)(\s+MUTED)?\])?\s*$',
                line,
            )
            if match:
                is_default = match.group(1) == "*"
                dev_id = int(match.group(2))
                name = match.group(3).strip()
                volume = float(match.group(4)) if match.group(4) else None
                muted = match.group(5) is not None

                devices.append(AudioDevice(
                    id=dev_id,
                    name=name,
                    device_type=device_type,
                    is_default=is_default,
                    volume=volume,
                    muted=muted,
                ))

    return devices


def list_devices(
    source_only: bool = False,
    sink_only: bool = False,
) -> list[AudioDevice]:
    """List all PipeWire audio devices."""
    output = _run_wpctl_status()

    devices = []
    if not sink_only:
        devices.extend(_parse_section(output, "Sources:"))
    if not source_only:
        devices.extend(_parse_section(output, "Sinks:"))

    return devices


def find_device(name_substring: str, device_type: Optional[str] = None) -> Optional[AudioDevice]:
    """Find a device by name substring match."""
    source_only = device_type == "source"
    sink_only = device_type == "sink"
    devices = list_devices(source_only=source_only, sink_only=sink_only)

    needle = name_substring.lower()
    for dev in devices:
        if needle in dev.name.lower():
            return dev
    return None


def get_default_source() -> Optional[AudioDevice]:
    """Get the default audio source (microphone)."""
    devices = list_devices(source_only=True)
    for dev in devices:
        if dev.is_default:
            return dev
    return devices[0] if devices else None


def print_devices(
    source_only: bool = False,
    sink_only: bool = False,
    json_output: bool = False,
) -> None:
    """Display devices in a table or JSON."""
    devices = list_devices(source_only=source_only, sink_only=sink_only)

    if json_output:
        print(json.dumps([d.to_dict() for d in devices], indent=2))
        return

    if not devices:
        console.print("[yellow]No audio devices found[/yellow]")
        return

    table = Table(title="PipeWire Audio Devices")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Type", width=8)
    table.add_column("Name")
    table.add_column("Volume", justify="right")
    table.add_column("Default", justify="center")

    for dev in devices:
        vol_str = ""
        if dev.volume is not None:
            vol_str = f"{dev.volume:.2f}"
            if dev.muted:
                vol_str += " [red]MUTED[/red]"
        default_str = "[green]*[/green]" if dev.is_default else ""

        table.add_row(
            str(dev.id),
            dev.device_type,
            dev.name,
            vol_str,
            default_str,
        )

    console.print(table)
