"use client";

import { useEffect, useId, useRef } from "react";

export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="badge">—</span>;
  const s = status.toLowerCase();
  let cls = "badge";
  if (
    s.includes("success") ||
    s === "parsed" ||
    s === "approved" ||
    s === "ready_for_plan" ||
    s === "converted"
  ) {
    cls += " ok";
  } else if (
    s.includes("fail") ||
    s.includes("reject") ||
    s === "invalid_record" ||
    s === "asset_not_found"
  ) {
    cls += " danger";
  } else if (
    s.includes("waiting") ||
    s.includes("review") ||
    s.includes("draft") ||
    s.includes("running")
  ) {
    cls += " warn";
  }
  return <span className={cls}>{status}</span>;
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="error">{message}</div>;
}

export function SuccessBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="success">{message}</div>;
}

export function CounterMap({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data || {});
  return (
    <div className="panel">
      <h2>{title}</h2>
      {entries.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <div className="grid-stats">
          {entries.map(([key, value]) => (
            <div className="stat" key={key}>
              <div className="label">{key || "unknown"}</div>
              <div className="value">{value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Simple confirmation modal for bulk / destructive workflow actions. */
export function ConfirmModal({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) confirmRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={() => {
        if (!busy) onCancel();
      }}
    >
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId}>{title}</h2>
        <p>{body}</p>
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            className={`btn ${danger ? "danger" : "primary"}`}
            type="button"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
