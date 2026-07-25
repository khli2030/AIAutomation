import { expect, test } from "@playwright/test";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 10A — Safety / Ansible pilot UI (mocked API).
 * Never calls ansible-runner / playbook / subprocess / SSH.
 */

test.describe("Phase 10A Safety / Ansible pilot", () => {
  test("Safety / Ansible page renders blocked reasons by default", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByRole("heading", { name: "Safety / Ansible" })).toBeVisible();
    await expect(page.getByTestId("safety-status-panel")).toBeVisible();
    await expect(page.getByTestId("safety-mock-mode")).toHaveText("true");
    await expect(page.getByTestId("safety-real-enabled")).toHaveText("false");
    await expect(page.getByTestId("safety-check-mode-only")).toHaveText("true");
    await expect(page.getByTestId("safety-real-available")).toHaveText("NO");
    await expect(page.getByTestId("safety-reasons")).toContainText(
      "REAL_ANSIBLE_ENABLED=false",
    );
  });

  test("real dry-run button hidden when unavailable", async ({ page }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-real-ansible-badge")).toContainText(
      "BLOCKED",
    );
    await expect(page.getByTestId("real-dry-run-1")).toHaveCount(0);
  });

  test("real dry-run button requires confirmation when available", async ({
    page,
  }) => {
    const state = createInitialState({
      role: "admin",
      jobCount: 1,
      realExecutionAvailable: true,
    });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-real-ansible-badge")).toContainText(
      "AVAILABLE",
    );
    await expect(page.getByTestId("real-dry-run-1")).toBeVisible();
    await page.getByTestId("real-dry-run-1").click();
    await expect(
      page.getByText(
        "This runs Ansible in check mode only on allowlisted hosts.",
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: "Run check-mode dry-run" }).click();
    await expect(
      page.getByText(/Real Ansible dry-run \(check mode\) job #1/),
    ).toBeVisible();
    expect(state.callsRealDryRun).toEqual([1]);
  });

  test("Results support real_dry_run filter with expandable stdout/stderr", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    state.jobs[0].status = "dry_run_success";
    state.jobs[0].realDryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/jobs/1");
    await page.getByTestId("filter-result-type").selectOption("real_dry_run");
    await expect(page.getByTestId("result-row-310")).toBeVisible();
    await page.getByTestId("expand-result-310").click();
    await expect(page.getByTestId("stdout-310")).toContainText(
      "REAL check-mode ok",
    );
    await expect(page.getByTestId("stderr-310")).toBeVisible();
  });

  test("Audit timeline shows real ansible events", async ({ page }) => {
    const state = createInitialState({
      role: "admin",
      jobCount: 1,
      realExecutionAvailable: true,
    });
    state.validated = true;
    state.auditEvents.push({
      id: 501,
      created_at: new Date().toISOString(),
      actor: "ui-e2e-admin",
      role: "admin",
      action: "real_dry_run",
      event: "real_dry_run_completed",
      plan_id: 1,
      job_id: 1,
      batch_id: 1,
      task_code: "SSH_DISABLE_ROOT_LOGIN",
      old_status: "waiting_dry_run",
      new_status: "dry_run_success",
      mock_mode: false,
      real_ansible_enabled: true,
      hosts_total: 2,
      hosts_success: 2,
      hosts_failed: 0,
      hosts_skipped: 0,
      hosts_changed: 0,
    });
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await page.getByTestId("plan-tab-audit").click();
    await expect(page.getByTestId("plan-audit-timeline")).toContainText(
      "real_dry_run_completed",
    );
  });
});
