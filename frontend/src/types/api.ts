/** Shared API types for the Phase 7 operator UI. */

export type ImportBatch = {
  id: number;
  original_filename: string;
  stored_path: string;
  status: string;
  total_records: number;
  valid_records: number;
  invalid_records: number;
  total_rows?: number | null;
  processed_rows: number;
  uploaded_by?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type RawImportRecord = {
  id: number;
  batch_id: number;
  row_number: number;
  device_name?: string | null;
  overall_status?: string | null;
  criticality?: string | null;
  qualys_control_id?: string | null;
  source_check_id?: string | null;
  control_description?: string | null;
  remediation?: string | null;
  expected_configuration?: string | null;
  task_code?: string | null;
  validation_status?: string | null;
  validation_error?: string | null;
  record_hash?: string | null;
  created_at: string;
};

export type ValidationSummary = {
  batch_id: number;
  total_records: number;
  ready_for_plan: number;
  needs_review: number;
  asset_not_found: number;
  already_compliant: number;
  duplicate: number;
  invalid_record: number;
  unsupported_control: number;
};

export type ExecutionPlan = {
  id: number;
  batch_id: number;
  status: string;
  created_by?: string | null;
  created_at: string;
  job_count: number;
  target_count: number;
  skipped_records?: number;
  ready_for_plan_records?: number;
  skipped_missing_catalog?: number;
  skipped_disabled_catalog?: number;
  skipped_missing_asset?: number;
  skipped_missing_asset_metadata?: number;
  skipped_excluded_status?: number;
};

export type ExecutionJob = {
  id: number;
  plan_id: number;
  task_code: string;
  environment?: string | null;
  criticality?: string | null;
  ansible_group?: string | null;
  status: string;
  dry_run_status?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  target_count: number;
};

export type JobResult = {
  id: number;
  job_id: number;
  result_type: string;
  device_name: string;
  status: string;
  changed: boolean;
  skipped: boolean;
  stdout?: string | null;
  stderr?: string | null;
  return_code?: number | null;
  created_at: string;
};

export type PlanAuditEvent = {
  id: number;
  created_at: string;
  actor: string;
  role?: string | null;
  action: string;
  event: string;
  plan_id?: number | null;
  job_id?: number | null;
  batch_id?: number | null;
  task_code?: string | null;
  old_status?: string | null;
  new_status?: string | null;
  mock_mode?: boolean | null;
  real_ansible_enabled?: boolean | null;
  hosts_total?: number | null;
  hosts_success?: number | null;
  hosts_failed?: number | null;
  hosts_skipped?: number | null;
  hosts_changed?: number | null;
};

export type PlanExecutionSummary = {
  plan_id: number;
  batch_id: number;
  total_jobs: number;
  jobs_by_status: Record<string, number>;
  total_targets: number;
  dry_run_results_by_status: Record<string, number>;
  run_results_by_status: Record<string, number>;
  failed_task_codes: string[];
  skipped_task_codes: string[];
  mock_mode: boolean;
  real_ansible_enabled: boolean;
};

export type AnsibleSafetyStatus = {
  mock_mode: boolean;
  real_ansible_enabled: boolean;
  check_mode_only: boolean;
  allowed_hosts_count: number;
  allowed_task_codes_count: number;
  inventory_configured: boolean;
  private_key_configured: boolean;
  remote_user_configured: boolean;
  real_execution_available: boolean;
  reasons: string[];
  allowed_hosts?: string[];
  allowed_task_codes?: string[];
  timeout_seconds?: number;
  pilot_mode?: boolean;
  max_hosts_per_run?: number;
  single_host_pilot_qualified?: boolean;
  auth_mode?: string;
  auth_source?: string;
};

export type LabConfigPreview = {
  allowed_hosts: string[];
  allowed_task_codes: string[];
  inventory_path_configured: boolean;
  private_key_configured: boolean;
  remote_user_configured: boolean;
  timeout_seconds: number;
  validation_status: string;
  validation_errors: string[];
  mock_mode: boolean;
  real_ansible_enabled: boolean;
  check_mode_only: boolean;
  connectivity_allowed: boolean;
  pilot_mode?: boolean;
  max_hosts_per_run?: number;
  pilot_ready?: boolean;
  pilot_readiness_errors?: string[];
  auth_mode?: string;
  auth_source?: string;
};

export type PilotReadiness = {
  ready: boolean;
  mock_mode: boolean;
  real_ansible_enabled: boolean;
  check_mode_only: boolean;
  pilot_mode: boolean;
  max_hosts_per_run: number;
  allowed_hosts: string[];
  allowed_task_codes: string[];
  inventory_configured: boolean;
  remote_user_configured: boolean;
  private_key_configured: boolean;
  auth_mode?: string;
  auth_source?: string;
  errors: string[];
  warnings: string[];
};

export type JobExecutionSummary = {
  job_id: number;
  mode: string;
  mock_mode: boolean;
  status: string;
  dry_run_status?: string | null;
  hosts_total: number;
  hosts_success: number;
  hosts_failed: number;
  hosts_changed: number;
  hosts_skipped: number;
  message?: string;
};

export type AISuggestion = {
  id: number;
  raw_record_id: number;
  source_check_id?: string | null;
  qualys_control_id?: string | null;
  control_description?: string | null;
  rationale?: string | null;
  remediation?: string | null;
  expected_configuration?: string | null;
  suggested_task_code?: string | null;
  confidence?: number | null;
  risk_level?: string | null;
  target_file?: string | null;
  setting_name?: string | null;
  expected_value?: string | null;
  ansible_module?: string | null;
  generated_playbook?: string | null;
  validation_notes?: string | null;
  safety_warnings?: string | null;
  rollback_strategy?: string | null;
  status: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string;
};

export type DashboardSummary = {
  mock_mode: boolean;
  import_batches_total: number;
  import_batches_by_status: Record<string, number>;
  records_total: number;
  records_by_validation_status: Record<string, number>;
  jobs_total: number;
  jobs_by_status: Record<string, number>;
  plans_total: number;
  suggestions_total: number;
  suggestions_by_status: Record<string, number>;
  latest_imports: ImportBatch[];
  latest_jobs: ExecutionJob[];
  generated_at: string;
};

export type Paginated<T> = {
  total: number;
  limit: number;
  offset: number;
  items: T[];
};
