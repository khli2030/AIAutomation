import { expect, test } from "@playwright/test";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 10C — single-host pilot readiness UI (mocked API).
 * Never calls ansible-runner / playbook / subprocess / SSH.
 */

test.describe("Phase 10C single-host pilot", () => {
  test("Pilot Readiness panel renders with blocked reasons and max-host warning", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("pilot-readiness-panel")).toBeVisible();
    await expect(page.getByTestId("pilot-ready-badge")).toHaveText("false");
    await expect(page.getByTestId("max-hosts-per-run")).toHaveText("1");
    await expect(page.getByTestId("pilot-blocked-reasons")).toContainText(
      "REAL_ANSIBLE_PILOT_MODE=false",
    );
    await expect(page.getByTestId("max-host-warning")).toContainText(
      "max_hosts_per_run=1",
    );
    await expect(page.getByTestId("pilot-warnings")).toContainText(
      "Never use production or critical hosts",
    );
  });

  test("connectivity form prevents too many hosts", async ({ page }) => {
    const state = createInitialState({
      role: "admin",
      realExecutionAvailable: true,
    });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("pilot-ready-badge")).toHaveText("true");
    await expect(page.getByTestId("connectivity-check")).toBeEnabled();

    await page.getByTestId("connectivity-hosts").fill("host-a host-b");
    await expect(page.getByTestId("connectivity-host-limit")).toContainText(
      "Too many hosts (2)",
    );
    await expect(page.getByTestId("connectivity-check")).toBeDisabled();
  });

  test("real dry-run hidden when pilot not ready", async ({ page }) => {
    const state = createInitialState({ role: "admin", jobCount: 1 });
    state.validated = true;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-real-ansible-badge")).toContainText(
      "BLOCKED",
    );
    await expect(page.getByTestId("real-dry-run-1")).toHaveCount(0);
  });

  test("real dry-run hidden when job exceeds max_hosts_per_run", async ({
    page,
  }) => {
    const state = createInitialState({
      role: "admin",
      jobCount: 1,
      realExecutionAvailable: true,
    });
    state.validated = true;
    state.jobs[0].target_count = 3;
    await installMockApi(page, state);

    await page.goto("/plans/1");
    await expect(page.getByTestId("plan-real-ansible-badge")).toContainText(
      "AVAILABLE",
    );
    await expect(page.getByTestId("real-dry-run-1")).toHaveCount(0);
    await expect(page.getByTestId("real-dry-run-blocked-1")).toContainText(
      "max_hosts_per_run=1",
    );
  });

  test("no real apply/run button exists on Safety page", async ({ page }) => {
    const state = createInitialState({
      role: "admin",
      realExecutionAvailable: true,
    });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("no-real-apply-panel")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /real apply|apply\/run|Run apply/i }),
    ).toHaveCount(0);
  });
});
