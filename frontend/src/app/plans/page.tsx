"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, listPlans } from "@/lib/api";
import type { ExecutionPlan } from "@/types/api";
import { ErrorBox, StatusBadge } from "@/components/Ui";

export default function PlansPage() {
  const [plans, setPlans] = useState<ExecutionPlan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const res = await listPlans(100, 0);
      setPlans(res.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Execution Plans</h1>
        <p>
          Plans generated from READY_FOR_PLAN records. Open a plan to dry-run,
          approve, and run jobs from the UI (no curl required).
        </p>
      </div>
      <ErrorBox message={error} />
      <div className="panel">
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Refresh
          </button>
        </div>
        <h2>Plans ({plans.length})</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Plan ID</th>
                <th>Batch ID</th>
                <th>Status</th>
                <th>Job count</th>
                <th>Target count</th>
                <th>Created by</th>
                <th>Created at</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.id} data-testid={`plan-row-${p.id}`}>
                  <td>
                    <Link href={`/plans/${p.id}`}>{p.id}</Link>
                  </td>
                  <td>{p.batch_id}</td>
                  <td>
                    <StatusBadge status={p.status} />
                  </td>
                  <td>{p.job_count}</td>
                  <td>{p.target_count}</td>
                  <td>{p.created_by || "—"}</td>
                  <td className="mono" style={{ fontSize: "0.8rem" }}>
                    {p.created_at}
                  </td>
                  <td>
                    <Link
                      className="btn"
                      href={`/plans/${p.id}`}
                      data-testid={`view-jobs-${p.id}`}
                    >
                      View Jobs
                    </Link>
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
