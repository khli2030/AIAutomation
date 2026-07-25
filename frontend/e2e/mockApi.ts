/**
 * Stateful FastAPI mock for Phase 7.5 / 9B Playwright UI E2E.
 * Simulates MOCK_MODE backend responses only — never Ansible/SSH/subprocess.
 */

import type { Page, Route } from "@playwright/test";

type JobStatus =
  | "waiting_dry_run"
  | "dry_run_success"
  | "dry_run_failed"
  | "waiting_approval"
  | "approved"
  | "success"
  | "failed"
  | "partially_failed"
  | "rejected";

export type MockJob = {
  id: number;
  status: JobStatus;
  dryRunResults: boolean;
  runResults: boolean;
  task_code: string;
  environment: string;
  criticality: string;
  ansible_group: string;
  target_count: number;
};

export type MockApiState = {
  batchId: number;
  planId: number;
  batchStatus: string;
  validated: boolean;
  jobs: MockJob[];
  /** Role returned by GET /auth/me (default admin for full UI access). */
  role: "viewer" | "operator" | "approver" | "admin";
  /** Track dry-run/approve/run POST calls for assertions. */
  calls: { dryRun: number[]; approve: number[]; run: number[]; reject: number[] };
};

export type InstallMockOptions = {
  role?: MockApiState["role"];
  jobCount?: number;
};

const now = () => new Date().toISOString();

function makeJobs(count: number): MockJob[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    status: "waiting_dry_run" as const,
    dryRunResults: false,
    runResults: false,
    task_code: "SSH_DISABLE_ROOT_LOGIN",
    environment: "test",
    criticality: "High",
    ansible_group: "linux_test",
    target_count: 2,
  }));
}

export function createInitialState(
  options: InstallMockOptions = {},
): MockApiState {
  const jobCount = options.jobCount ?? 1;
  return {
    batchId: 1,
    planId: 1,
    batchStatus: "parsed",
    validated: false,
    jobs: makeJobs(jobCount),
    role: options.role ?? "admin",
    calls: { dryRun: [], approve: [], run: [], reject: [] },
  };
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function permissionsFor(role: MockApiState["role"]) {
  const isAdmin = role === "admin";
  const isOperator = role === "operator" || isAdmin;
  const isApprover = role === "approver" || isAdmin;
  return {
    can_upload: isOperator,
    can_validate: isOperator,
    can_generate_plan: isOperator,
    can_dry_run: isOperator,
    can_run: isOperator,
    can_approve_job: isApprover,
    can_reject_job: isApprover,
    can_approve_suggestion: isApprover,
    can_reject_suggestion: isApprover,
    can_convert_catalog: isAdmin,
    can_ai_analyze: isOperator,
  };
}

function batch(state: MockApiState) {
  return {
    id: state.batchId,
    original_filename: "e2e_compliance.xlsx",
    stored_path: `/tmp/uploads/${state.batchId}/e2e_compliance.xlsx`,
    status: state.batchStatus,
    total_records: 2,
    valid_records: 2,
    invalid_records: 0,
    total_rows: 2,
    processed_rows: 2,
    uploaded_by: "ui-e2e",
    error_message: null,
    created_at: now(),
    updated_at: now(),
  };
}

function records(state: MockApiState) {
  const status = state.validated ? "READY_FOR_PLAN" : null;
  return {
    batch_id: state.batchId,
    total: 2,
    limit: 200,
    offset: 0,
    items: [
      {
        id: 11,
        batch_id: state.batchId,
        row_number: 2,
        device_name: "e2e-linux-01",
        overall_status: "Failed",
        criticality: "High",
        qualys_control_id: "CTRL-ROOT-01",
        source_check_id: "SRC-1",
        control_description: "SSH PermitRootLogin must be no",
        remediation: "Set PermitRootLogin no (never executed)",
        expected_configuration: "PermitRootLogin no",
        task_code: state.validated ? "SSH_DISABLE_ROOT_LOGIN" : null,
        validation_status: status,
        validation_error: null,
        record_hash: "abc",
        created_at: now(),
      },
      {
        id: 12,
        batch_id: state.batchId,
        row_number: 3,
        device_name: "e2e-linux-02",
        overall_status: "Failed",
        criticality: "High",
        qualys_control_id: "CTRL-ROOT-02",
        source_check_id: "SRC-2",
        control_description: "SSH PermitRootLogin must be no",
        remediation: "Set PermitRootLogin no (never executed)",
        expected_configuration: "PermitRootLogin no",
        task_code: state.validated ? "SSH_DISABLE_ROOT_LOGIN" : null,
        validation_status: status,
        validation_error: null,
        record_hash: "def",
        created_at: now(),
      },
    ],
  };
}

function jobPayload(j: MockJob, planId: number) {
  return {
    id: j.id,
    plan_id: planId,
    task_code: j.task_code,
    environment: j.environment,
    criticality: j.criticality,
    ansible_group: j.ansible_group,
    status: j.status,
    dry_run_status: j.dryRunResults
      ? "dry_run_success"
      : j.status === "dry_run_failed"
        ? "dry_run_failed"
        : null,
    approved_by:
      j.status === "approved" || j.status === "success" ? "ui-e2e" : null,
    approved_at:
      j.status === "approved" || j.status === "success" ? now() : null,
    started_at: j.dryRunResults || j.status === "dry_run_failed" ? now() : null,
    finished_at: j.runResults ? now() : null,
    target_count: j.target_count,
  };
}

function plan(state: MockApiState) {
  const targetCount = state.jobs.reduce((n, j) => n + j.target_count, 0);
  return {
    id: state.planId,
    batch_id: state.batchId,
    status: "generated",
    created_by: "ui-e2e",
    created_at: now(),
    job_count: state.jobs.length,
    target_count: targetCount,
    skipped_records: 0,
    ready_for_plan_records: 2,
    skipped_missing_catalog: 0,
    skipped_disabled_catalog: 0,
    skipped_missing_asset: 0,
    skipped_missing_asset_metadata: 0,
    skipped_excluded_status: 0,
  };
}

function dryRunItems(j: MockJob) {
  if (!j.dryRunResults && j.status !== "dry_run_failed") return [];
  const failed = j.status === "dry_run_failed";
  return [
    {
      id: 100 + j.id * 10,
      job_id: j.id,
      result_type: "dry_run",
      device_name: "e2e-linux-01",
      status: failed ? "failed" : "success",
      changed: false,
      skipped: false,
      stdout: failed ? "" : "MOCK dry_run ok",
      stderr: failed ? "MOCK dry_run failed: host unreachable" : "",
      return_code: failed ? 1 : 0,
      created_at: now(),
    },
    {
      id: 101 + j.id * 10,
      job_id: j.id,
      result_type: "dry_run",
      device_name: "e2e-linux-02",
      status: failed ? "failed" : "success",
      changed: false,
      skipped: false,
      stdout: failed ? "" : "MOCK dry_run ok",
      stderr: failed ? "MOCK dry_run failed: check mode error" : "",
      return_code: failed ? 1 : 0,
      created_at: now(),
    },
  ];
}

function runItems(j: MockJob) {
  if (!j.runResults) return [];
  return [
    {
      id: 200 + j.id * 10,
      job_id: j.id,
      result_type: "run",
      device_name: "e2e-linux-01",
      status: "success",
      changed: true,
      skipped: false,
      stdout: "MOCK apply changed",
      stderr: "",
      return_code: 0,
      created_at: now(),
    },
    {
      id: 201 + j.id * 10,
      job_id: j.id,
      result_type: "run",
      device_name: "e2e-linux-02",
      status: "success",
      changed: true,
      skipped: false,
      stdout: "MOCK apply changed",
      stderr: "",
      return_code: 0,
      created_at: now(),
    },
  ];
}

function findJob(state: MockApiState, jobId: number): MockJob | undefined {
  return state.jobs.find((j) => j.id === jobId);
}

function parseJobId(path: string): number | null {
  const m = path.match(/^\/execution-jobs\/(\d+)(?:\/|$)/);
  return m ? Number(m[1]) : null;
}

export async function installMockApi(
  page: Page,
  state: MockApiState,
  options: InstallMockOptions = {},
) {
  if (options.role) state.role = options.role;
  if (options.jobCount && options.jobCount !== state.jobs.length) {
    state.jobs = makeJobs(options.jobCount);
  }

  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname.replace(/\/$/, "") || "/";

    if (method === "GET" && path === "/") {
      return json(route, 200, {
        app: "compliance-remediation-platform",
        env: "test",
        docs: "/docs",
        phase: "9B",
        auth: "role token required",
        mock_mode: "true",
        role: state.role,
      });
    }

    if (method === "GET" && path === "/auth/me") {
      const perms = permissionsFor(state.role);
      return json(route, 200, {
        role: state.role,
        actor: `ui-e2e-${state.role}`,
        token_name: `${state.role.toUpperCase()}_TOKEN`,
        mock_mode: true,
        mvp_auth_warning: "MVP token auth only",
        ...perms,
      });
    }

    if (method === "GET" && path === "/health") {
      return json(route, 200, { status: "ok" });
    }

    if (method === "GET" && path === "/dashboard/summary") {
      const byStatus: Record<string, number> = {};
      for (const j of state.jobs) {
        byStatus[j.status] = (byStatus[j.status] || 0) + 1;
      }
      return json(route, 200, {
        mock_mode: true,
        import_batches_total: 1,
        import_batches_by_status: { parsed: 1 },
        records_total: 2,
        records_by_validation_status: state.validated
          ? { READY_FOR_PLAN: 2 }
          : {},
        jobs_total: state.validated ? state.jobs.length : 0,
        jobs_by_status: state.validated ? byStatus : {},
        plans_total: state.validated ? 1 : 0,
        suggestions_total: 1,
        suggestions_by_status: { draft: 1 },
        latest_imports: [batch(state)],
        latest_jobs: state.validated
          ? state.jobs.map((j) => jobPayload(j, state.planId))
          : [],
        generated_at: now(),
      });
    }

    if (method === "POST" && path === "/imports/upload") {
      state.batchStatus = "parsed";
      return json(route, 202, {
        batch: batch(state),
        message: "Upload accepted; parse job queued.",
      });
    }

    if (method === "GET" && path === "/imports") {
      return json(route, 200, {
        total: 1,
        limit: 100,
        offset: 0,
        items: [batch(state)],
      });
    }

    if (method === "GET" && path === `/imports/${state.batchId}`) {
      return json(route, 200, batch(state));
    }

    if (method === "GET" && path === `/imports/${state.batchId}/records`) {
      const vs = url.searchParams.get("validation_status");
      const payload = records(state);
      if (vs) {
        payload.items = payload.items.filter(
          (r) => r.validation_status === vs,
        );
        payload.total = payload.items.length;
      }
      return json(route, 200, payload);
    }

    if (method === "POST" && path === `/imports/${state.batchId}/validate`) {
      state.validated = true;
      return json(route, 200, {
        batch_id: state.batchId,
        total_records: 2,
        ready_for_plan: 2,
        needs_review: 0,
        asset_not_found: 0,
        already_compliant: 0,
        duplicate: 0,
        invalid_record: 0,
        unsupported_control: 0,
      });
    }

    if (
      method === "POST" &&
      path === `/imports/${state.batchId}/generate-plan`
    ) {
      for (const j of state.jobs) {
        j.status = "waiting_dry_run";
        j.dryRunResults = false;
        j.runResults = false;
      }
      return json(route, 200, {
        plan: plan(state),
        message:
          "Execution plan generated. Jobs are waiting_dry_run; no Ansible or mock execution was invoked.",
      });
    }

    if (
      method === "POST" &&
      path === `/imports/${state.batchId}/ai-analyze-needs-review`
    ) {
      return json(route, 200, {
        batch_id: state.batchId,
        needs_review_records: 0,
        analyzed: 0,
        suggestions_created: 0,
        skipped_non_needs_review: 2,
        message: "AI analysis complete; draft suggestions only (never executed).",
      });
    }

    if (method === "GET" && path === "/execution-plans") {
      return json(route, 200, {
        total: state.validated ? 1 : 0,
        limit: 100,
        offset: 0,
        items: state.validated ? [plan(state)] : [],
      });
    }

    if (method === "GET" && path === `/execution-plans/${state.planId}`) {
      return json(route, 200, plan(state));
    }

    if (
      method === "GET" &&
      path === `/execution-plans/${state.planId}/jobs`
    ) {
      return json(route, 200, {
        plan_id: state.planId,
        total: state.jobs.length,
        items: state.jobs.map((j) => jobPayload(j, state.planId)),
      });
    }

    if (method === "GET" && path === "/execution-jobs") {
      const status = url.searchParams.get("status");
      let items = state.jobs.map((j) => jobPayload(j, state.planId));
      if (status) items = items.filter((j) => j.status === status);
      return json(route, 200, {
        total: items.length,
        limit: 100,
        offset: 0,
        items,
      });
    }

    const jobId = parseJobId(path);
    if (jobId != null) {
      const j = findJob(state, jobId);
      if (!j) {
        return json(route, 404, { detail: `Job ${jobId} not found` });
      }

      if (method === "GET" && path === `/execution-jobs/${jobId}`) {
        return json(route, 200, jobPayload(j, state.planId));
      }

      if (method === "POST" && path === `/execution-jobs/${jobId}/dry-run`) {
        state.calls.dryRun.push(jobId);
        if (j.status !== "waiting_dry_run" && j.status !== "dry_run_failed") {
          return json(route, 400, {
            detail: `Dry-run not allowed for status=${j.status}`,
          });
        }
        j.status = "dry_run_success";
        j.dryRunResults = true;
        return json(route, 200, {
          job_id: jobId,
          mode: "dry_run",
          mock_mode: true,
          status: "dry_run_success",
          dry_run_status: "dry_run_success",
          hosts_total: 2,
          hosts_success: 2,
          hosts_failed: 0,
          hosts_changed: 0,
          hosts_skipped: 0,
          message: "Mock execution only — no ansible-runner, subprocess, or SSH.",
        });
      }

      if (method === "POST" && path === `/execution-jobs/${jobId}/approve`) {
        state.calls.approve.push(jobId);
        if (j.status !== "dry_run_success") {
          return json(route, 400, {
            detail: "Approve allowed only when status=dry_run_success",
          });
        }
        j.status = "approved";
        return json(route, 200, jobPayload(j, state.planId));
      }

      if (method === "POST" && path === `/execution-jobs/${jobId}/reject`) {
        state.calls.reject.push(jobId);
        j.status = "rejected";
        return json(route, 200, jobPayload(j, state.planId));
      }

      if (method === "POST" && path === `/execution-jobs/${jobId}/run`) {
        state.calls.run.push(jobId);
        if (j.status !== "approved") {
          return json(route, 400, {
            detail: "Run allowed only when job status=approved",
          });
        }
        j.status = "success";
        j.runResults = true;
        return json(route, 200, {
          job_id: jobId,
          mode: "apply",
          mock_mode: true,
          status: "success",
          dry_run_status: "dry_run_success",
          hosts_total: 2,
          hosts_success: 2,
          hosts_failed: 0,
          hosts_changed: 2,
          hosts_skipped: 0,
          message: "Mock execution only — no ansible-runner, subprocess, or SSH.",
        });
      }

      if (method === "GET" && path === `/execution-jobs/${jobId}/results`) {
        const rt = url.searchParams.get("result_type");
        let items = [...dryRunItems(j), ...runItems(j)];
        if (rt === "dry_run") items = dryRunItems(j);
        if (rt === "run") items = runItems(j);
        return json(route, 200, {
          job_id: jobId,
          job_status: j.status,
          dry_run_status: j.dryRunResults ? "dry_run_success" : null,
          result_type_filter: rt,
          total: items.length,
          items,
        });
      }
    }

    if (method === "GET" && path === "/ai-suggestions") {
      return json(route, 200, {
        total: 1,
        limit: 100,
        offset: 0,
        items: [
          {
            id: 501,
            raw_record_id: 99,
            control_description: "Unknown control",
            remediation: "example",
            expected_configuration: "x",
            suggested_task_code: "NEEDS_REVIEW_CUSTOM",
            confidence: 0.4,
            risk_level: "medium",
            generated_playbook:
              "---\n# AI DRAFT — NOT EXECUTABLE\n- hosts: all\n  tasks: []\n",
            safety_warnings: "Never execute AI drafts without human review.",
            status: "draft",
            reviewed_by: null,
            reviewed_at: null,
            created_at: now(),
          },
        ],
      });
    }

    if (method === "POST" && path.startsWith("/ai-suggestions/")) {
      return json(route, 200, {
        id: 501,
        raw_record_id: 99,
        suggested_task_code: "NEEDS_REVIEW_CUSTOM",
        generated_playbook: "---\n# AI DRAFT — NOT EXECUTABLE\n",
        status: path.endsWith("/approve")
          ? "approved"
          : path.endsWith("/reject")
            ? "rejected"
            : "converted",
        created_at: now(),
      });
    }

    return json(route, 404, {
      detail: `Mock API has no handler for ${method} ${path}`,
    });
  });
}
