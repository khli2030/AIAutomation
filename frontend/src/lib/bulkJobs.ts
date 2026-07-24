/**
 * Safe sequential bulk job actions for Phase 9B.
 * Only operates on jobs already filtered to the correct status.
 * Continues after individual failures and returns a summary.
 */

import {
  ApiError,
  approveJob,
  dryRunJob,
  runJob,
} from "@/lib/api";
import type { ExecutionJob, JobExecutionSummary } from "@/types/api";

export type BulkActionKind = "dry_run" | "approve" | "run";

export type BulkItemResult = {
  jobId: number;
  ok: boolean;
  detail: string;
};

export type BulkSummary = {
  kind: BulkActionKind;
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  results: BulkItemResult[];
};

export type BulkProgress = {
  kind: BulkActionKind;
  completed: number;
  total: number;
  currentJobId: number | null;
};

const DRY_RUN_STATUSES = new Set(["waiting_dry_run"]);
const APPROVE_STATUSES = new Set(["dry_run_success"]);
const RUN_STATUSES = new Set(["approved"]);

export function filterJobsForBulk(
  jobs: ExecutionJob[],
  kind: BulkActionKind,
): ExecutionJob[] {
  if (kind === "dry_run") {
    return jobs.filter((j) => DRY_RUN_STATUSES.has(j.status));
  }
  if (kind === "approve") {
    return jobs.filter((j) => APPROVE_STATUSES.has(j.status));
  }
  return jobs.filter((j) => RUN_STATUSES.has(j.status));
}

export async function runBulkJobAction(
  jobs: ExecutionJob[],
  kind: BulkActionKind,
  opts: {
    actor?: string;
    onProgress?: (progress: BulkProgress) => void;
  } = {},
): Promise<BulkSummary> {
  const targets = filterJobsForBulk(jobs, kind);
  const results: BulkItemResult[] = [];
  let completed = 0;

  for (const job of targets) {
    opts.onProgress?.({
      kind,
      completed,
      total: targets.length,
      currentJobId: job.id,
    });
    try {
      if (kind === "dry_run") {
        const summary: JobExecutionSummary = await dryRunJob(job.id);
        results.push({
          jobId: job.id,
          ok: true,
          detail: summary.message || summary.status,
        });
      } else if (kind === "approve") {
        const updated = await approveJob(job.id, opts.actor);
        results.push({
          jobId: job.id,
          ok: true,
          detail: updated.status,
        });
      } else {
        const summary = await runJob(job.id);
        results.push({
          jobId: job.id,
          ok: true,
          detail: summary.message || summary.status,
        });
      }
    } catch (err) {
      results.push({
        jobId: job.id,
        ok: false,
        detail: err instanceof ApiError ? err.detail : String(err),
      });
    }
    completed += 1;
    opts.onProgress?.({
      kind,
      completed,
      total: targets.length,
      currentJobId: job.id,
    });
  }

  return {
    kind,
    total: targets.length,
    completed,
    succeeded: results.filter((r) => r.ok).length,
    failed: results.filter((r) => !r.ok).length,
    results,
  };
}
