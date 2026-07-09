"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, uploadExcel } from "@/lib/api";
import type { ImportBatch } from "@/types/api";
import { ErrorBox, StatusBadge, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";

export default function UploadPage() {
  const { auth } = useAuth();
  const canUpload = Boolean(auth?.can_upload);
  const [file, setFile] = useState<File | null>(null);
  const [uploadedBy, setUploadedBy] = useState("ui-operator");
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canUpload) {
      setError("Upload requires operator or admin role.");
      return;
    }
    if (!file) {
      setError("Choose a .xlsx file first.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setError("Only .xlsx Excel files are supported.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await uploadExcel(file, uploadedBy);
      setBatch(result.batch);
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Upload Excel</h1>
        <p>
          Upload a Qualys/MBSS-style .xlsx. Remediation text is stored for
          classification only — never executed as a command.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />
      {!canUpload ? (
        <div className="safety-note">
          Upload is disabled for role <code>{auth?.role || "unknown"}</code>.
          Requires operator or admin. Change token in Settings.
        </div>
      ) : null}
      <div className="panel">
        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="xlsx">Excel file (.xlsx)</label>
            <input
              id="xlsx"
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={!canUpload}
            />
          </div>
          <div className="field">
            <label htmlFor="uploaded_by">Uploaded by</label>
            <input
              id="uploaded_by"
              value={uploadedBy}
              onChange={(e) => setUploadedBy(e.target.value)}
              disabled={!canUpload}
            />
          </div>
          <button
            className="btn primary"
            type="submit"
            disabled={busy || !canUpload}
          >
            {busy ? "Uploading…" : "Upload"}
          </button>
        </form>
      </div>
      {batch ? (
        <div className="panel">
          <h2>Upload accepted</h2>
          <div className="grid-stats">
            <div className="stat">
              <div className="label">batch_id</div>
              <div className="value">{batch.id}</div>
            </div>
            <div className="stat">
              <div className="label">status</div>
              <div className="value" style={{ fontSize: "1rem" }}>
                <StatusBadge status={batch.status} />
              </div>
            </div>
            <div className="stat">
              <div className="label">filename</div>
              <div className="value" style={{ fontSize: "0.95rem" }}>
                {batch.original_filename}
              </div>
            </div>
          </div>
          <div className="btn-row">
            <Link className="btn primary" href={`/imports?batchId=${batch.id}`}>
              Open import summary
            </Link>
            <Link className="btn" href={`/records?batchId=${batch.id}`}>
              Review records
            </Link>
          </div>
          <p className="muted">
            Parse runs asynchronously via Celery. Refresh the import summary
            until status is <code>parsed</code>.
          </p>
        </div>
      ) : null}
    </div>
  );
}
