/**
 * Browser API client for the compliance remediation backend.
 *
 * ADMIN_TOKEN is never hardcoded — operators paste it into sessionStorage
 * via the Settings page (or set NEXT_PUBLIC_ADMIN_TOKEN only for local lab).
 * Backend URL comes from NEXT_PUBLIC_API_URL (default http://127.0.0.1:8000).
 */

import type {
  AISuggestion,
  DashboardSummary,
  ExecutionJob,
  ExecutionPlan,
  ImportBatch,
  JobExecutionSummary,
  JobResult,
  Paginated,
  RawImportRecord,
  ValidationSummary,
} from "@/types/api";

export const DEFAULT_API_BASE = "http://127.0.0.1:8000";
export const TOKEN_STORAGE_KEY = "compliance_admin_token";

export function getApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL?.trim();
  return (fromEnv || DEFAULT_API_BASE).replace(/\/$/, "");
}

export function getAdminToken(): string {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_ADMIN_TOKEN?.trim() || "";
  }
  const stored = window.sessionStorage.getItem(TOKEN_STORAGE_KEY)?.trim();
  if (stored) return stored;
  return process.env.NEXT_PUBLIC_ADMIN_TOKEN?.trim() || "";
}

export function setAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  const value = token.trim();
  if (!value) {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    return;
  }
  window.sessionStorage.setItem(TOKEN_STORAGE_KEY, value);
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText || "Request failed";
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (body?.detail) detail = JSON.stringify(body.detail);
  } catch {
    /* ignore */
  }
  return new ApiError(res.status, detail);
}

type RequestOptions = {
  method?: string;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  token?: string;
  formData?: boolean;
};

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const token = options.token ?? getAdminToken();
  if (!token) {
    throw new ApiError(
      401,
      "ADMIN_TOKEN is not set. Open Settings and paste your token (never commit it).",
    );
  }

  const headers: Record<string, string> = {
    "X-Admin-Token": token,
    ...(options.headers || {}),
  };
  if (options.body && !options.formData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${getApiBase()}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body,
    cache: "no-store",
  });

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function fetchRootMeta(): Promise<{
  mock_mode: string;
  phase: string;
  app: string;
}> {
  return apiFetch("/");
}

export async function fetchDashboard(): Promise<DashboardSummary> {
  return apiFetch("/dashboard/summary");
}

export async function listImports(
  limit = 50,
  offset = 0,
): Promise<Paginated<ImportBatch>> {
  return apiFetch(`/imports?limit=${limit}&offset=${offset}`);
}

export async function getImport(batchId: number): Promise<ImportBatch> {
  return apiFetch(`/imports/${batchId}`);
}

export async function uploadExcel(
  file: File,
  uploadedBy?: string,
): Promise<{ batch: ImportBatch; message: string }> {
  const form = new FormData();
  form.append("file", file);
  if (uploadedBy) form.append("uploaded_by", uploadedBy);
  return apiFetch("/imports/upload", {
    method: "POST",
    body: form,
    formData: true,
  });
}

export async function validateBatch(
  batchId: number,
): Promise<ValidationSummary> {
  return apiFetch(`/imports/${batchId}/validate`, { method: "POST" });
}

export async function generatePlan(
  batchId: number,
  createdBy?: string,
): Promise<{ plan: ExecutionPlan; message: string }> {
  const q = createdBy
    ? `?created_by=${encodeURIComponent(createdBy)}`
    : "";
  return apiFetch(`/imports/${batchId}/generate-plan${q}`, { method: "POST" });
}

export async function aiAnalyzeNeedsReview(batchId: number): Promise<{
  batch_id: number;
  needs_review_records: number;
  analyzed: number;
  suggestions_created: number;
  skipped_non_needs_review: number;
  message: string;
}> {
  return apiFetch(`/imports/${batchId}/ai-analyze-needs-review`, {
    method: "POST",
  });
}

export async function listRecords(
  batchId: number,
  params: {
    limit?: number;
    offset?: number;
    validation_status?: string;
    task_code?: string;
    device_name?: string;
  } = {},
): Promise<{
  batch_id: number;
  total: number;
  limit: number;
  offset: number;
  items: RawImportRecord[];
}> {
  const q = new URLSearchParams();
  q.set("limit", String(params.limit ?? 100));
  q.set("offset", String(params.offset ?? 0));
  if (params.validation_status) q.set("validation_status", params.validation_status);
  if (params.task_code) q.set("task_code", params.task_code);
  if (params.device_name) q.set("device_name", params.device_name);
  return apiFetch(`/imports/${batchId}/records?${q.toString()}`);
}

export async function listPlans(
  limit = 50,
  offset = 0,
  batchId?: number,
): Promise<Paginated<ExecutionPlan>> {
  const q = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (batchId != null) q.set("batch_id", String(batchId));
  return apiFetch(`/execution-plans?${q.toString()}`);
}

export async function getPlan(planId: number): Promise<ExecutionPlan> {
  return apiFetch(`/execution-plans/${planId}`);
}

export async function listPlanJobs(
  planId: number,
): Promise<{ plan_id: number; total: number; items: ExecutionJob[] }> {
  return apiFetch(`/execution-plans/${planId}/jobs`);
}

export async function listJobs(params: {
  limit?: number;
  offset?: number;
  status?: string;
  plan_id?: number;
} = {}): Promise<Paginated<ExecutionJob>> {
  const q = new URLSearchParams();
  q.set("limit", String(params.limit ?? 50));
  q.set("offset", String(params.offset ?? 0));
  if (params.status) q.set("status", params.status);
  if (params.plan_id != null) q.set("plan_id", String(params.plan_id));
  return apiFetch(`/execution-jobs?${q.toString()}`);
}

export async function getJob(jobId: number): Promise<ExecutionJob> {
  return apiFetch(`/execution-jobs/${jobId}`);
}

export async function dryRunJob(jobId: number): Promise<JobExecutionSummary> {
  return apiFetch(`/execution-jobs/${jobId}/dry-run`, { method: "POST" });
}

export async function approveJob(
  jobId: number,
  reviewedBy?: string,
): Promise<ExecutionJob> {
  return apiFetch(`/execution-jobs/${jobId}/approve`, {
    method: "POST",
    body: JSON.stringify({ reviewed_by: reviewedBy || "ui-operator" }),
  });
}

export async function rejectJob(
  jobId: number,
  reviewedBy?: string,
): Promise<ExecutionJob> {
  return apiFetch(`/execution-jobs/${jobId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reviewed_by: reviewedBy || "ui-operator" }),
  });
}

export async function runJob(jobId: number): Promise<JobExecutionSummary> {
  return apiFetch(`/execution-jobs/${jobId}/run`, { method: "POST" });
}

export async function getJobResults(
  jobId: number,
  resultType?: "dry_run" | "run",
): Promise<{
  job_id: number;
  job_status: string;
  dry_run_status?: string | null;
  result_type_filter?: string | null;
  total: number;
  items: JobResult[];
}> {
  const q = resultType ? `?result_type=${resultType}` : "";
  return apiFetch(`/execution-jobs/${jobId}/results${q}`);
}

export async function listSuggestions(params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Paginated<AISuggestion>> {
  const q = new URLSearchParams();
  q.set("limit", String(params.limit ?? 50));
  q.set("offset", String(params.offset ?? 0));
  if (params.status) q.set("status", params.status);
  return apiFetch(`/ai-suggestions?${q.toString()}`);
}

export async function approveSuggestion(
  id: number,
  reviewedBy?: string,
): Promise<AISuggestion> {
  return apiFetch(`/ai-suggestions/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ reviewed_by: reviewedBy || "ui-operator" }),
  });
}

export async function rejectSuggestion(
  id: number,
  reviewedBy?: string,
): Promise<AISuggestion> {
  return apiFetch(`/ai-suggestions/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reviewed_by: reviewedBy || "ui-operator" }),
  });
}

export async function convertSuggestionToCatalog(
  id: number,
  reviewedBy?: string,
): Promise<{
  suggestion_id: number;
  catalog_id: number;
  task_code: string;
  is_enabled: boolean;
  ansible_playbook_path: string;
  message: string;
}> {
  // enable must stay false — UI never enables AI playbooks for execution.
  return apiFetch(`/ai-suggestions/${id}/convert-to-catalog`, {
    method: "POST",
    body: JSON.stringify({
      reviewed_by: reviewedBy || "ui-operator",
      enable: false,
    }),
  });
}
