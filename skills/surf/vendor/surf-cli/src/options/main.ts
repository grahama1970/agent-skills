const app = document.getElementById("app")!;

app.innerHTML = `
  <h1 style="font-size: 1.5rem; font-weight: bold; margin-bottom: 1.5rem;">Surf Settings</h1>
  
  <section style="margin-bottom: 2rem;">
    <h2 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">Debug Mode</h2>
    <label style="display: flex; align-items: center; gap: 0.5rem;">
      <input type="checkbox" id="debug-mode" style="width: 1rem; height: 1rem;" />
      <span>Enable debug logging</span>
    </label>
  </section>
  
  <section style="margin-bottom: 2rem;">
    <h2 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">Static Indicator</h2>
    <label style="display: flex; align-items: center; gap: 0.5rem;">
      <span>Heartbeat interval (seconds):</span>
      <input type="number" id="heartbeat-interval" min="5" max="60" value="10" style="width: 4rem; padding: 0.25rem 0.5rem; border: 1px solid #ccc; border-radius: 0.25rem;" />
    </label>
    <p class="muted" style="font-size: 0.875rem; margin-top: 0.5rem;">
      How often the static indicator checks if Surf is still active (5-60 seconds).
    </p>
  </section>
  
  <section style="margin-bottom: 2rem;">
    <h2 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">About</h2>
    <p class="muted">
      Surf v${chrome.runtime.getManifest().version}
    </p>
  </section>
`;

const debugCheckbox = document.getElementById("debug-mode") as HTMLInputElement | null;
if (debugCheckbox) {
  chrome.storage.local.get("debugMode").then(({ debugMode }) => {
    debugCheckbox.checked = !!debugMode;
  });
  debugCheckbox.addEventListener("change", () => {
    chrome.storage.local.set({ debugMode: debugCheckbox.checked });
  });
}

const heartbeatInput = document.getElementById("heartbeat-interval") as HTMLInputElement | null;
if (heartbeatInput) {
  chrome.storage.local.get("heartbeatInterval").then(({ heartbeatInterval }) => {
    heartbeatInput.value = String(heartbeatInterval ?? 10);
  });
  heartbeatInput.addEventListener("change", () => {
    const value = Math.max(5, Math.min(60, parseInt(heartbeatInput.value, 10) || 10));
    heartbeatInput.value = String(value);
    chrome.storage.local.set({ heartbeatInterval: value });
  });
}
