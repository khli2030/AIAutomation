"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, listImports, listRecords } from "@/lib/api";
import type { ImportBatch, RawImportRecord } from "@/types/api";
import { ErrorBox, StatusBadge } from "@/components/Ui";

function RecordsInner() {
  const params = useSearchParams();
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [batchId, setBatchId] = useState(params.get("batchId") || "");
  const [validationStatus, setValidationStatus] = useState("");
  const [taskCode, setTaskCode] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [records, setRecords] = useState<RawImportRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<RawImportRecord | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await listImports(100, 0);
        if (cancelled) return;
        setBatches(res.items);
        if (!batchId && res.items[0]) setBatchId(String(res.items[0].id));
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.detail : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load() {
    if (!batchId) return;
    setError(null);
    try {
      const res = await listRecords(Number(batchId), {
        limit: 200,
        validation_status: validationStatus || undefined,
        task_code: taskCode || undefined,
        device_name: deviceName || undefined,
      });
      setRecords(res.items);
      setTotal(res.total);
      setSelected(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  useEffect(() => {
    if (batchId) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  return (
    <div>
      <div className="page-header">
        <h1>Records Review</h1>
        <p>
          Filter raw import records. Remediation and Expected Configuration are
          shown for review only — never executed.
        </p>
      </div>
      <ErrorBox message={error} />
      <div className="panel">
        <div className="filters">
          <div className="field">
            <label>Batch</label>
            <select value={batchId} onChange={(e) => setBatchId(e.target.value)}>
              <option value="">—</option>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>
                  #{b.id} · {b.original_filename}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>validation_status</label>
            <select
              value={validationStatus}
              onChange={(e) => setValidationStatus(e.target.value)}
            >
              <option value="">(any)</option>
              <option value="READY_FOR_PLAN">READY_FOR_PLAN</option>
              <option value="NEEDS_REVIEW">NEEDS_REVIEW</option>
              <option value="ASSET_NOT_FOUND">ASSET_NOT_FOUND</option>
              <option value="ALREADY_COMPLIANT">ALREADY_COMPLIANT</option>
              <option value="DUPLICATE">DUPLICATE</option>
              <option value="INVALID_RECORD">INVALID_RECORD</option>
              <option value="UNSUPPORTED_CONTROL">UNSUPPORTED_CONTROL</option>
            </select>
          </div>
          <div className="field">
            <label>task_code</label>
            <input
              value={taskCode}
              onChange={(e) => setTaskCode(e.target.value)}
              placeholder="SSH_DISABLE_ROOT_LOGIN"
            />
          </div>
          <div className="field">
            <label>device_name</label>
            <input
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              placeholder="e2e-linux"
            />
          </div>
        </div>
        <button className="btn primary" type="button" onClick={() => void load()}>
          Apply filters
        </button>
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          Showing {records.length} of {total}
        </p>
      </div>

      <div className="two-col">
        <div className="panel">
          <h2>Records</h2>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Device</th>
                  <th>Status</th>
                  <th>Task</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelected(r)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>{r.row_number}</td>
                    <td>{r.device_name}</td>
                    <td>
                      <StatusBadge status={r.validation_status} />
                    </td>
                    <td className="mono">{r.task_code || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <h2>Details</h2>
          {!selected ? (
            <p className="muted">Select a record.</p>
          ) : (
            <>
              <p>
                <strong>{selected.device_name}</strong> · row {selected.row_number}
              </p>
              <p className="muted">{selected.control_description}</p>
              <div className="safety-note">
                Remediation text below is never executed as a shell/Ansible
                command.
              </div>
              <h3 style={{ fontSize: "0.85rem" }}>Remediation</h3>
              <div className="pre-block mono">{selected.remediation || "—"}</div>
              <h3 style={{ fontSize: "0.85rem" }}>Expected Configuration</h3>
              <div className="pre-block mono">
                {selected.expected_configuration || "—"}
              </div>
              {selected.validation_error ? (
                <p className="error" style={{ marginTop: "0.75rem" }}>
                  {selected.validation_error}
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RecordsPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <RecordsInner />
    </Suspense>
  );
}
