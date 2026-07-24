import { expect, test } from "@playwright/test";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 9B — frontend execution workflow controls (mocked API).
 * Never calls ansible-runner / playbook / subprocess / SSH.
 */

test.describe("Phase 9B workflow controls", () => {
  test("validate + generate-plan buttons call the right APIs", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/imports?batchId=1");
    await expect(page.getByRole("heading", { name: "Import Summary" })).toBeVisible();
    await page.getByTestId("validate-batch").click();
    await expect(page.getByText(/Validated: 2 READY_FOR_PLAN/)).toBeVisible();
    expect(state.validated).toBe(true);

    await page.getByTestId("generate-plan").click();
    await expect(page.getByText(/Plan #1 created/)).toBeVisible();
    expect(state.jobs[0].status).toBe("waiting_dry_run");
  });

  test("plans page shows plan rows and plan detail shows jobs", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 2 });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/plans");
    await expect(page.getByRole("heading", { name: "Execution Plans" })).toBeVisible();
    await expect(page.getByTestId("plan-row-1")).toBeVisible();
    await expect(page.getByText("Job count").or(page.getByText("job count", { exact: false }))).toBeVisible();
    await page.getByTestId("view-jobs-1").click();
    await expect(page.getByRole("heading", { name: "Plan #1" })).toBeVisible();
    await expect(page.getByTestId("plan-job-row-1")).toBeVisible();
    await expect(page.getByTestId("plan-job-row-2")).toBeVisible();
  });

  test("status-gated action buttons on plan detail", async ({ page }) => {
    const state = createInitialState({ role: "admin", jobCount: 3 });
    state.validated = true;
    state.jobs[0].status = "waiting_dry_run";
    state.jobs[1].status = "dry_run_success";
    state.jobs[1].dryRunResults = true;
    state.jobs[2].status = "approved";
    state.jobs[2].dryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("dry-run-1")).toBeVisible();
    await expect(page.getByTestId("approve-1")).toHaveCount(0);
    await expect(page.getByTestId("run-1")).toHaveCount(0);

    await expect(page.getByTestId("approve-2")).toBeVisible();
    await expect(page.getByTestId("dry-run-2")).toHaveCount(0);
    await expect(page.getByTestId("run-2")).toHaveCount(0);

    await expect(page.getByTestId("run-3")).toBeVisible();
    await expect(page.getByTestId("dry-run-3")).toHaveCount(0);
    await expect(page.getByTestId("approve-3")).toHaveCount(0);
  });

  test("bulk dry-run / approve / run only call eligible jobs", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 3 });
    state.validated = true;
    state.jobs[0].status = "waiting_dry_run";
    state.jobs[1].status = "dry_run_success";
    state.jobs[1].dryRunResults = true;
    state.jobs[2].status = "approved";
    state.jobs[2].dryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");

    await page.getByTestId("bulk-dry-run").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk dry_run:/)).toBeVisible();
    expect(state.calls.dryRun).toEqual([1]);
    expect(state.jobs[0].status).toBe("dry_run_success");
    // Non-waiting jobs must not be dry-run
    expect(state.calls.dryRun).not.toContain(2);
    expect(state.calls.dryRun).not.toContain(3);

    await page.getByTestId("bulk-approve").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk approve:/)).toBeVisible();
    // Jobs 1 (now dry_run_success after bulk dry-run) and 2
    expect(state.calls.approve.sort()).toEqual([1, 2]);
    expect(state.calls.approve).not.toContain(3);
    expect(state.jobs[0].status).toBe("approved");
    expect(state.jobs[1].status).toBe("approved");
    expect(state.jobs[2].status).toBe("approved");

    await page.getByTestId("bulk-run").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk run:/)).toBeVisible();
    expect(state.calls.run.sort()).toEqual([1, 2, 3]);
    expect(state.jobs.every((j) => j.status === "success")).toBe(true);
  });

  test("viewer cannot see workflow action buttons", async ({ page }) => {
    const state = createInitialState({ role: "viewer", jobCount: 2 });
    state.validated = true;
    state.jobs[0].status = "waiting_dry_run";
    state.jobs[1].status = "dry_run_success";
    state.jobs[1].dryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/imports?batchId=1");
    await expect(page.getByTestId("validate-batch")).toBeDisabled();
    await expect(page.getByTestId("generate-plan")).toBeDisabled();

    await page.goto("/plans/1");
    await expect(page.getByTestId("dry-run-1")).toHaveCount(0);
    await expect(page.getByTestId("approve-2")).toHaveCount(0);
    await expect(page.getByTestId("bulk-dry-run")).toBeDisabled();
    await expect(page.getByTestId("bulk-approve")).toBeDisabled();
    await expect(page.getByTestId("bulk-run")).toBeDisabled();
    await expect(page.getByText(/Viewer role is read-only/)).toBeVisible();
  });

  test("admin sees allowed action buttons", async ({ page }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/imports?batchId=1");
    await expect(page.getByTestId("validate-batch")).toBeEnabled();

    await page.goto("/plans/1");
    await expect(page.getByTestId("dry-run-1")).toBeVisible();
    await expect(page.getByTestId("bulk-dry-run")).toBeEnabled();
  });

  test("full UI flow without curl: validate → plan → bulk dry-run → approve → run → results", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 2 });
    await installMockApi(page, state);

    await page.goto("/imports?batchId=1");
    await page.getByTestId("validate-batch").click();
    await expect(
      page.getByText("Validated: 2 READY_FOR_PLAN, 0 NEEDS_REVIEW"),
    ).toBeVisible();
    await page.getByTestId("generate-plan").click();
    await expect(page.getByText(/Plan #1 created/)).toBeVisible();
    await page.getByRole("link", { name: "#1" }).click();

    await expect(page.getByRole("heading", { name: "Plan #1" })).toBeVisible();
    await page.getByTestId("bulk-dry-run").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk dry_run:/)).toBeVisible();

    await page.getByTestId("bulk-approve").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk approve:/)).toBeVisible();

    await page.getByTestId("bulk-run").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk run:/)).toBeVisible();

    await page.getByTestId("results-1").click();
    await expect(page.getByRole("heading", { name: /Job #1 results/ })).toBeVisible();
    await page.getByTestId("filter-result-type").selectOption("dry_run");
    await expect(page.getByText("e2e-linux-01")).toBeVisible();
  });

  test("Retry Dry Run appears for dry_run_failed; Approve/Run hidden", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 2 });
    state.validated = true;
    state.jobs[0].status = "dry_run_failed";
    state.jobs[1].status = "dry_run_success";
    state.jobs[1].dryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("retry-dry-run-1")).toBeVisible();
    await expect(page.getByTestId("approve-1")).toHaveCount(0);
    await expect(page.getByTestId("run-1")).toHaveCount(0);
    await expect(page.getByTestId("dry-run-1")).toHaveCount(0);

    await expect(page.getByTestId("approve-2")).toBeVisible();
    await expect(page.getByTestId("retry-dry-run-2")).toHaveCount(0);
  });

  test("Bulk Retry Failed Dry Runs only calls dry_run_failed jobs", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 3 });
    state.validated = true;
    state.jobs[0].status = "dry_run_failed";
    state.jobs[1].status = "waiting_dry_run";
    state.jobs[2].status = "dry_run_success";
    state.jobs[2].dryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("bulk-retry-dry-run")).toBeEnabled();
    await page.getByTestId("bulk-retry-dry-run").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk retry_dry_run:/)).toBeVisible();

    expect(state.calls.dryRun).toEqual([1]);
    expect(state.calls.dryRun).not.toContain(2);
    expect(state.calls.dryRun).not.toContain(3);
    expect(state.jobs[0].status).toBe("dry_run_success");
    expect(state.jobs[1].status).toBe("waiting_dry_run");
    expect(state.jobs[2].status).toBe("dry_run_success");
  });

  test("Bulk Approve and Bulk Run ignore dry_run_failed jobs", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 3 });
    state.validated = true;
    state.jobs[0].status = "dry_run_failed";
    state.jobs[1].status = "dry_run_success";
    state.jobs[1].dryRunResults = true;
    state.jobs[2].status = "approved";
    state.jobs[2].dryRunResults = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");

    await page.getByTestId("bulk-approve").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk approve:/)).toBeVisible();
    expect(state.calls.approve).toEqual([2]);
    expect(state.calls.approve).not.toContain(1);
    expect(state.jobs[0].status).toBe("dry_run_failed");
    expect(state.jobs[1].status).toBe("approved");

    await page.getByTestId("bulk-run").click();
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Bulk run:/)).toBeVisible();
    // After approve, jobs 1 (still failed) and 2 (now approved) + original approved 3
    expect(state.calls.run.sort()).toEqual([2, 3]);
    expect(state.calls.run).not.toContain(1);
    expect(state.jobs[0].status).toBe("dry_run_failed");
  });

  test("results page highlights failed dry_run rows with stdout/stderr", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    state.jobs[0].status = "dry_run_failed";
    await installMockApi(page, state);

    await page.goto("/jobs/1");
    await expect(page.getByTestId("dry-run-failed-banner")).toBeVisible();
    await page.getByTestId("filter-result-type").selectOption("dry_run");
    await page.getByTestId("filter-result-status").selectOption("failed");
    await expect(page.getByTestId("failed-dry-run-result-110")).toBeVisible();
    await page.getByTestId("expand-result-110").click();
    await expect(page.getByTestId("stderr-110")).toContainText("MOCK dry_run failed");
    await expect(page.getByTestId("stdout-110")).toBeVisible();
  });
});
