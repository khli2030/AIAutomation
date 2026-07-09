import { expect, test } from "@playwright/test";
import ExcelJS from "exceljs";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { createInitialState, installMockApi } from "./mockApi";

/**
 * Phase 7.5 UI happy-path E2E (MOCK_MODE).
 * Intercepts backend HTTP — never calls ansible-runner/playbook/subprocess/SSH.
 */

const EXCEL_HEADERS = [
  "Sector Name",
  "General Department Name",
  "Department Name",
  "Application Name",
  "Device Name",
  "VM Authentication",
  "VM Integration",
  "Section Manager",
  "Last Scan Date Time",
  "Last Compliance Scan Date Time",
  "Config Scan ID",
  "Overall Status",
  "Criticality",
  "Tracking Method",
  "Evaluation Date",
  "Posture Modified Date",
  "Posture Evidence",
  "MBSS Score",
  "Source Check ID",
  "Control Description",
  "Policy ID",
  "Qualys Control ID",
  "RATIONALE",
  "Remediation",
  "Expected Configuration",
];

async function writeSampleXlsx(): Promise<string> {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet("Compliance");
  ws.addRow(EXCEL_HEADERS);
  for (const [device, cid] of [
    ["e2e-linux-01", "CTRL-ROOT-01"],
    ["e2e-linux-02", "CTRL-ROOT-02"],
  ] as const) {
    const row = EXCEL_HEADERS.map(() => "");
    row[EXCEL_HEADERS.indexOf("Device Name")] = device;
    row[EXCEL_HEADERS.indexOf("Overall Status")] = "Failed";
    row[EXCEL_HEADERS.indexOf("Criticality")] = "High";
    row[EXCEL_HEADERS.indexOf("Qualys Control ID")] = cid;
    row[EXCEL_HEADERS.indexOf("Source Check ID")] = `SRC-${cid}`;
    row[EXCEL_HEADERS.indexOf("Control Description")] =
      "SSH PermitRootLogin must be no";
    row[EXCEL_HEADERS.indexOf("RATIONALE")] = "Prevent direct root SSH";
    row[EXCEL_HEADERS.indexOf("Remediation")] =
      "Set PermitRootLogin no in sshd_config";
    row[EXCEL_HEADERS.indexOf("Expected Configuration")] = "PermitRootLogin no";
    row[EXCEL_HEADERS.indexOf("Config Scan ID")] = `SCAN-${cid}`;
    ws.addRow(row);
  }
  const out = path.join(os.tmpdir(), `ui-e2e-${Date.now()}.xlsx`);
  await wb.xlsx.writeFile(out);
  return out;
}

test.describe("Phase 7.5 UI E2E mock workflow", () => {
  test("happy path: upload → validate → plan → dry-run → approve → run", async ({
    page,
  }) => {
    const state = createInitialState();
    await installMockApi(page, state);

    // 1–2. Dashboard + MOCK_MODE banner
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.locator(".mock-banner")).toBeVisible();
    await expect(page.locator(".mock-banner .tag")).toHaveText("MOCK_MODE");
    await expect(page.locator(".mock-banner")).toContainText(
      "no ansible-runner",
    );

    // 3. Upload sample Excel
    const xlsxPath = await writeSampleXlsx();
    await page.getByRole("link", { name: "Upload Excel" }).click();
    await expect(page.getByRole("heading", { name: "Upload Excel" })).toBeVisible();
    await page.locator("#xlsx").setInputFiles(xlsxPath);
    await page.getByRole("button", { name: "Upload" }).click();
    await expect(
      page.getByRole("heading", { name: "Upload accepted" }),
    ).toBeVisible();
    await expect(page.getByText("batch_id")).toBeVisible();
    await expect(page.locator(".stat .value").first()).toContainText("1");
    fs.unlinkSync(xlsxPath);

    // 4–5. Import Summary → Validate
    await page.getByRole("link", { name: "Open import summary" }).click();
    await expect(
      page.getByRole("heading", { name: "Import Summary" }),
    ).toBeVisible();
    await page.locator("#batch").selectOption("1");
    await expect(page.getByRole("heading", { name: /Batch #1/ })).toBeVisible();
    await page.getByRole("button", { name: "Validate batch" }).click();
    await expect(
      page.getByText("Validated: 2 READY_FOR_PLAN, 0 NEEDS_REVIEW"),
    ).toBeVisible();
    await expect(page.locator(".stat .label", { hasText: "ready_for_plan" })).toBeVisible();
    await expect(page.locator(".stat").filter({ hasText: "ready_for_plan" }).locator(".value")).toHaveText("2");

    // 6–7. Records Review — READY_FOR_PLAN
    await page.getByRole("link", { name: "Records Review" }).click();
    await expect(
      page.getByRole("heading", { name: "Records Review" }),
    ).toBeVisible();
    await page.locator("select").first().selectOption("1");
    await page.locator("select").nth(1).selectOption("READY_FOR_PLAN");
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page.getByText("e2e-linux-01")).toBeVisible();
    await expect(
      page.locator("table.data .badge", { hasText: "READY_FOR_PLAN" }).first(),
    ).toBeVisible();

    // Confirm remediation is display-only (no execute control on records page)
    await page.getByText("e2e-linux-01").click();
    await expect(page.getByText(/never executed/i).first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: /execute playbook|run ansible/i }),
    ).toHaveCount(0);

    // 8. Generate execution plan (from Import Summary)
    await page.getByRole("link", { name: "Import Summary" }).click();
    await page.locator("#batch").selectOption("1");
    // Re-validate so Generate plan enables (page remount may clear local validation)
    await page.getByRole("button", { name: "Validate batch" }).click();
    await expect(page.getByRole("button", { name: "Generate plan" })).toBeEnabled({
      timeout: 10_000,
    });
    await page.getByRole("button", { name: "Generate plan" }).click();
    await expect(page.getByText(/Plan #1 created/)).toBeVisible();

    // 9. Execution Plans — list plan + jobs
    await page.getByRole("link", { name: "Execution Plans" }).click();
    await expect(
      page.getByRole("heading", { name: "Execution Plans" }),
    ).toBeVisible();
    await page.locator("table.data tbody tr").first().click();
    await expect(page.getByText("SSH_DISABLE_ROOT_LOGIN")).toBeVisible();
    await expect(
      page.locator("table.data .badge", { hasText: "waiting_dry_run" }),
    ).toBeVisible();

    // 10. Open job (Approvals)
    await page.goto("/approvals?jobId=1");
    await expect(page.getByRole("heading", { name: "Job Approval" })).toBeVisible();
    await expect(page.getByText(/Job #1/)).toBeVisible();
    await expect(
      page.locator(".badge", { hasText: "waiting_dry_run" }).first(),
    ).toBeVisible();

    // 11. Mock dry-run
    await page.getByRole("button", { name: "Run mock dry-run" }).click();
    await expect(page.getByText(/Mock dry-run complete/)).toBeVisible();
    await expect(
      page.locator(".badge", { hasText: "dry_run_success" }).first(),
    ).toBeVisible();

    // 12. Dry-run results with result_type=dry_run
    await expect(
      page.getByRole("heading", { name: /Dry-run results \(result_type=dry_run\)/ }),
    ).toBeVisible();
    await expect(
      page.locator("table.data td.mono", { hasText: "dry_run" }).first(),
    ).toBeVisible();
    await expect(page.getByText("e2e-linux-01")).toBeVisible();

    // 13. Approve only after dry_run_success
    const approveBtn = page.getByRole("button", { name: "Approve", exact: true });
    await expect(approveBtn).toBeEnabled();
    await approveBtn.click();
    await expect(page.getByText(/Job #1 approved/)).toBeVisible();
    await expect(
      page.locator(".badge", { hasText: "approved" }).first(),
    ).toBeVisible();

    // Dry-run button should no longer appear after leaving waiting_dry_run
    await expect(
      page.getByRole("button", { name: "Run mock dry-run" }),
    ).toHaveCount(0);

    // 14. Mock execution
    const runBtn = page.getByRole("button", { name: "Run mock execution" });
    await expect(runBtn).toBeEnabled();
    await runBtn.click();
    await expect(page.getByText(/Mock run complete/)).toBeVisible();

    // 15–16. Job results page — run vs dry_run + final status
    await page.getByRole("link", { name: "View all results" }).click();
    await expect(page.getByRole("heading", { name: /Job #1 results/ })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Dry-run results \(result_type=dry_run\)/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Run results \(result_type=run\)/ }),
    ).toBeVisible();
    await expect(page.locator("body")).toContainText("success");
    // Both result types present in tables
    await expect(page.getByText("dry_run").first()).toBeVisible();
    await expect(page.getByText("run").first()).toBeVisible();

    // 17. No UI page allows editing Ansible playbooks
    for (const route of [
      "/",
      "/upload",
      "/imports",
      "/records",
      "/needs-review",
      "/ai-suggestions",
      "/plans",
      "/approvals",
      "/jobs",
      "/settings",
    ]) {
      await page.goto(route);
      await expect(
        page.getByRole("button", {
          name: /edit playbook|save playbook|write playbook/i,
        }),
      ).toHaveCount(0);
      await expect(page.locator('textarea[name*="playbook" i]')).toHaveCount(0);
      await expect(page.locator('input[name*="playbook" i]')).toHaveCount(0);
    }
    await expect(page.getByText(/Playbooks are read-only/i).first()).toBeVisible();

    // 18. AI generated_playbook is read-only and cannot be executed
    await page.goto("/ai-suggestions");
    await expect(
      page.getByRole("heading", { name: "AI Suggestions" }),
    ).toBeVisible();
    await page.locator("table.data tbody tr").first().click();
    await expect(
      page.getByRole("heading", { name: /generated_playbook \(read-only\)/ }),
    ).toBeVisible();
    await expect(page.getByText(/AI DRAFT — NOT EXECUTABLE/)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /execute|run playbook|apply draft/i }),
    ).toHaveCount(0);
    // Convert button exists but only for approved; no enable toggle
    await expect(
      page.getByRole("button", { name: "Convert to disabled catalog" }),
    ).toBeVisible();
    await expect(page.getByLabel(/enable catalog|is_enabled/i)).toHaveCount(0);
  });
});
