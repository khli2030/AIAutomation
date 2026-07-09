"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, getJob, getJobResults } from "@/lib/api";
import type { ExecutionJob, JobResult } from "@/types/api";
import { ErrorBox, StatusBadge } from "@/components/Ui";

function ResultRow({
  result: r,
  open,
  onToggle,
}: {
  result: JobResult;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr>
        <td>{r.device_name}</td>
        <td>
          <StatusBadge status={r.status} />
        </td>
        <td>{String(r.changed)}</td>
        <td>{String(r.skipped)}</td>
        <td>{r.return_code ?? "—"}</td>
        <td className="mono">{r.result_type}</td>
        <td>
          <button className="btn" type="button" onClick={onToggle}>
            stdout/stderr
          </button>
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={7}>
            <h3 style={{ fontSize: "0.8rem" }}>stdout</h3>
            <div className="pre-block mono">{r.stdout || "(empty)"}</div>
            <h3 style={{ fontSize: "0.8rem" }}>stderr</h3>
            <div className="pre-block mono">{r.stderr || "(empty)"}</div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ResultsTable({
  title,
  items,
}: {
  title: string;
  items: JobResult[];
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  return (
    <div className="panel">
      <h2>
        {title} ({items.length})
      </h2>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Host</th>
              <th>Status</th>
              <th>Changed</th>
              <th>Skipped</th>
              <th>RC</th>
              <th>Type</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <ResultRow
                key={r.id}
                result={r}
                open={openId === r.id}
                onToggle={() => setOpenId(openId === r.id ? null : r.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function JobResultsPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = Number(params.jobId);
  const [job, setJob] = useState<ExecutionJob | null>(null);
  const [dryRun, setDryRun] = useState<JobResult[]>([]);
  const [run, setRun] = useState<JobResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    (async () => {
      try {
        const [j, dry, apply] = await Promise.all([
          getJob(jobId),
          getJobResults(jobId, "dry_run"),
          getJobResults(jobId, "run"),
        ]);
        setJob(j);
        setDryRun(dry.items);
        setRun(apply.items);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : String(err));
      }
    })();
  }, [jobId]);

  return (
    <div>
      <div className="page-header">
        <h1>Job #{jobId} results</h1>
        <p>
          <Link href="/jobs">← All jobs</Link>
          {" · "}
          <Link href={`/approvals?jobId=${jobId}`}>Approval flow</Link>
        </p>
      </div>
      <ErrorBox message={error} />
      {job ? (
        <div className="panel">
          <p>
            <StatusBadge status={job.status} /> · {job.task_code} · targets=
            {job.target_count}
          </p>
        </div>
      ) : null}
      <ResultsTable title="Dry-run results (result_type=dry_run)" items={dryRun} />
      <ResultsTable title="Run results (result_type=run)" items={run} />
    </div>
  );
}
