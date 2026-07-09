"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  approveJob,
  dryRunJob,
  getJob,
  getJobResults,
  listJobs,
  rejectJob,
  runJob,
} from "@/lib/api";
import type { ExecutionJob, JobResult } from "@/types/api";
import { ErrorBox, StatusBadge, SuccessBox } from "@/components/Ui";

function ApprovalsInner() {
  const params = useSearchParams();
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [jobId, setJobId] = useState(params.get("jobId") || "");
  const [job, setJob] = useState<ExecutionJob | null>(null);
  const [dryResults, setDryResults] = useState<JobResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refreshJobs() {
    const res = await listJobs({ limit: 100 });
    setJobs(res.items);
  }

  async function loadJob(id: number) {
    const j = await getJob(id);
    setJob(j);
    try {
      const results = await getJobResults(id, "dry_run");
      setDryResults(results.items);
    } catch {
      setDryResults([]);
    }
  }

  useEffect(() => {
    void refreshJobs().catch((err) =>
      setError(err instanceof ApiError ? err.detail : String(err)),
    );
  }, []);

  useEffect(() => {
    if (!jobId) return;
    void loadJob(Number(jobId)).catch((err) =>
      setError(err instanceof ApiError ? err.detail : String(err)),
    );
  }, [jobId]);

  async function onDryRun() {
    if (!job) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const summary = await dryRunJob(job.id);
      setMessage(
        `Mock dry-run complete: status=${summary.status} mock_mode=${summary.mock_mode} hosts=${summary.hosts_total}`,
      );
      await loadJob(job.id);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onApprove() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await approveJob(job.id, "ui-operator");
      setMessage(`Job #${updated.id} approved.`);
      await loadJob(job.id);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await rejectJob(job.id, "ui-operator");
      setMessage(`Job #${updated.id} rejected.`);
      await loadJob(job.id);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const summary = await runJob(job.id);
      setMessage(
        `Mock run complete: status=${summary.status} mock_mode=${summary.mock_mode}`,
      );
      await loadJob(job.id);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  const canDryRun =
    job &&
    (job.status === "waiting_dry_run" || job.status === "dry_run_failed");
  const canApprove = job && job.status === "dry_run_success";
  const canReject =
    job &&
    ["waiting_dry_run", "dry_run_failed", "waiting_approval"].includes(
      job.status,
    );
  const canRun = job && job.status === "approved";

  return (
    <div>
      <div className="page-header">
        <h1>Job Approval</h1>
        <p>
          Mock dry-run → review results → approve only after{" "}
          <code>dry_run_success</code> → optional mock run. No real Ansible.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />
      <div className="panel">
        <div className="filters">
          <div className="field">
            <label>Job</label>
            <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
              <option value="">—</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  #{j.id} · {j.task_code} · {j.status}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
      {job ? (
        <div className="panel">
          <h2>
            Job #{job.id} · <StatusBadge status={job.status} />
          </h2>
          <p className="mono">
            {job.task_code} · env={job.environment || "—"} · targets=
            {job.target_count} · dry_run_status={job.dry_run_status || "—"}
          </p>
          <div className="safety-note">
            Buttons call MOCK_MODE API endpoints only. Approve is disabled until
            dry_run_success. There is no playbook editor.
          </div>
          <div className="btn-row">
            {canDryRun ? (
              <button
                className="btn primary"
                type="button"
                disabled={busy}
                onClick={() => void onDryRun()}
              >
                Run mock dry-run
              </button>
            ) : null}
            <button
              className="btn"
              type="button"
              disabled={busy || !canApprove}
              onClick={() => void onApprove()}
            >
              Approve
            </button>
            <button
              className="btn danger"
              type="button"
              disabled={busy || !canReject}
              onClick={() => void onReject()}
            >
              Reject
            </button>
            <button
              className="btn"
              type="button"
              disabled={busy || !canRun}
              onClick={() => void onRun()}
              title="Mock apply only after approval"
            >
              Run mock execution
            </button>
            <Link className="btn" href={`/jobs/${job.id}`}>
              View all results
            </Link>
          </div>
          <h3 style={{ fontSize: "0.95rem" }}>
            Dry-run results (result_type=dry_run)
          </h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Host</th>
                  <th>Status</th>
                  <th>Changed</th>
                  <th>Skipped</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {dryResults.map((r) => (
                  <tr key={r.id}>
                    <td>{r.device_name}</td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td>{String(r.changed)}</td>
                    <td>{String(r.skipped)}</td>
                    <td className="mono">{r.result_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <ApprovalsInner />
    </Suspense>
  );
}
