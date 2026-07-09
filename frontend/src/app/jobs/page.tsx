"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, listJobs } from "@/lib/api";
import type { ExecutionJob } from "@/types/api";
import { ErrorBox, StatusBadge } from "@/components/Ui";

export default function JobsIndexPage() {
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listJobs({ limit: 100, status: status || undefined })
      .then((res) => setJobs(res.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : String(err)),
      );
  }, [status]);

  return (
    <div>
      <div className="page-header">
        <h1>Job Results</h1>
        <p>
          Open a job to inspect dry_run vs run results separately via{" "}
          <code>result_type</code>.
        </p>
      </div>
      <ErrorBox message={error} />
      <div className="panel">
        <div className="filters">
          <div className="field">
            <label>Status filter</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">(any)</option>
              <option value="waiting_dry_run">waiting_dry_run</option>
              <option value="dry_run_success">dry_run_success</option>
              <option value="dry_run_failed">dry_run_failed</option>
              <option value="approved">approved</option>
              <option value="success">success</option>
              <option value="failed">failed</option>
              <option value="partially_failed">partially_failed</option>
              <option value="rejected">rejected</option>
            </select>
          </div>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Plan</th>
                <th>Task</th>
                <th>Status</th>
                <th>Targets</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>{j.id}</td>
                  <td>
                    <Link href={`/plans/${j.plan_id}`}>{j.plan_id}</Link>
                  </td>
                  <td className="mono">{j.task_code}</td>
                  <td>
                    <StatusBadge status={j.status} />
                  </td>
                  <td>{j.target_count}</td>
                  <td>
                    <Link href={`/jobs/${j.id}`}>Results</Link>
                    {" · "}
                    <Link href={`/approvals?jobId=${j.id}`}>Approval</Link>
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
