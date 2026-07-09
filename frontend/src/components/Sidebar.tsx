"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { RoleBadge } from "@/components/RoleBadge";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/upload", label: "Upload Excel" },
  { href: "/imports", label: "Import Summary" },
  { href: "/records", label: "Records Review" },
  { href: "/needs-review", label: "Needs Review" },
  { href: "/ai-suggestions", label: "AI Suggestions" },
  { href: "/plans", label: "Execution Plans" },
  { href: "/approvals", label: "Job Approval" },
  { href: "/jobs", label: "Job Results" },
  { href: "/settings", label: "Settings / Login" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="brand">
        Compliance Remediation
        <span>Internal operator console · Phase 8A</span>
      </div>
      <nav className="nav" aria-label="Primary">
        {LINKS.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href || pathname.startsWith(`${link.href}/`);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={active ? "active" : undefined}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      <div style={{ marginTop: "auto" }}>
        <RoleBadge />
        <p className="muted" style={{ fontSize: "0.75rem", marginTop: "0.75rem" }}>
          Playbooks are read-only. Excel Remediation text is never executed.
          AI drafts stay non-executable. Token auth is MVP-only.
        </p>
      </div>
    </aside>
  );
}
