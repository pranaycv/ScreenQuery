/** Local Python API. The page never talks to the public internet. */

export interface SettingsPayload {
  save_enabled: boolean;
  clipboard_enabled: boolean;
  llm_enabled: boolean;
  custom_folder: string | null;
  base_url: string;
  model: string;
  key_stored: boolean;
  key_status: string;
  login_supported: boolean;
  launch_at_login: boolean;
  permission_help: string;
  platform: string;
}

export interface StatusPayload {
  banner: string | null;
  banner_is_error: boolean;
  save_display: string | null;
  save_full: string | null;
  save_error: string | null;
  llm_working: boolean;
  answer: string | null;
  llm_error: string | null;
  clipboard_copied: boolean;
  clipboard_error: string | null;
  clipboard_note: string | null;
}

export interface StatusSnapshot {
  generation: number;
  visible: boolean;
  status: StatusPayload;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const data = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

export function fetchSettings(): Promise<SettingsPayload> {
  return request("/api/settings");
}

export function saveSettings(patch: Partial<SettingsPayload>): Promise<SettingsPayload> {
  return request("/api/settings", { method: "POST", body: JSON.stringify(patch) });
}

export function saveKey(key: string): Promise<SettingsPayload> {
  return request("/api/key", { method: "POST", body: JSON.stringify({ key }) });
}

export function removeKey(): Promise<SettingsPayload> {
  return request("/api/key", { method: "DELETE" });
}

export function setLogin(enabled: boolean): Promise<SettingsPayload> {
  return request("/api/login", { method: "POST", body: JSON.stringify({ enabled }) });
}

export function openPermission(kind: "screen" | "input" | "accessibility"): Promise<void> {
  return request("/api/permissions", { method: "POST", body: JSON.stringify({ kind }) });
}

export function chooseFolder(): Promise<SettingsPayload> {
  return request("/api/folder", { method: "POST", body: JSON.stringify({}) });
}

export function useDefaultFolder(): Promise<SettingsPayload> {
  return request("/api/folder/default", { method: "POST", body: JSON.stringify({}) });
}

export function captureNow(): Promise<void> {
  return request("/api/capture", { method: "POST", body: JSON.stringify({}) });
}

export function quitApp(): Promise<void> {
  return request("/api/quit", { method: "POST", body: JSON.stringify({}) });
}

export function fetchStatus(): Promise<StatusSnapshot> {
  return request("/api/status");
}

export function hideStatus(generation?: number): Promise<void> {
  return request("/api/status/hide", {
    method: "POST",
    body: JSON.stringify(generation == null ? {} : { generation }),
  });
}

export function revealPath(path: string): Promise<void> {
  return request("/api/reveal", { method: "POST", body: JSON.stringify({ path }) });
}
