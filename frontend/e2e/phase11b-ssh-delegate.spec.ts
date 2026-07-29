import { expect, test } from "@playwright/test";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 11B — SSH delegate execution mode UI (mocked API).
 */

test.describe("Phase 11B SSH delegate execution mode", () => {
  test("Safety page shows local execution mode by default", async ({ page }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);

    await page.goto("/safety");
    await expect(page.getByTestId("execution-mode-badge")).toBeVisible();
    await expect(page.getByTestId("safety-execution-mode")).toHaveText("local");
    await expect(page.getByTestId("lab-execution-mode")).toHaveText("local");
  });

  test("no real apply/run button exists", async ({ page }) => {
    const state = createInitialState({ role: "admin" });
    await installMockApi(page, state);
    await page.goto("/safety");
    await expect(page.getByTestId("no-real-apply-panel")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /real apply|apply\/run|Run apply/i }),
    ).toHaveCount(0);
  });
});
