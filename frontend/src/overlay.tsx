import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { fetchStatus, hideStatus, revealPath, type StatusPayload } from "./api";
import { Logo } from "./Logo";
import "./styles.css";

declare global {
  interface Window {
    __sqRefresh?: () => void;
  }
}

function ribbonLine(status: StatusPayload): string {
  const parts: string[] = [];
  if (status.llm_working) parts.push("Asking OpenAI…");
  if (status.answer) parts.push(status.answer.replace(/\s+/g, " ").trim());
  if (status.llm_error) parts.push(status.llm_error.replace(/\s+/g, " ").trim());
  if (status.banner) parts.push(status.banner.replace(/\s+/g, " ").trim());
  if (status.clipboard_note) parts.push(status.clipboard_note);
  if (status.clipboard_error) parts.push(status.clipboard_error);
  if (status.save_display) parts.push(`Saved ${status.save_display}`);
  if (status.save_error) parts.push(status.save_error);
  return parts.filter(Boolean).join("  ·  ") || "ScreenQuery";
}

function OverlayApp() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [generation, setGeneration] = useState(0);

  const refresh = useCallback(() => {
    void fetchStatus().then((snapshot) => {
      if (!snapshot.visible) return;
      setStatus(snapshot.status);
      setGeneration(snapshot.generation);
    });
  }, []);

  useEffect(() => {
    window.__sqRefresh = refresh;
    refresh();
    const timer = window.setInterval(refresh, 400);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!status || status.llm_working) return undefined;
    const seconds = status.answer || status.llm_error ? 20 : status.banner_is_error || status.save_error || status.clipboard_error ? 12 : 8;
    const seen = generation;
    const timer = window.setTimeout(() => {
      void hideStatus(seen);
    }, seconds * 1000);
    return () => window.clearTimeout(timer);
  }, [generation, status]);

  const line = status ? ribbonLine(status) : "ScreenQuery";
  const long = line.length > 72;
  const isError = Boolean(status?.llm_error || status?.banner_is_error || status?.save_error || status?.clipboard_error);

  return (
    <div className={`ribbon${isError ? " ribbon--error" : ""}`}>
      <Logo size={18} />
      <div className="ribbon__track">
        <span className={`ribbon__text${long ? " is-long" : ""}`}>
          {line}
          {long ? `    ${line}` : ""}
        </span>
      </div>
      {status?.save_full ? (
        <button className="ribbon__btn" type="button" title="Show in Folder" onClick={() => void revealPath(status.save_full || "")}>
          ↗
        </button>
      ) : null}
      <button className="ribbon__btn" type="button" title="Close" onClick={() => void hideStatus(generation)}>
        ✕
      </button>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OverlayApp />
  </StrictMode>,
);
