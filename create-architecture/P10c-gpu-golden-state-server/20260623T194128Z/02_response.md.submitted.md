Fix GPU inference probe. PersonaPlex container uses streaming audio binary WebSocket, not one-shot REST. The golden_state_server.py already knows how to run LMGen.step() with GPU. Update the probe to run golden_state_server as a subprocess with --probe-lmgen-step --json flags. Set real_gpu_personaplex=true only when valid generated output is received from the subprocess.

Zip: personaplex-p10c-gpu-golden-state-server-solution.zip

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260623T194628Z:3a5e30ec>>>

Do not print anything after that marker.
