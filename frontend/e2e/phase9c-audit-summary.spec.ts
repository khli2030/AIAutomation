import { expect, test } from "@playwright/test";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 9C — execution audit, plan summary cards, CSV export (mocked API).
 * Never calls ansible-runner / playbook / subprocess / SSH.
 */

test.describe("Phase 9C audit + summary + CSV", () => {
  test("plan summary cards render MOCK MODE and job/result counts", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 2 });
    state.validated = true;
    state.jobs[0].status = "dry_run_success";
    state.jobs[0].dryRunResults = true;
    state.jobs[1].status = "dry_run_failed";
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-summary-cards")).toBeVisible();
    await expect(page.getByTestId("plan-mode-badge")).toContainText("MOCK MODE");
    await expect(page.getByTestId("plan-mode-badge")).toContainText("Ansible off");
    await expect(page.getByTestId("plan-summary-cards")).toContainText(
      "dry_run_success",
    );
    await expect(page.getByTestId("plan-summary-cards")).toContainText(
      "dry_run_failed",
    );
    await expect(page.getByTestId("plan-summary-cards")).toContainText("dry run");
  });

  test("Audit tab renders timeline after dry-run / approve", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await page.getByTestId("dry-run-1").click();
    await expect(page.getByText(/Dry-run job #1/)).toBeVisible();

    await page.getByTestId("plan-tab-audit").click();
    await expect(page.getByTestId("plan-audit-timeline")).toBeVisible();
    await expect(page.getByTestId("plan-audit-event").first()).toBeVisible();
    await expect(page.getByTestId("plan-audit-timeline")).toContainText(
      "dry_run_completed",
    );
    await expect(page.getByTestId("plan-audit-timeline")).toContainText(
      "dry_run_started",
    );
  });

  test("Export Results CSV button exists on plan detail", async ({ page }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-export-csv")).toBeVisible();
    await expect(page.getByTestId("plan-export-csv")).toBeEnabled();
  });

  test("results page Export CSV + failed stdout/stderr still work", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    state.jobs[0].status = "dry_run_failed";
    await installMockApi(page, state);

    await page.goto("/jobs/1");
    await expect(page.getByTestId("results-export-csv")).toBeVisible();
    await expect(page.getByTestId("dry-run-failed-banner")).toBeVisible();
    await page.getByTestId("filter-result-type").selectOption("dry_run");
    await page.getByTestId("filter-result-status").selectOption("failed");
    await expect(page.getByTestId("failed-dry-run-result-110")).toBeVisible();
    await page.getByTestId("expand-result-110").click();
    await expect(page.getByTestId("stderr-110")).toContainText(
      "MOCK dry_run failed",
    );
    await expect(page.getByTestId("stdout-110")).toBeVisible();
  });

  test("viewer role still hides unauthorized actions; summary/audit readable", async ({
    page,
  }) => {
    const state = createInitialState({ role: "viewer", jobCount: 2 });
    state.validated = true;
    state.jobs[0].status = "waiting_dry_run";
    state.jobs[1].status = "dry_run_success";
    state.jobs[1].dryRunResults = true;
    state.auditEvents.push({
      id: 99,
      created_at: new Date().toISOString(),
      actor: "ui-e2e-admin",
      role: "admin",
      action: "dry_run",
      event: "dry_run_completed",
      plan_id: 1,
      job_id: 1,
      batch_id: 1,
      task_code: "SSH_DISABLE_ROOT_LOGIN",
      old_status: "waiting_dry_run",
      new_status: "dry_run_success",
      mock_mode: true,
      real_ansible_enabled: false,
      hosts_total: 2,
      hosts_success: 2,
      hosts_failed: 0,
      hosts_skipped: 0,
      hosts_changed: 0,
    });
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-summary-cards")).toBeVisible();
    await expect(page.getByTestId("plan-export-csv")).toBeVisible();
    await expect(page.getByTestId("dry-run-1")).toHaveCount(0);
    await expect(page.getByTestId("approve-2")).toHaveCount(0);
    await expect(page.getByTestId("bulk-dry-run")).toBeDisabled();
    await expect(page.getByTestId("bulk-approve")).toBeDisabled();
    await expect(page.getByTestId("bulk-run")).toBeDisabled();

    await page.getByTestId("plan-tab-audit").click();
    await expect(page.getByTestId("plan-audit-event").first()).toContainText(
      "dry_run_completed",
    );
  });
});
