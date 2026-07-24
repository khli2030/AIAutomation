"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  approveJob,
  dryRunJob,
  getPlan,
  listPlanJobs,
  rejectJob,
  runJob,
} from "@/lib/api";
import type { ExecutionJob, ExecutionPlan } from "@/types/api";
import { ConfirmModal, ErrorBox, StatusBadge, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";
import {
  filterJobsForBulk,
  runBulkJobAction,
  type BulkActionKind,
  type BulkProgress,
  type BulkSummary,
} from "@/lib/bulkJobs";

const REJECT_STATUSES = new Set([
  "waiting_dry_run",
  "dry_run_failed",
  "waiting_approval",
]);

function countByStatus(jobs: ExecutionJob[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const j of jobs) {
    counts[j.status] = (counts[j.status] || 0) + 1;
  }
  return counts;
}

export default function PlanDetailPage() {
  const params = useParams<{ planId: string }>();
  const planId = Number(params.planId);
  const { auth } = useAuth();
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyJobId, setBusyJobId] = useState<number | null>(null);
  const [bulkProgress, setBulkProgress] = useState<BulkProgress | null>(null);
  const [confirmKind, setConfirmKind] = useState<BulkActionKind | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);

  const canDryRun = Boolean(auth?.can_dry_run);
  const canApprove = Boolean(auth?.can_approve_job);
  const canReject = Boolean(auth?.can_reject_job);
  const canRun = Boolean(auth?.can_run);

  const statusCounts = useMemo(() => countByStatus(jobs), [jobs]);
  const waitingCount = filterJobsForBulk(jobs, "dry_run").length;
  const dryRunSuccessCount = filterJobsForBulk(jobs, "approve").length;
  const approvedCount = filterJobsForBulk(jobs, "run").length;

  const refresh = useCallback(async () => {
    if (!planId) return;
    const [p, j] = await Promise.all([getPlan(planId), listPlanJobs(planId)]);
    setPlan(p);
    setJobs(j.items);
  }, [planId]);

  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    (async () => {
      try {
        await refresh();
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
  }, [planId, refresh]);

  async function withJobBusy(jobId: number, fn: () => Promise<void>) {
    setBusyJobId(jobId);
    setError(null);
    setMessage(null);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusyJobId(null);
    }
  }

  async function onDryRun(job: ExecutionJob) {
    await withJobBusy(job.id, async () => {
      const summary = await dryRunJob(job.id);
      setMessage(`Dry-run job #${job.id}: ${summary.status}`);
    });
  }

  async function onApprove(job: ExecutionJob) {
    await withJobBusy(job.id, async () => {
      const updated = await approveJob(job.id, auth?.actor || "ui-operator");
      setMessage(`Approved job #${job.id} → ${updated.status}`);
    });
  }

  async function onReject(job: ExecutionJob) {
    await withJobBusy(job.id, async () => {
      const updated = await rejectJob(job.id, auth?.actor || "ui-operator");
      setMessage(`Rejected job #${job.id} → ${updated.status}`);
    });
  }

  async function onRun(job: ExecutionJob) {
    await withJobBusy(job.id, async () => {
      const summary = await runJob(job.id);
      setMessage(`Run job #${job.id}: ${summary.status}`);
    });
  }

  function confirmCopy(kind: BulkActionKind): { title: string; body: string } {
    if (kind === "dry_run") {
      return {
        title: "Bulk dry-run",
        body: `Dry-run ${waitingCount} job(s) in waiting_dry_run only? Never runs apply. Continue on individual failures.`,
      };
    }
    if (kind === "approve") {
      return {
        title: "Bulk approve",
        body: `Approve ${dryRunSuccessCount} job(s) with status dry_run_success only? dry_run_failed jobs are never approved.`,
      };
    }
    return {
      title: "Bulk run",
      body: `Run ${approvedCount} approved job(s) only? Jobs still in dry_run_success are never run directly.`,
    };
  }

  async function executeBulk(kind: BulkActionKind) {
    setConfirmKind(null);
    setBulkBusy(true);
    setError(null);
    setMessage(null);
    setBulkProgress({ kind, completed: 0, total: 0, currentJobId: null });
    try {
      const summary: BulkSummary = await runBulkJobAction(jobs, kind, {
        actor: auth?.actor || "ui-operator",
        onProgress: setBulkProgress,
      });
      setMessage(
        `Bulk ${kind}: ${summary.succeeded}/${summary.total} succeeded` +
          (summary.failed ? `, ${summary.failed} failed` : ""),
      );
      if (summary.failed) {
        const details = summary.results
          .filter((r) => !r.ok)
          .map((r) => `#${r.jobId}: ${r.detail}`)
          .join("; ");
        setError(details || "Some bulk actions failed");
      }
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBulkBusy(false);
      setBulkProgress(null);
    }
  }

  const confirmMeta = confirmKind ? confirmCopy(confirmKind) : null;

  return (
    <div>
      <div className="page-header">
        <h1>Plan #{planId}</h1>
        <p>
          <Link href="/plans">← All plans</Link>
          {" · "}
          Per-job and bulk dry-run / approve / run with status + role gates.
          Approval is required before run.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />

      {plan ? (
        <div className="panel">
          <h2>Plan summary</h2>
          <div className="grid-stats">
            <div className="stat">
              <div className="label">status</div>
              <div className="value" style={{ fontSize: "1rem" }}>
                <StatusBadge status={plan.status} />
              </div>
            </div>
            <div className="stat">
              <div className="label">batch_id</div>
              <div className="value">{plan.batch_id}</div>
            </div>
            <div className="stat">
              <div className="label">jobs</div>
              <div className="value">{plan.job_count}</div>
            </div>
            <div className="stat">
              <div className="label">targets</div>
              <div className="value">{plan.target_count}</div>
            </div>
            <div className="stat">
              <div className="label">created_by</div>
              <div className="value" style={{ fontSize: "0.95rem" }}>
                {plan.created_by || "—"}
              </div>
            </div>
            <div className="stat">
              <div className="label">created_at</div>
              <div className="value" style={{ fontSize: "0.85rem" }}>
                {plan.created_at}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="panel">
        <h2>Job status counts</h2>
        <div className="grid-stats">
          {Object.keys(statusCounts).length === 0 ? (
            <p className="muted">No jobs yet.</p>
          ) : (
            Object.entries(statusCounts).map(([status, count]) => (
              <div className="stat" key={status}>
                <div className="label">{status}</div>
                <div className="value">{count}</div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Bulk actions</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Confirmation required. Only eligible statuses are called; failures do
          not stop the rest. Progress:{" "}
          {bulkProgress
            ? `${bulkProgress.completed}/${bulkProgress.total}`
            : "idle"}
        </p>
        {!canDryRun && !canApprove && !canRun ? (
          <div className="safety-note">
            Viewer role is read-only. Current role:{" "}
            <code>{auth?.role || "unknown"}</code>.
          </div>
        ) : null}
        <div className="btn-row">
          <button
            className="btn primary"
            type="button"
            data-testid="bulk-dry-run"
            disabled={
              bulkBusy || busyJobId != null || !canDryRun || waitingCount === 0
            }
            onClick={() => setConfirmKind("dry_run")}
          >
            Dry Run All Waiting Jobs ({waitingCount})
          </button>
          <button
            className="btn"
            type="button"
            data-testid="bulk-approve"
            disabled={
              bulkBusy ||
              busyJobId != null ||
              !canApprove ||
              dryRunSuccessCount === 0
            }
            onClick={() => setConfirmKind("approve")}
          >
            Approve All Dry Run Success Jobs ({dryRunSuccessCount})
          </button>
          <button
            className="btn"
            type="button"
            data-testid="bulk-run"
            disabled={
              bulkBusy || busyJobId != null || !canRun || approvedCount === 0
            }
            onClick={() => setConfirmKind("run")}
          >
            Run All Approved Jobs ({approvedCount})
          </button>
          <button
            className="btn"
            type="button"
            disabled={bulkBusy || busyJobId != null}
            onClick={() => void refresh()}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>Jobs</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Task Code</th>
                <th>Environment</th>
                <th>Ansible Group</th>
                <th>Criticality</th>
                <th>Targets</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const busy = busyJobId === j.id || bulkBusy;
                const showDryRun =
                  canDryRun && j.status === "waiting_dry_run";
                const showApprove =
                  canApprove && j.status === "dry_run_success";
                const showReject = canReject && REJECT_STATUSES.has(j.status);
                const showRun = canRun && j.status === "approved";
                const showResults =
                  j.status !== "waiting_dry_run" || Boolean(j.dry_run_status);
                return (
                  <tr key={j.id} data-testid={`plan-job-row-${j.id}`}>
                    <td>{j.id}</td>
                    <td className="mono">{j.task_code}</td>
                    <td>{j.environment || "—"}</td>
                    <td>{j.ansible_group || "—"}</td>
                    <td>{j.criticality || "—"}</td>
                    <td>{j.target_count}</td>
                    <td>
                      <StatusBadge status={j.status} />
                    </td>
                    <td>
                      <div className="btn-row" style={{ margin: 0 }}>
                        {showDryRun ? (
                          <button
                            className="btn primary"
                            type="button"
                            data-testid={`dry-run-${j.id}`}
                            disabled={busy}
                            onClick={() => void onDryRun(j)}
                          >
                            Dry Run
                          </button>
                        ) : null}
                        {showApprove ? (
                          <button
                            className="btn"
                            type="button"
                            data-testid={`approve-${j.id}`}
                            disabled={busy}
                            onClick={() => void onApprove(j)}
                          >
                            Approve
                          </button>
                        ) : null}
                        {showReject ? (
                          <button
                            className="btn danger"
                            type="button"
                            data-testid={`reject-${j.id}`}
                            disabled={busy}
                            onClick={() => void onReject(j)}
                          >
                            Reject
                          </button>
                        ) : null}
                        {showRun ? (
                          <button
                            className="btn"
                            type="button"
                            data-testid={`run-${j.id}`}
                            disabled={busy}
                            onClick={() => void onRun(j)}
                          >
                            Run
                          </button>
                        ) : null}
                        {showResults ? (
                          <Link
                            className="btn"
                            href={`/jobs/${j.id}`}
                            data-testid={`results-${j.id}`}
                          >
                            Results
                          </Link>
                        ) : (
                          <Link className="btn" href={`/jobs/${j.id}`}>
                            Results
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmModal
        open={confirmKind != null}
        title={confirmMeta?.title || ""}
        body={confirmMeta?.body || ""}
        confirmLabel="Confirm"
        danger={confirmKind === "run"}
        busy={bulkBusy}
        onCancel={() => setConfirmKind(null)}
        onConfirm={() => {
          if (confirmKind) void executeBulk(confirmKind);
        }}
      />
    </div>
  );
}
