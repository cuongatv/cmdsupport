"use client";

import * as React from "react";
import { FEATURE_AGILE_PHASE_5 } from "@/lib/feature-flags";
import type { TaskGovernanceAdvisory } from "@/lib/task-types";

// Phase 5 (FEATURE_AGILE_PHASE_5) — non-blocking Stage A governance toast.
// The backend records a `permission_denied_advisory` audit row when an
// actor lacks an `agile.*` permission. The mutation itself succeeds; the
// toast is the user-facing breadcrumb so operators know they should ask
// for the missing permission before Stage B starts hard-blocking.
//
// Hidden entirely when the flag is OFF so legacy deployments stay
// untouched. Mirrors the WIP advisory toast styling (Phase 1) to stay
// visually coherent — same amber palette, same dismiss affordance.

type GovernanceAdvisoryToastProps = {
  advisories: TaskGovernanceAdvisory[];
  onDismiss?: () => void;
};

// Per-permission Vietnamese labels. The fallback uses the raw permission
// string so newly-introduced governance permissions still surface a useful
// hint without a UI deploy.
const PERMISSION_LABEL: Record<string, string> = {
  "agile.wip.override":
    "Bạn không có quyền vượt giới hạn việc đang làm (agile.wip.override)",
  "agile.dod.bypass":
    "Bạn không có quyền bỏ qua điều kiện Hoàn thành (agile.dod.bypass)",
  "agile.sprint.close":
    "Bạn không có quyền đóng Sprint (agile.sprint.close)",
};

function describe(advisory: TaskGovernanceAdvisory): string {
  return (
    PERMISSION_LABEL[advisory.permission] ??
    `Bạn không có quyền ${advisory.permission}`
  );
}

export function GovernanceAdvisoryToast({
  advisories,
  onDismiss,
}: GovernanceAdvisoryToastProps) {
  if (!FEATURE_AGILE_PHASE_5) return null;
  if (!advisories || advisories.length === 0) return null;

  return (
    <div
      className="flex items-start justify-between gap-3 rounded-lg border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-400/40 dark:bg-amber-950/30 dark:text-amber-100"
      role="status"
      data-testid="governance-advisory-toast"
    >
      <div className="flex items-start gap-2">
        <span className="material-symbols-outlined text-base">policy</span>
        <div className="flex flex-col gap-0.5">
          <span className="font-medium">Cảnh báo khuyến nghị</span>
          <ul
            className="flex list-disc flex-col gap-0.5 pl-4 text-xs text-amber-800/90 dark:text-amber-100/80"
            data-testid="governance-advisory-toast-list"
          >
            {advisories.map((adv) => (
              <li
                key={adv.permission}
                data-testid={`governance-advisory-item-${adv.permission}`}
              >
                {describe(adv)}
              </li>
            ))}
          </ul>
          <span className="mt-1 text-xs text-amber-800/90 dark:text-amber-100/80">
            Đây chỉ là cảnh báo — thao tác vẫn được ghi nhận.
          </span>
        </div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md p-1 text-amber-700 hover:bg-amber-100 dark:text-amber-200 dark:hover:bg-amber-900/40"
          aria-label="Đóng cảnh báo"
          data-testid="governance-advisory-toast-dismiss"
        >
          <span className="material-symbols-outlined text-sm">close</span>
        </button>
      )}
    </div>
  );
}
