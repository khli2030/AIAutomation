"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  generatePlan,
  getImport,
  listImports,
  listRecords,
  validateBatch,
} from "@/lib/api";
import type { ImportBatch, ValidationSummary } from "@/types/api";
import { ErrorBox, StatusBadge, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";

function ImportsInner() {
  const { auth } = useAuth();
  const canValidate = Boolean(auth?.can_validate);
  const canPlan = Boolean(auth?.can_generate_plan);
  const params = useSearchParams();
  const initialId = params.get("batchId");
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [selectedId, setSelectedId] = useState<string>(initialId || "");
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [readyForPlan, setReadyForPlan] = useState(0);
  const [hasUnknownRecords, setHasUnknownRecords] = useState(false);
  const [planId, setPlanId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canValidateBatch = useMemo(() => {
    if (!canValidate || !batch) return false;
    // Allow when parsed, or when records still have null/unknown validation_status.
    return batch.status === "parsed" || hasUnknownRecords;
  }, [canValidate, batch, hasUnknownRecords]);

  const canGeneratePlan = useMemo(() => {
    const ready = validation?.ready_for_plan ?? readyForPlan;
    return Boolean(canPlan && ready > 0);
  }, [canPlan, validation, readyForPlan]);

  const refreshRecordHints = useCallback(async (batchId: number) => {
    const [ready, unknown] = await Promise.all([
      listRecords(batchId, {
        limit: 1,
        offset: 0,
        validation_status: "READY_FOR_PLAN",
      }),
      listRecords(batchId, { limit: 50, offset: 0 }),
    ]);
    setReadyForPlan(ready.total);
    const unknownCount = unknown.items.filter(
      (r) => !r.validation_status || r.validation_status === "UNKNOWN",
    ).length;
    // Also treat empty validation across the batch sample as unknown when total>0
    // and no READY/NEEDS yet (pre-validate).
    setHasUnknownRecords(
      unknownCount > 0 ||
        (unknown.total > 0 &&
          unknown.items.every((r) => !r.validation_status)),
    );
  }, []);

  async function refreshList() {
    const res = await listImports(100, 0);
    setBatches(res.items);
    if (!selectedId && res.items[0]) {
      setSelectedId(String(res.items[0].id));
    }
  }

  async function loadBatch(id: number) {
    const b = await getImport(id);
    setBatch(b);
    await refreshRecordHints(id);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refreshList();
        if (cancelled) return;
        setError(null);
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
    if (!selectedId) return;
    let cancelled = false;
    (async () => {
      try {
        await loadBatch(Number(selectedId));
        if (!cancelled) setError(null);
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
  }, [selectedId]);

  async function onRefresh() {
    if (!batch) {
      await refreshList();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await refreshList();
      await loadBatch(batch.id);
      setMessage(`Refreshed batch #${batch.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onValidate() {
    if (!batch) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const summary = await validateBatch(batch.id);
      setValidation(summary);
      setReadyForPlan(summary.ready_for_plan);
      setHasUnknownRecords(false);
      setMessage(
        `Validated: ${summary.ready_for_plan} READY_FOR_PLAN, ${summary.needs_review} NEEDS_REVIEW`,
      );
      await loadBatch(batch.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onGeneratePlan() {
    if (!batch) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await generatePlan(batch.id, auth?.actor || "ui-operator");
      setPlanId(result.plan.id);
      setMessage(
        `Plan #${result.plan.id} created with ${result.plan.job_count} job(s), ${result.plan.target_count} target(s).`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Import Summary</h1>
        <p>
          Validate Batch and Generate Plan from the UI. Operator/admin only.
          Refresh reloads batch + READY_FOR_PLAN hints.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />

      <div className="panel">
        <div className="filters">
          <div className="field">
            <label htmlFor="batch">Select batch</label>
            <select
              id="batch"
              value={selectedId}
              onChange={(e) => {
                setSelectedId(e.target.value);
                setValidation(null);
                setPlanId(null);
                setReadyForPlan(0);
                setHasUnknownRecords(false);
              }}
            >
              <option value="">—</option>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>
                  #{b.id} · {b.original_filename} · {b.status}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button
          className="btn"
          type="button"
          disabled={busy}
          onClick={() => void onRefresh()}
        >
          Refresh
        </button>
      </div>

      {batch ? (
        <div className="panel">
          <h2>Batch #{batch.id}</h2>
          <div className="grid-stats">
            <div className="stat">
              <div className="label">status</div>
              <div className="value" style={{ fontSize: "1rem" }}>
                <StatusBadge status={batch.status} />
              </div>
            </div>
            <div className="stat">
              <div className="label">total_records</div>
              <div className="value">{batch.total_records}</div>
            </div>
            <div className="stat">
              <div className="label">valid_records</div>
              <div className="value">{batch.valid_records}</div>
            </div>
            <div className="stat">
              <div className="label">READY_FOR_PLAN</div>
              <div className="value">
                {validation?.ready_for_plan ?? readyForPlan}
              </div>
            </div>
          </div>
          {batch.error_message ? (
            <p className="error">{batch.error_message}</p>
          ) : null}
          {!canValidate && !canPlan ? (
            <div className="safety-note">
              Validate / generate-plan require operator or admin. Current role:{" "}
              <code>{auth?.role || "unknown"}</code>.
            </div>
          ) : null}
          <div className="btn-row">
            <button
              className="btn primary"
              type="button"
              data-testid="validate-batch"
              disabled={busy || !canValidateBatch}
              onClick={() => void onValidate()}
              title={
                canValidate
                  ? "Validate batch"
                  : "Requires operator or admin"
              }
            >
              Validate Batch
            </button>
            <button
              className="btn"
              type="button"
              data-testid="generate-plan"
              disabled={busy || !canGeneratePlan}
              onClick={() => void onGeneratePlan()}
              title={
                canPlan
                  ? "Generate plan when READY_FOR_PLAN > 0"
                  : "Requires operator or admin"
              }
            >
              Generate Plan
            </button>
            <button
              className="btn"
              type="button"
              data-testid="refresh-batch"
              disabled={busy}
              onClick={() => void onRefresh()}
            >
              Refresh
            </button>
            <Link className="btn" href={`/records?batchId=${batch.id}`}>
              Records
            </Link>
            <Link className="btn" href={`/needs-review?batchId=${batch.id}`}>
              Needs review
            </Link>
          </div>
          {validation ? (
            <div className="grid-stats" style={{ marginTop: "1rem" }}>
              {Object.entries(validation)
                .filter(([k]) => k !== "batch_id")
                .map(([k, v]) => (
                  <div className="stat" key={k}>
                    <div className="label">{k}</div>
                    <div className="value">{v as number}</div>
                  </div>
                ))}
            </div>
          ) : null}
          {planId ? (
            <p>
              Open plan: <Link href={`/plans/${planId}`}>#{planId}</Link>
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function ImportsPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <ImportsInner />
    </Suspense>
  );
}
