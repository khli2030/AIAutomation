/**
 * Stateful FastAPI mock for Phase 7.5 / 9B / 9C Playwright UI E2E.
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
  realDryRunResults: boolean;
  task_code: string;
  environment: string;
  criticality: string;
  ansible_group: string;
  target_count: number;
};

export type MockAuditEvent = {
  id: number;
  created_at: string;
  actor: string;
  role: string;
  action: string;
  event: string;
  plan_id: number;
  job_id: number;
  batch_id: number;
  task_code: string;
  old_status: string | null;
  new_status: string | null;
  mock_mode: boolean;
  real_ansible_enabled: boolean;
  hosts_total: number | null;
  hosts_success: number | null;
  hosts_failed: number | null;
  hosts_skipped: number | null;
  hosts_changed: number | null;
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
  /** Phase 9C execution audit timeline (newest first). */
  auditEvents: MockAuditEvent[];
  nextAuditId: number;
  /** Phase 10A/10C safety-status overrides for UI tests. */
  realExecutionAvailable: boolean;
  realAnsibleEnabled: boolean;
  checkModeOnly: boolean;
  pilotMode: boolean;
  maxHostsPerRun: number;
  pilotReady: boolean;
  allowedHostsCount: number;
  allowedTaskCodesCount: number;
  safetyReasons: string[];
  pilotErrors: string[];
  pilotWarnings: string[];
  callsRealDryRun: number[];
};

export type InstallMockOptions = {
  role?: MockApiState["role"];
  jobCount?: number;
  realExecutionAvailable?: boolean;
  /** When true with realExecutionAvailable, jobs default to single-host target_count. */
  pilotReady?: boolean;
};

const now = () => new Date().toISOString();

function makeJobs(count: number, targetCount = 2): MockJob[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    status: "waiting_dry_run" as const,
    dryRunResults: false,
    runResults: false,
    realDryRunResults: false,
    task_code: "SSH_DISABLE_ROOT_LOGIN",
    environment: "test",
    criticality: "High",
    ansible_group: "linux_test",
    target_count: targetCount,
  }));
}

export function createInitialState(
  options: InstallMockOptions = {},
): MockApiState {
  const jobCount = options.jobCount ?? 1;
  const realAvailable = options.realExecutionAvailable ?? false;
  const pilotReady =
    options.pilotReady ?? realAvailable;
  const targetCount = realAvailable && pilotReady ? 1 : 2;
  return {
    batchId: 1,
    planId: 1,
    batchStatus: "parsed",
    validated: false,
    jobs: makeJobs(jobCount, targetCount),
    role: options.role ?? "admin",
    calls: { dryRun: [], approve: [], run: [], reject: [] },
    auditEvents: [],
    nextAuditId: 1,
    realExecutionAvailable: realAvailable,
    realAnsibleEnabled: realAvailable,
    checkModeOnly: true,
    pilotMode: realAvailable && pilotReady,
    maxHostsPerRun: 1,
    pilotReady: realAvailable && pilotReady,
    allowedHostsCount: realAvailable ? 1 : 0,
    allowedTaskCodesCount: realAvailable ? 1 : 0,
    safetyReasons: realAvailable
      ? [
          "Pilot real check-mode path is configured (still allowlist + check-mode gated; apply remains blocked)",
        ]
      : [
          "MOCK_MODE=true (safe default)",
          "REAL_ANSIBLE_ENABLED=false (safe default)",
          "REAL_ANSIBLE_CHECK_MODE_ONLY=true — apply/run remains blocked",
          "REAL_ANSIBLE_PILOT_MODE=false — single-host lab pilot disabled",
          "No hosts in REAL_ANSIBLE_ALLOWED_HOSTS",
          "No task codes in REAL_ANSIBLE_ALLOWED_TASK_CODES",
        ],
    pilotErrors: realAvailable && pilotReady
      ? []
      : [
          "REAL_ANSIBLE_PILOT_MODE=false — pilot not ready",
          "MOCK_MODE=true — pilot not ready",
          "REAL_ANSIBLE_ENABLED=false — pilot not ready",
        ],
    pilotWarnings: [
      "Single-host pilot: REAL_ANSIBLE_MAX_HOSTS_PER_RUN=1 (jobs with more targets cannot use real dry-run)",
      "Check-mode only — real apply/run remains blocked in Phase 10C",
      "Never use production or critical hosts for the lab pilot",
    ],
    callsRealDryRun: [],
  };
}

function pushAudit(
  state: MockApiState,
  partial: Omit<MockAuditEvent, "id" | "created_at" | "plan_id" | "batch_id" | "mock_mode" | "real_ansible_enabled" | "actor" | "role"> &
    Partial<Pick<MockAuditEvent, "actor" | "role" | "hosts_total" | "hosts_success" | "hosts_failed" | "hosts_skipped" | "hosts_changed">>,
) {
  const event: MockAuditEvent = {
    id: state.nextAuditId++,
    created_at: now(),
    actor: partial.actor ?? `ui-e2e-${state.role}`,
    role: partial.role ?? state.role,
    action: partial.action,
    event: partial.event,
    plan_id: state.planId,
    job_id: partial.job_id,
    batch_id: state.batchId,
    task_code: partial.task_code,
    old_status: partial.old_status,
    new_status: partial.new_status,
    mock_mode: true,
    real_ansible_enabled: false,
    hosts_total: partial.hosts_total ?? null,
    hosts_success: partial.hosts_success ?? null,
    hosts_failed: partial.hosts_failed ?? null,
    hosts_skipped: partial.hosts_skipped ?? null,
    hosts_changed: partial.hosts_changed ?? null,
  };
  state.auditEvents.unshift(event);
}

function planSummary(state: MockApiState) {
  const jobs_by_status: Record<string, number> = {};
  for (const j of state.jobs) {
    jobs_by_status[j.status] = (jobs_by_status[j.status] || 0) + 1;
  }
  const dry_run_results_by_status: Record<string, number> = {};
  const run_results_by_status: Record<string, number> = {};
  const failed_task_codes = new Set<string>();
  for (const j of state.jobs) {
    for (const r of dryRunItems(j)) {
      dry_run_results_by_status[r.status] =
        (dry_run_results_by_status[r.status] || 0) + 1;
      if (String(r.status).includes("fail")) failed_task_codes.add(j.task_code);
    }
    for (const r of runItems(j)) {
      run_results_by_status[r.status] =
        (run_results_by_status[r.status] || 0) + 1;
    }
  }
  return {
    plan_id: state.planId,
    batch_id: state.batchId,
    total_jobs: state.jobs.length,
    jobs_by_status,
    total_targets: state.jobs.reduce((n, j) => n + j.target_count, 0),
    dry_run_results_by_status,
    run_results_by_status,
    failed_task_codes: [...failed_task_codes],
    skipped_task_codes: [],
    mock_mode: true,
    real_ansible_enabled: false,
  };
}

function resultsCsv(state: MockApiState): string {
  const header = [
    "plan_id",
    "job_id",
    "task_code",
    "host",
    "result_type",
    "status",
    "changed",
    "stdout",
    "stderr",
    "message",
    "created_at",
  ].join(",");
  const rows: string[] = [header];
  for (const j of state.jobs) {
    for (const r of [...dryRunItems(j), ...runItems(j)]) {
      const message = (r.stderr || r.stdout || "").slice(0, 500);
      rows.push(
        [
          state.planId,
          j.id,
          j.task_code,
          r.device_name,
          r.result_type,
          r.status,
          r.changed,
          JSON.stringify(r.stdout || ""),
          JSON.stringify(r.stderr || ""),
          JSON.stringify(message),
          r.created_at,
        ].join(","),
      );
    }
  }
  return rows.join("\n") + "\n";
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

function realDryRunItems(j: MockJob) {
  if (!j.realDryRunResults) return [];
  return [
    {
      id: 300 + j.id * 10,
      job_id: j.id,
      result_type: "real_dry_run",
      device_name: "e2e-linux-01",
      status: "success",
      changed: false,
      skipped: false,
      stdout: "REAL check-mode ok",
      stderr: "",
      return_code: 0,
      created_at: now(),
    },
    {
      id: 301 + j.id * 10,
      job_id: j.id,
      result_type: "real_dry_run",
      device_name: "e2e-linux-02",
      status: "success",
      changed: false,
      skipped: false,
      stdout: "REAL check-mode ok",
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
        phase: "10A",
        auth: "role token required",
        mock_mode: "true",
        role: state.role,
      });
    }

    if (method === "GET" && path === "/ansible/safety-status") {
      return json(route, 200, {
        mock_mode: !state.pilotReady,
        real_ansible_enabled: state.realAnsibleEnabled,
        check_mode_only: state.checkModeOnly,
        allowed_hosts_count: state.allowedHostsCount,
        allowed_task_codes_count: state.allowedTaskCodesCount,
        inventory_configured: state.realExecutionAvailable,
        private_key_configured: state.realExecutionAvailable,
        remote_user_configured: state.realExecutionAvailable,
        real_execution_available: state.realExecutionAvailable && state.pilotReady,
        reasons: state.safetyReasons,
        allowed_hosts: state.realExecutionAvailable ? ["e2e-linux-01"] : [],
        allowed_task_codes: state.realExecutionAvailable
          ? ["SSH_DISABLE_ROOT_LOGIN"]
          : [],
        timeout_seconds: 120,
        pilot_mode: state.pilotMode,
        max_hosts_per_run: state.maxHostsPerRun,
        single_host_pilot_qualified: state.pilotReady,
      });
    }

    if (method === "GET" && path === "/ansible/lab-config-preview") {
      return json(route, 200, {
        allowed_hosts: state.realExecutionAvailable ? ["e2e-linux-01"] : [],
        allowed_task_codes: state.realExecutionAvailable
          ? ["SSH_DISABLE_ROOT_LOGIN"]
          : [],
        inventory_path_configured: state.realExecutionAvailable,
        private_key_configured: state.realExecutionAvailable,
        remote_user_configured: state.realExecutionAvailable,
        timeout_seconds: 120,
        validation_status: state.pilotReady ? "ok" : "blocked",
        validation_errors: state.pilotReady ? [] : state.safetyReasons,
        mock_mode: !state.pilotReady,
        real_ansible_enabled: state.realAnsibleEnabled,
        check_mode_only: state.checkModeOnly,
        connectivity_allowed: state.pilotReady,
        pilot_mode: state.pilotMode,
        max_hosts_per_run: state.maxHostsPerRun,
        pilot_ready: state.pilotReady,
        pilot_readiness_errors: state.pilotReady ? [] : state.pilotErrors,
      });
    }

    if (method === "GET" && path === "/ansible/pilot-readiness") {
      return json(route, 200, {
        ready: state.pilotReady,
        mock_mode: !state.pilotReady,
        real_ansible_enabled: state.realAnsibleEnabled,
        check_mode_only: state.checkModeOnly,
        pilot_mode: state.pilotMode,
        max_hosts_per_run: state.maxHostsPerRun,
        allowed_hosts: state.realExecutionAvailable ? ["e2e-linux-01"] : [],
        allowed_task_codes: state.realExecutionAvailable
          ? ["SSH_DISABLE_ROOT_LOGIN"]
          : [],
        inventory_configured: state.realExecutionAvailable,
        remote_user_configured: state.realExecutionAvailable,
        private_key_configured: state.realExecutionAvailable,
        errors: state.pilotReady ? [] : state.pilotErrors,
        warnings: state.pilotWarnings,
      });
    }

    if (method === "POST" && path === "/ansible/connectivity-check") {
      const body = req.postDataJSON() as { hosts?: string[] };
      const hosts = body?.hosts || [];
      if (hosts.length > state.maxHostsPerRun) {
        pushAudit(state, {
          action: "connectivity_check",
          event: "real_execution_blocked",
          job_id: 0,
          task_code: "",
          old_status: null,
          new_status: null,
        });
        return json(route, 200, {
          ok: false,
          blocked: true,
          hosts,
          blocked_hosts: hosts,
          reasons: [
            `Host count ${hosts.length} exceeds REAL_ANSIBLE_MAX_HOSTS_PER_RUN=${state.maxHostsPerRun}`,
          ],
          stdout: "",
          stderr: "max hosts exceeded",
          mock_mode: true,
          real_ansible_enabled: state.realAnsibleEnabled,
        });
      }
      if (!state.realAnsibleEnabled || !state.pilotReady) {
        pushAudit(state, {
          action: "connectivity_check",
          event: "real_execution_blocked",
          job_id: 0,
          task_code: "",
          old_status: null,
          new_status: null,
        });
        return json(route, 200, {
          ok: false,
          blocked: true,
          hosts,
          blocked_hosts: hosts,
          reasons: state.pilotReady
            ? ["REAL_ANSIBLE_ENABLED=false"]
            : ["REAL_ANSIBLE_PILOT_MODE=false — single-host lab pilot disabled"],
          stdout: "",
          stderr: "blocked",
          mock_mode: true,
          real_ansible_enabled: state.realAnsibleEnabled,
        });
      }
      return json(route, 200, {
        ok: true,
        blocked: false,
        hosts,
        reasons: [],
        stdout: "pong",
        stderr: "",
        mock_mode: false,
        real_ansible_enabled: true,
        module: "ping",
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
        j.realDryRunResults = false;
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

    if (
      method === "GET" &&
      path === `/execution-plans/${state.planId}/summary`
    ) {
      return json(route, 200, planSummary(state));
    }

    if (
      method === "GET" &&
      path === `/execution-plans/${state.planId}/audit`
    ) {
      return json(route, 200, {
        plan_id: state.planId,
        total: state.auditEvents.length,
        items: state.auditEvents,
      });
    }

    if (
      method === "GET" &&
      path === `/execution-plans/${state.planId}/results.csv`
    ) {
      return route.fulfill({
        status: 200,
        contentType: "text/csv; charset=utf-8",
        headers: {
          "Content-Disposition": `attachment; filename="plan-${state.planId}-results.csv"`,
        },
        body: resultsCsv(state),
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
        const oldStatus = j.status;
        const startEvent =
          oldStatus === "dry_run_failed"
            ? "dry_run_retry_started"
            : "dry_run_started";
        pushAudit(state, {
          action: "dry_run",
          event: startEvent,
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "running",
        });
        j.status = "dry_run_success";
        j.dryRunResults = true;
        pushAudit(state, {
          action: "dry_run",
          event: "dry_run_completed",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "dry_run_success",
          hosts_total: 2,
          hosts_success: 2,
          hosts_failed: 0,
          hosts_changed: 0,
          hosts_skipped: 0,
        });
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
        const oldStatus = j.status;
        j.status = "approved";
        pushAudit(state, {
          action: "approve",
          event: "approved",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "approved",
        });
        return json(route, 200, jobPayload(j, state.planId));
      }

      if (method === "POST" && path === `/execution-jobs/${jobId}/reject`) {
        state.calls.reject.push(jobId);
        const oldStatus = j.status;
        j.status = "rejected";
        pushAudit(state, {
          action: "reject",
          event: "rejected",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "rejected",
        });
        return json(route, 200, jobPayload(j, state.planId));
      }

      if (method === "POST" && path === `/execution-jobs/${jobId}/run`) {
        state.calls.run.push(jobId);
        if (j.status !== "approved") {
          return json(route, 400, {
            detail: "Run allowed only when job status=approved",
          });
        }
        const oldStatus = j.status;
        pushAudit(state, {
          action: "run",
          event: "run_started",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "running",
        });
        j.status = "success";
        j.runResults = true;
        pushAudit(state, {
          action: "run",
          event: "run_completed",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "success",
          hosts_total: 2,
          hosts_success: 2,
          hosts_failed: 0,
          hosts_changed: 2,
          hosts_skipped: 0,
        });
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

      if (method === "POST" && path === `/execution-jobs/${jobId}/real-dry-run`) {
        state.callsRealDryRun.push(jobId);
        if (!state.realExecutionAvailable) {
          pushAudit(state, {
            action: "real_dry_run",
            event: "real_execution_blocked",
            job_id: jobId,
            task_code: j.task_code,
            old_status: j.status,
            new_status: j.status,
          });
          return json(route, 400, {
            detail: "REAL_ANSIBLE_ENABLED=false",
          });
        }
        const oldStatus = j.status;
        pushAudit(state, {
          action: "real_dry_run",
          event: "real_dry_run_started",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "dry_run_running",
        });
        j.status = "dry_run_success";
        j.realDryRunResults = true;
        pushAudit(state, {
          action: "real_dry_run",
          event: "real_dry_run_completed",
          job_id: jobId,
          task_code: j.task_code,
          old_status: oldStatus,
          new_status: "dry_run_success",
          hosts_total: 2,
          hosts_success: 2,
          hosts_failed: 0,
          hosts_changed: 0,
          hosts_skipped: 0,
        });
        return json(route, 200, {
          job_id: jobId,
          mode: "dry_run",
          mock_mode: false,
          status: "dry_run_success",
          dry_run_status: "dry_run_success",
          hosts_total: 2,
          hosts_success: 2,
          hosts_failed: 0,
          hosts_changed: 0,
          hosts_skipped: 0,
          message: "Real Ansible check-mode dry-run completed",
        });
      }

      if (method === "GET" && path === `/execution-jobs/${jobId}/results`) {
        const rt = url.searchParams.get("result_type");
        let items = [
          ...dryRunItems(j),
          ...realDryRunItems(j),
          ...runItems(j),
        ];
        if (rt === "dry_run") items = dryRunItems(j);
        if (rt === "real_dry_run") items = realDryRunItems(j);
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
