/**
 * Stateful FastAPI mock for Phase 7.5 Playwright UI E2E.
 * Simulates MOCK_MODE backend responses only — never Ansible/SSH/subprocess.
 */

import type { Page, Route } from "@playwright/test";

type JobStatus =
  | "waiting_dry_run"
  | "dry_run_success"
  | "approved"
  | "success"
  | "failed"
  | "partially_failed";

export type MockApiState = {
  batchId: number;
  planId: number;
  jobId: number;
  batchStatus: string;
  validated: boolean;
  jobStatus: JobStatus;
  dryRunResults: boolean;
  runResults: boolean;
};

const now = () => new Date().toISOString();

export function createInitialState(): MockApiState {
  return {
    batchId: 1,
    planId: 1,
    jobId: 1,
    batchStatus: "parsed",
    validated: false,
    jobStatus: "waiting_dry_run",
    dryRunResults: false,
    runResults: false,
  };
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
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

function job(state: MockApiState) {
  return {
    id: state.jobId,
    plan_id: state.planId,
    task_code: "SSH_DISABLE_ROOT_LOGIN",
    environment: "test",
    criticality: "High",
    ansible_group: "linux_test",
    status: state.jobStatus,
    dry_run_status:
      state.jobStatus === "waiting_dry_run" ? null : "dry_run_success",
    approved_by: state.jobStatus === "approved" || state.jobStatus === "success"
      ? "ui-e2e"
      : null,
    approved_at:
      state.jobStatus === "approved" || state.jobStatus === "success"
        ? now()
        : null,
    started_at: state.dryRunResults ? now() : null,
    finished_at: state.runResults ? now() : null,
    target_count: 2,
  };
}

function plan(state: MockApiState) {
  return {
    id: state.planId,
    batch_id: state.batchId,
    status: "draft",
    created_by: "ui-e2e",
    created_at: now(),
    job_count: 1,
    target_count: 2,
    skipped_records: 0,
    ready_for_plan_records: 2,
    skipped_missing_catalog: 0,
    skipped_disabled_catalog: 0,
    skipped_missing_asset: 0,
    skipped_missing_asset_metadata: 0,
    skipped_excluded_status: 0,
  };
}

function dryRunItems(state: MockApiState) {
  if (!state.dryRunResults) return [];
  return [
    {
      id: 101,
      job_id: state.jobId,
      result_type: "dry_run",
      device_name: "e2e-linux-01",
      status: "success",
      changed: false,
      skipped: false,
      stdout: "MOCK dry_run ok",
      stderr: "",
      return_code: 0,
      created_at: now(),
    },
    {
      id: 102,
      job_id: state.jobId,
      result_type: "dry_run",
      device_name: "e2e-linux-02",
      status: "success",
      changed: false,
      skipped: false,
      stdout: "MOCK dry_run ok",
      stderr: "",
      return_code: 0,
      created_at: now(),
    },
  ];
}

function runItems(state: MockApiState) {
  if (!state.runResults) return [];
  return [
    {
      id: 201,
      job_id: state.jobId,
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
      id: 202,
      job_id: state.jobId,
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

export async function installMockApi(page: Page, state: MockApiState) {
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname.replace(/\/$/, "") || "/";

    // Public-ish / root meta
    if (method === "GET" && path === "/") {
      return json(route, 200, {
        app: "compliance-remediation-platform",
        env: "test",
        docs: "/docs",
        phase: "7",
        auth: "ADMIN_TOKEN required",
        mock_mode: "true",
      });
    }

    if (method === "GET" && path === "/health") {
      return json(route, 200, { status: "ok" });
    }

    if (method === "GET" && path === "/dashboard/summary") {
      return json(route, 200, {
        mock_mode: true,
        import_batches_total: 1,
        import_batches_by_status: { parsed: 1 },
        records_total: 2,
        records_by_validation_status: state.validated
          ? { READY_FOR_PLAN: 2 }
          : {},
        jobs_total: state.validated ? 1 : 0,
        jobs_by_status: state.validated ? { [state.jobStatus]: 1 } : {},
        plans_total: state.validated ? 1 : 0,
        suggestions_total: 1,
        suggestions_by_status: { draft: 1 },
        latest_imports: [batch(state)],
        latest_jobs: state.validated ? [job(state)] : [],
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
      state.jobStatus = "waiting_dry_run";
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
        total: 1,
        items: [job(state)],
      });
    }

    if (method === "GET" && path === "/execution-jobs") {
      return json(route, 200, {
        total: 1,
        limit: 100,
        offset: 0,
        items: [job(state)],
      });
    }

    if (method === "GET" && path === `/execution-jobs/${state.jobId}`) {
      return json(route, 200, job(state));
    }

    if (
      method === "POST" &&
      path === `/execution-jobs/${state.jobId}/dry-run`
    ) {
      state.jobStatus = "dry_run_success";
      state.dryRunResults = true;
      return json(route, 200, {
        job_id: state.jobId,
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

    if (
      method === "POST" &&
      path === `/execution-jobs/${state.jobId}/approve`
    ) {
      if (state.jobStatus !== "dry_run_success") {
        return json(route, 400, {
          detail: "Approve allowed only when status=dry_run_success",
        });
      }
      state.jobStatus = "approved";
      return json(route, 200, job(state));
    }

    if (
      method === "POST" &&
      path === `/execution-jobs/${state.jobId}/reject`
    ) {
      state.jobStatus = "waiting_dry_run";
      return json(route, 200, { ...job(state), status: "rejected" });
    }

    if (method === "POST" && path === `/execution-jobs/${state.jobId}/run`) {
      if (state.jobStatus !== "approved") {
        return json(route, 400, {
          detail: "Run allowed only when job status=approved",
        });
      }
      state.jobStatus = "success";
      state.runResults = true;
      return json(route, 200, {
        job_id: state.jobId,
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

    if (
      method === "GET" &&
      path === `/execution-jobs/${state.jobId}/results`
    ) {
      const rt = url.searchParams.get("result_type");
      let items = [...dryRunItems(state), ...runItems(state)];
      if (rt === "dry_run") items = dryRunItems(state);
      if (rt === "run") items = runItems(state);
      return json(route, 200, {
        job_id: state.jobId,
        job_status: state.jobStatus,
        dry_run_status: state.dryRunResults ? "dry_run_success" : null,
        result_type_filter: rt,
        total: items.length,
        items,
      });
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
