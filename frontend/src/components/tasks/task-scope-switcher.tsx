"use client";

/**
 * Switch between the personal task board (`/me/tasks`) and the team/department
 * board (`/admin/tasks`). Visually mirrors the "Phạm vi" chip group on the
 * weekly calendar page (`/me/calendar`) so the two surfaces feel like part of
 * the same workspace shell.
 *
 * Both target pages already exist; this component is a navigation shell —
 * clicking a chip is a route push, not a state change. The component knows
 * its own active tab from the `current` prop the page passes in.
 */

import Link from "next/link";
import { cn } from "@/lib/utils";

export type TaskScopeKind = "personal" | "team";

const TABS: ReadonlyArray<{
  kind: TaskScopeKind;
  label: string;
  href: string;
  icon: string;
}> = [
  { kind: "personal", label: "Cá nhân", href: "/me/tasks", icon: "person" },
  { kind: "team", label: "Đơn vị", href: "/admin/tasks", icon: "domain" },
];

export function TaskScopeSwitcher({ current }: { current: TaskScopeKind }) {
  return (
    <div
      className="rounded-xl border border-border bg-card shadow-sahara p-3 sm:p-4"
      role="tablist"
      aria-label="Phạm vi công việc"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mr-2">
          Phạm vi
        </span>
        {TABS.map((tab) => {
          const active = tab.kind === current;
          return (
            <Link
              key={tab.kind}
              href={tab.href}
              role="tab"
              aria-selected={active}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-2 sm:py-1 min-h-[40px] sm:min-h-7 text-xs font-medium transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-foreground hover:bg-secondary/50",
              )}
            >
              <span
                className="material-symbols-outlined text-[14px]"
                style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 18" }}
                aria-hidden="true"
              >
                {tab.icon}
              </span>
              <span className="truncate max-w-[180px]">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
