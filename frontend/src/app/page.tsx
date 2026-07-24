"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, fetchDashboard } from "@/lib/api";
import type { DashboardSummary } from "@/types/api";
import { CounterMap, ErrorBox, StatusBadge } from "@/components/Ui";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const summary = await fetchDashboard();
        if (!cancelled) {
          setData(summary);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.detail : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>
          Import, record, and job counters from the backend. Execution stays on
          the MOCK_MODE path only — no real Ansible from this UI.
        </p>
      </div>
      <ErrorBox message={error} />
      {!data && !error ? <p className="muted">Loading summary…</p> : null}
      {data ? (
        <>
          <div className="grid-stats">
            <div className="stat">
              <div className="label">Import batches</div>
              <div className="value">{data.import_batches_total}</div>
            </div>
            <div className="stat">
              <div className="label">Records</div>
              <div className="value">{data.records_total}</div>
            </div>
            <div className="stat">
              <div className="label">Plans</div>
              <div className="value">{data.plans_total}</div>
            </div>
            <div className="stat">
              <div className="label">Jobs</div>
              <div className="value">{data.jobs_total}</div>
            </div>
            <div className="stat">
              <div className="label">AI suggestions</div>
              <div className="value">{data.suggestions_total}</div>
            </div>
            <div className="stat">
              <div className="label">MOCK_MODE</div>
              <div className="value">{data.mock_mode ? "true" : "false"}</div>
            </div>
          </div>

          <CounterMap
            title="Import batch status"
            data={data.import_batches_by_status}
          />
          <CounterMap
            title="Record validation status"
            data={data.records_by_validation_status}
          />
          <CounterMap title="Job status" data={data.jobs_by_status} />

          <div className="two-col">
            <div className="panel">
              <h2>Latest imports</h2>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>File</th>
                      <th>Status</th>
                      <th>Records</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.latest_imports.map((b) => (
                      <tr key={b.id}>
                        <td>
                          <Link href={`/imports?batchId=${b.id}`}>{b.id}</Link>
                        </td>
                        <td>{b.original_filename}</td>
                        <td>
                          <StatusBadge status={b.status} />
                        </td>
                        <td>{b.total_records}</td>
                        <td>
                          <Link
                            className="btn"
                            href={`/imports?batchId=${b.id}`}
                          >
                            Validate / Plan
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="panel">
              <h2>Latest jobs</h2>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Task</th>
                      <th>Status</th>
                      <th>Targets</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.latest_jobs.map((j) => (
                      <tr key={j.id}>
                        <td>
                          <Link href={`/jobs/${j.id}`}>{j.id}</Link>
                        </td>
                        <td className="mono">{j.task_code}</td>
                        <td>
                          <StatusBadge status={j.status} />
                        </td>
                        <td>{j.target_count}</td>
                        <td>
                          <Link className="btn" href={`/plans/${j.plan_id}`}>
                            Plan
                          </Link>{" "}
                          <Link className="btn" href={`/jobs/${j.id}`}>
                            Results
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
