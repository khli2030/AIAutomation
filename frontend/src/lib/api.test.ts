import { describe, expect, it } from "vitest";
import { DEFAULT_API_BASE, getApiBase } from "@/lib/api";

describe("api client safety", () => {
  it("defaults to loopback API base", () => {
    expect(DEFAULT_API_BASE).toBe("http://127.0.0.1:8000");
  });

  it("getApiBase strips trailing slash", () => {
    const prev = process.env.NEXT_PUBLIC_API_URL;
    process.env.NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000/";
    expect(getApiBase()).toBe("http://127.0.0.1:8000");
    process.env.NEXT_PUBLIC_API_URL = prev;
  });

  it("does not embed a hardcoded admin token in the module source", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const src = fs.readFileSync(
      path.join(process.cwd(), "src/lib/api.ts"),
      "utf8",
    );
    expect(src).not.toMatch(/ADMIN_TOKEN\s*=\s*["'][^"']+["']/);
    expect(src).not.toMatch(/VIEWER_TOKEN\s*=\s*["'][^"']+["']/);
    expect(src).not.toMatch(/OPERATOR_TOKEN\s*=\s*["'][^"']+["']/);
    expect(src).not.toMatch(/APPROVER_TOKEN\s*=\s*["'][^"']+["']/);
    expect(src).toContain("enable: false");
    expect(src).toContain("/auth/me");
  });
});
