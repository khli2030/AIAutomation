import { expect, test } from "@playwright/test";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 10B — lab config preview + gated connectivity UI (mocked API).
 * Never calls ansible-runner / playbook / subprocess / SSH.
 */

test.describe("Phase 10B lab inventory + connectivity", () => {
  test("Safety page shows lab config preview and blocked reasons", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByRole("heading", { name: "Safety / Ansible" })).toBeVisible();
    await expect(page.getByTestId("lab-config-preview")).toBeVisible();
    await expect(page.getByTestId("lab-validation-status")).toHaveText("blocked");
    await expect(page.getByTestId("lab-validation-errors")).toContainText(
      "REAL_ANSIBLE_ENABLED=false",
    );
    await expect(page.getByTestId("safety-reasons")).toContainText(
      "REAL_ANSIBLE_ENABLED=false",
    );
    await expect(page.getByTestId("lab-inventory-configured")).toHaveText(
      "false",
    );
    await expect(page.getByTestId("lab-remote-user-configured")).toHaveText(
      "false",
    );
    await expect(page.getByTestId("lab-private-key-configured")).toHaveText(
      "false",
    );
    await expect(page.getByTestId("lab-timeout-seconds")).toHaveText("120");
  });

  test("connectivity check disabled when unavailable", async ({ page }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("connectivity-check")).toBeDisabled();
    await expect(page.getByTestId("connectivity-disabled-note")).toBeVisible();
  });

  test("no real apply/run button exists; private key secret never displayed", async ({
    page,
  }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("no-real-apply-panel")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /real apply|apply\/run|Run apply/i }),
    ).toHaveCount(0);
    const body = await page.locator("body").innerText();
    // Secret material must never appear (labels like private_key_configured are OK).
    expect(body).not.toContain("BEGIN OPENSSH");
    expect(body).not.toContain("BEGIN RSA PRIVATE KEY");
    expect(body).not.toContain("BEGIN OPENSSH PRIVATE KEY");
    expect(body.toLowerCase()).not.toContain("/var/lib/compliance/keys");
    await expect(page.getByTestId("lab-private-key-configured")).toBeVisible();
  });

  test("allowed hosts/task codes visible when lab pilot marked available", async ({
    page,
  }) => {
    const state = createInitialState({
      role: "admin",
      realExecutionAvailable: true,
    });
    // Mock "available" still keeps mock_mode=true in safety-status mock —
    // force connectivity flags for UI rendering of lists.
    state.realAnsibleEnabled = true;
    state.safetyReasons = ["Lab pilot configured (mock e2e)"];
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("lab-allowed-hosts")).toContainText(
      "e2e-linux-01",
    );
    await expect(page.getByTestId("lab-allowed-task-codes")).toContainText(
      "SSH_DISABLE_ROOT_LOGIN",
    );
  });
});
