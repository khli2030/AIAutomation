"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  aiAnalyzeNeedsReview,
  listImports,
  listRecords,
} from "@/lib/api";
import type { ImportBatch, RawImportRecord } from "@/types/api";
import { ErrorBox, StatusBadge, SuccessBox } from "@/components/Ui";

function NeedsReviewInner() {
  const params = useSearchParams();
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [batchId, setBatchId] = useState(params.get("batchId") || "");
  const [records, setRecords] = useState<RawImportRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!batchId) return;
    const res = await listRecords(Number(batchId), {
      limit: 200,
      validation_status: "NEEDS_REVIEW",
    });
    setRecords(res.items);
  }

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

  useEffect(() => {
    if (!batchId) return;
    void load().catch((err) =>
      setError(err instanceof ApiError ? err.detail : String(err)),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  async function onAnalyze() {
    if (!batchId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await aiAnalyzeNeedsReview(Number(batchId));
      setMessage(
        `${result.message} Analyzed ${result.analyzed}; created ${result.suggestions_created} draft suggestion(s).`,
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
        <h1>Needs Review</h1>
        <p>
          Records classified as NEEDS_REVIEW. Trigger mock AI analysis to create
          draft suggestions — drafts are never executed.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />
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
        </div>
        <div className="btn-row">
          <button
            className="btn primary"
            type="button"
            disabled={busy || !batchId}
            onClick={() => void onAnalyze()}
          >
            {busy ? "Analyzing…" : "Run AI analysis for batch"}
          </button>
          <Link className="btn" href="/ai-suggestions">
            Open AI suggestions
          </Link>
        </div>
      </div>
      <div className="panel">
        <h2>NEEDS_REVIEW records ({records.length})</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Row</th>
                <th>Device</th>
                <th>Status</th>
                <th>Control</th>
                <th>Remediation (preview)</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td>{r.row_number}</td>
                  <td>{r.device_name}</td>
                  <td>
                    <StatusBadge status={r.validation_status} />
                  </td>
                  <td>{r.control_description || "—"}</td>
                  <td className="mono">
                    {(r.remediation || "").slice(0, 80)}
                    {(r.remediation || "").length > 80 ? "…" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function NeedsReviewPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <NeedsReviewInner />
    </Suspense>
  );
}
