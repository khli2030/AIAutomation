"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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
  const failed = r.status.toLowerCase().includes("fail");
  return (
    <>
      <tr className={failed ? "row-failed" : undefined}>
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
            {open ? "Hide" : "Expand"} stdout/stderr
          </button>
        </td>
      </tr>
      {open ? (
        <tr className={failed ? "row-failed" : undefined}>
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

export default function JobResultsPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = Number(params.jobId);
  const [job, setJob] = useState<ExecutionJob | null>(null);
  const [allResults, setAllResults] = useState<JobResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"all" | "dry_run" | "run">(
    "all",
  );
  const [statusFilter, setStatusFilter] = useState<
    "all" | "success" | "skipped" | "failed"
  >("all");
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    (async () => {
      try {
        const [j, results] = await Promise.all([
          getJob(jobId),
          getJobResults(jobId),
        ]);
        setJob(j);
        setAllResults(results.items);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : String(err));
      }
    })();
  }, [jobId]);

  const filtered = useMemo(() => {
    return allResults.filter((r) => {
      if (resultType !== "all" && r.result_type !== resultType) return false;
      const st = r.status.toLowerCase();
      if (statusFilter === "success" && !st.includes("success")) return false;
      if (statusFilter === "skipped" && !(r.skipped || st.includes("skip"))) {
        return false;
      }
      if (statusFilter === "failed" && !st.includes("fail")) return false;
      return true;
    });
  }, [allResults, resultType, statusFilter]);

  const counts = useMemo(() => {
    const base = { total: allResults.length, dry_run: 0, run: 0, success: 0, skipped: 0, failed: 0 };
    for (const r of allResults) {
      if (r.result_type === "dry_run") base.dry_run += 1;
      if (r.result_type === "run") base.run += 1;
      const st = r.status.toLowerCase();
      if (st.includes("success")) base.success += 1;
      if (r.skipped || st.includes("skip")) base.skipped += 1;
      if (st.includes("fail")) base.failed += 1;
    }
    return base;
  }, [allResults]);

  return (
    <div>
      <div className="page-header">
        <h1>Job #{jobId} results</h1>
        <p>
          <Link href="/jobs">← All jobs</Link>
          {" · "}
          <Link href={`/approvals?jobId=${jobId}`}>Approval flow</Link>
          {job?.plan_id ? (
            <>
              {" · "}
              <Link href={`/plans/${job.plan_id}`}>Plan #{job.plan_id}</Link>
            </>
          ) : null}
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

      <div className="panel">
        <h2>Counts</h2>
        <div className="grid-stats">
          {Object.entries(counts).map(([k, v]) => (
            <div className="stat" key={k}>
              <div className="label">{k}</div>
              <div className="value">{v}</div>
            </div>
          ))}
        </div>
        <div className="filters">
          <div className="field">
            <label htmlFor="result-type">result_type</label>
            <select
              id="result-type"
              data-testid="filter-result-type"
              value={resultType}
              onChange={(e) =>
                setResultType(e.target.value as "all" | "dry_run" | "run")
              }
            >
              <option value="all">all</option>
              <option value="dry_run">dry_run</option>
              <option value="run">run</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="result-status">status</label>
            <select
              id="result-status"
              data-testid="filter-result-status"
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(
                  e.target.value as "all" | "success" | "skipped" | "failed",
                )
              }
            >
              <option value="all">all</option>
              <option value="success">success</option>
              <option value="skipped">skipped</option>
              <option value="failed">failed</option>
            </select>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>
          Results ({filtered.length}
          {filtered.length !== allResults.length
            ? ` of ${allResults.length}`
            : ""}
          )
        </h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>device_name</th>
                <th>status</th>
                <th>changed</th>
                <th>skipped</th>
                <th>return_code</th>
                <th>result_type</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
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
    </div>
  );
}
