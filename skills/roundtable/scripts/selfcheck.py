import subprocess, json, pathlib, tempfile
d = pathlib.Path(__file__).parent.parent
with tempfile.TemporaryDirectory() as t:
    pkt = pathlib.Path(t, "p.md"); pkt.write_text("Assess X.")
    for mode, extra in [("roundtable", []), ("compete", ["--criterion", "verified"])]:
        out = str(pathlib.Path(t, mode + ".js"))
        r = subprocess.run(["bash", str(d / "run.sh"), "--mode", mode, "--packet-file", str(pkt),
                            "--seat", "gpt=openai-codex/gpt-5.5:high", "--web", "webgpt", "--web-research", "webx",
                            "--out", out] + extra, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        js = pathlib.Path(out).read_text()
        assert "webgpt" in js and "fail-closed" in js and "webRuns" in js, "web models must be first-class"
        assert '"model": "openai-codex/gpt-5.5:high"' in js
    # fail-closed: no seats at all
    r = subprocess.run(["bash", str(d / "run.sh"), "--mode", "roundtable", "--packet", "x",
                        "--out", str(pathlib.Path(t, "bad.js"))], capture_output=True, text=True)
    assert r.returncode != 0 and "no seats" in r.stderr
print("selfcheck OK: both modes generate, web first-class, no-seat fails closed")
