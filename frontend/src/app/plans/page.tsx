"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, listPlanJobs, listPlans } from "@/lib/api";
import type { ExecutionJob, ExecutionPlan } from "@/types/api";
import { ErrorBox, StatusBadge } from "@/components/Ui";

export default function PlansPage() {
  const [plans, setPlans] = useState<ExecutionPlan[]>([]);
  const [selected, setSelected] = useState<ExecutionPlan | null>(null);
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listPlans(100, 0)
      .then((res) => setPlans(res.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : String(err)),
      );
  }, []);

  async function openPlan(plan: ExecutionPlan) {
    setSelected(plan);
    setError(null);
    try {
      const res = await listPlanJobs(plan.id);
      setJobs(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Execution Plans</h1>
        <p>
          Plans and jobs created from READY_FOR_PLAN records. Jobs start in{" "}
          <code>waiting_dry_run</code> — use Job Approval for mock dry-run.
        </p>
      </div>
      <ErrorBox message={error} />
      <div className="two-col">
        <div className="panel">
          <h2>Plans ({plans.length})</h2>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Batch</th>
                  <th>Status</th>
                  <th>Jobs</th>
                  <th>Targets</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => void openPlan(p)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <Link href={`/plans/${p.id}`}>{p.id}</Link>
                    </td>
                    <td>{p.batch_id}</td>
                    <td>
                      <StatusBadge status={p.status} />
                    </td>
                    <td>{p.job_count}</td>
                    <td>{p.target_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <h2>
            Jobs
            {selected ? ` for plan #${selected.id}` : ""}
          </h2>
          {!selected ? (
            <p className="muted">Select a plan.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Task</th>
                    <th>Status</th>
                    <th>Targets</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.id}>
                      <td>
                        <Link href={`/approvals?jobId=${j.id}`}>{j.id}</Link>
                      </td>
                      <td className="mono">{j.task_code}</td>
                      <td>
                        <StatusBadge status={j.status} />
                      </td>
                      <td>{j.target_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
