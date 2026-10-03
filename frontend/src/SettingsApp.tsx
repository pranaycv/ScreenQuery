import { useEffect, useState } from "react";
import {
  captureNow,
  chooseFolder,
  fetchSettings,
  openPermission,
  quitApp,
  removeKey,
  saveKey,
  saveSettings,
  setLogin,
  useDefaultFolder,
  type SettingsPayload,
} from "./api";
import { Logo } from "./Logo";

const EMPTY: SettingsPayload = {
  save_enabled: true,
  clipboard_enabled: true,
  llm_enabled: false,
  custom_folder: null,
  base_url: "https://api.openai.com/v1",
  model: "gpt-4o",
  key_stored: false,
  key_status: "No API key stored.",
  login_supported: false,
  launch_at_login: false,
  permission_help: "",
  platform: "",
};

export function SettingsApp() {
  const [settings, setSettings] = useState<SettingsPayload>(EMPTY);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void fetchSettings()
      .then(setSettings)
      .catch((exc: Error) => setError(exc.message));
  }, []);

  const patch = async (next: Partial<SettingsPayload>) => {
    setError("");
    const merged = { ...settings, ...next };
    setSettings(merged);
    try {
      setSettings(await saveSettings(merged));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save settings.");
    }
  };

  const folderLabel = settings.custom_folder
    ? `Saves to ${settings.custom_folder}/<YYYY-MM-DD>/ScreenQuery-<time>.png`
    : "Saves to ~/ScreenQuery/<YYYY-MM-DD>/ScreenQuery-<time>.png";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__brand">
          <Logo />
          <div>
            <div className="topbar__title">ScreenQuery</div>
            <div className="topbar__tag">Shift+S+P captures the window. Shift+S+O crops an area.</div>
          </div>
        </div>
        <div className="topbar__status">
          <span className="status-dot" />
          Menu bar
        </div>
      </header>

      <main className="dashboard">
        <section className="card">
          <h2>When the hotkey fires</h2>
          <label className="check">
            <input
              type="checkbox"
              checked={settings.save_enabled}
              onChange={(event) => void patch({ save_enabled: event.target.checked })}
            />
            Save screenshot
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={settings.clipboard_enabled}
              onChange={(event) => void patch({ clipboard_enabled: event.target.checked })}
            />
            Copy to clipboard
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={settings.llm_enabled}
              onChange={(event) => void patch({ llm_enabled: event.target.checked })}
            />
            Send to OpenAI
          </label>
          <p>
            Copy is on by default, so you can paste the image with Cmd+V. Saving an API key turns on Send to
            OpenAI. If that switch is off, the popup says so instead of staying quiet.
          </p>
          <p>
            Shift+S+P captures the window in front. Shift+S+O lets you drag a rectangle anywhere. A crop of one
            word or one line is explained. A question is answered. Anything else gets two or three easy sentences.
          </p>
          {settings.key_stored && !settings.llm_enabled ? (
            <p className="notice">Sending is off. Turn on Send to OpenAI to get a reply. Your key stays saved.</p>
          ) : null}
        </section>

        <section className="card">
          <h2>Save location</h2>
          <p>{folderLabel}</p>
          <div className="row">
            <button className="btn" type="button" onClick={() => void chooseFolder().then(setSettings)}>
              Choose Folder…
            </button>
            <button className="btn" type="button" onClick={() => void useDefaultFolder().then(setSettings)}>
              Use Default
            </button>
          </div>
        </section>

        <section className="card">
          <h2>OpenAI</h2>
          <p>Paste your own key and choose Save Key. That stores it in the system keychain and turns on Send to OpenAI.</p>
          <label className="field">
            <span>API key</span>
            <input type="password" value={key} onChange={(event) => setKey(event.target.value)} />
          </label>
          <div className="row">
            <button
              className="btn primary"
              type="button"
              onClick={() =>
                void saveKey(key)
                  .then((next) => {
                    setSettings(next);
                    setKey("");
                  })
                  .catch((exc: Error) => setError(exc.message))
              }
            >
              Save Key
            </button>
            <button
              className="btn"
              type="button"
              onClick={() => void removeKey().then(setSettings).catch((exc: Error) => setError(exc.message))}
            >
              Remove Key
            </button>
          </div>
          <p>{settings.key_status}</p>
          <label className="field">
            <span>Base URL</span>
            <input
              type="text"
              value={settings.base_url}
              onChange={(event) => setSettings({ ...settings, base_url: event.target.value })}
              onBlur={() => void patch({ base_url: settings.base_url })}
            />
          </label>
          <label className="field">
            <span>Model</span>
            <input
              type="text"
              value={settings.model}
              onChange={(event) => setSettings({ ...settings, model: event.target.value })}
              onBlur={() => void patch({ model: settings.model })}
            />
          </label>
          <div className="row">
            {["gpt-4o", "gpt-4o-mini", "gpt-4.1"].map((name) => (
              <button key={name} className="btn" type="button" onClick={() => void patch({ model: name })}>
                {name}
              </button>
            ))}
          </div>
        </section>

        <section className="card">
          <h2>Permissions</h2>
          <p>{settings.permission_help}</p>
          {settings.platform === "darwin" ? (
            <div className="row">
              <button className="btn" type="button" onClick={() => void openPermission("screen")}>
                Screen Recording
              </button>
              <button className="btn" type="button" onClick={() => void openPermission("input")}>
                Input Monitoring
              </button>
              <button className="btn" type="button" onClick={() => void openPermission("accessibility")}>
                Accessibility
              </button>
            </div>
          ) : null}
        </section>

        <section className="card">
          <h2>General</h2>
          {settings.login_supported ? (
            <label className="check">
              <input
                type="checkbox"
                checked={settings.launch_at_login}
                onChange={(event) =>
                  void setLogin(event.target.checked)
                    .then(setSettings)
                    .catch((exc: Error) => setError(exc.message))
                }
              />
              Launch at login
            </label>
          ) : null}
          <p>ScreenQuery 1.0 · menu-bar utility</p>
        </section>
        {error ? <p className="notice">{error}</p> : null}
      </main>

      <footer className="shell-footer">
        <button className="btn primary" type="button" onClick={() => void captureNow()}>
          Capture Now
        </button>
        <button className="btn" type="button" onClick={() => void quitApp()}>
          Quit
        </button>
      </footer>
    </div>
  );
}
