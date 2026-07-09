"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  approveSuggestion,
  convertSuggestionToCatalog,
  listSuggestions,
  rejectSuggestion,
} from "@/lib/api";
import type { AISuggestion } from "@/types/api";
import { ErrorBox, StatusBadge, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";

export default function AISuggestionsPage() {
  const { auth } = useAuth();
  const canApprove = Boolean(auth?.can_approve_suggestion);
  const canReject = Boolean(auth?.can_reject_suggestion);
  const canConvert = Boolean(auth?.can_convert_catalog);
  const [status, setStatus] = useState("draft");
  const [items, setItems] = useState<AISuggestion[]>([]);
  const [selected, setSelected] = useState<AISuggestion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const res = await listSuggestions({
      status: status || undefined,
      limit: 100,
    });
    setItems(res.items);
    setSelected(null);
  }

  useEffect(() => {
    void load().catch((err) =>
      setError(err instanceof ApiError ? err.detail : String(err)),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function onApprove() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await approveSuggestion(
        selected.id,
        auth?.actor || "ui-approver",
      );
      setMessage(`Suggestion #${updated.id} approved (status only — not executed).`);
      await load();
      setSelected(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await rejectSuggestion(
        selected.id,
        auth?.actor || "ui-approver",
      );
      setMessage(`Suggestion #${updated.id} rejected.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onConvert() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const result = await convertSuggestionToCatalog(
        selected.id,
        auth?.actor || "ui-admin",
      );
      setMessage(
        `${result.message} catalog_id=${result.catalog_id} task_code=${result.task_code} is_enabled=${result.is_enabled}`,
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>AI Suggestions</h1>
        <p>
          Review draft suggestions. Approve / reject change status only. Convert
          creates a <strong>disabled</strong> catalog entry — AI{" "}
          <code>generated_playbook</code> is never executable from this UI.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />
      <div className="panel">
        <div className="filters">
          <div className="field">
            <label>Status filter</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">(any)</option>
              <option value="draft">draft</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
              <option value="converted">converted</option>
            </select>
          </div>
        </div>
      </div>
      <div className="two-col">
        <div className="panel">
          <h2>Suggestions ({items.length})</h2>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Suggested task</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => setSelected(s)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>{s.id}</td>
                    <td>
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="mono">{s.suggested_task_code || "—"}</td>
                    <td>{s.risk_level || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <h2>Detail</h2>
          {!selected ? (
            <p className="muted">Select a suggestion.</p>
          ) : (
            <>
              <p>
                Record #{selected.raw_record_id} ·{" "}
                <StatusBadge status={selected.status} />
              </p>
              <p className="muted">{selected.control_description}</p>
              <div className="safety-note">
                Playbook editing is disabled. Convert always sends{" "}
                <code>enable: false</code>. Approve/reject need approver or
                admin; convert-to-catalog is <strong>admin only</strong>. Current
                role: <code>{auth?.role || "unknown"}</code>.
              </div>
              <h3 style={{ fontSize: "0.85rem" }}>generated_playbook (read-only)</h3>
              <div className="pre-block mono">
                {selected.generated_playbook || "(none)"}
              </div>
              <h3 style={{ fontSize: "0.85rem" }}>Safety warnings</h3>
              <div className="pre-block mono">
                {selected.safety_warnings || "—"}
              </div>
              <div className="btn-row">
                <button
                  className="btn primary"
                  type="button"
                  disabled={
                    busy ||
                    !canApprove ||
                    selected.status === "converted"
                  }
                  onClick={() => void onApprove()}
                  title={
                    canApprove
                      ? "Approve suggestion"
                      : "Requires approver or admin"
                  }
                >
                  Approve
                </button>
                <button
                  className="btn danger"
                  type="button"
                  disabled={
                    busy ||
                    !canReject ||
                    selected.status === "converted"
                  }
                  onClick={() => void onReject()}
                  title={
                    canReject
                      ? "Reject suggestion"
                      : "Requires approver or admin"
                  }
                >
                  Reject
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={
                    busy ||
                    !canConvert ||
                    selected.status !== "approved"
                  }
                  onClick={() => void onConvert()}
                  title={
                    canConvert
                      ? "Creates disabled catalog entry only"
                      : "Requires admin"
                  }
                >
                  Convert to disabled catalog
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
