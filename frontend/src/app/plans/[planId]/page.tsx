"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, getPlan, listPlanJobs } from "@/lib/api";
import type { ExecutionJob, ExecutionPlan } from "@/types/api";
import { ErrorBox, StatusBadge } from "@/components/Ui";

export default function PlanDetailPage() {
  const params = useParams<{ planId: string }>();
  const planId = Number(params.planId);
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!planId) return;
    (async () => {
      try {
        const [p, j] = await Promise.all([getPlan(planId), listPlanJobs(planId)]);
        setPlan(p);
        setJobs(j.items);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : String(err));
      }
    })();
  }, [planId]);

  return (
    <div>
      <div className="page-header">
        <h1>Plan #{planId}</h1>
        <p>
          <Link href="/plans">← All plans</Link>
        </p>
      </div>
      <ErrorBox message={error} />
      {plan ? (
        <div className="panel">
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
          </div>
        </div>
      ) : null}
      <div className="panel">
        <h2>Jobs</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Task</th>
                <th>Env</th>
                <th>Status</th>
                <th>Targets</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>{j.id}</td>
                  <td className="mono">{j.task_code}</td>
                  <td>{j.environment || "—"}</td>
                  <td>
                    <StatusBadge status={j.status} />
                  </td>
                  <td>{j.target_count}</td>
                  <td>
                    <Link href={`/approvals?jobId=${j.id}`}>Approve flow</Link>
                    {" · "}
                    <Link href={`/jobs/${j.id}`}>Results</Link>
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
