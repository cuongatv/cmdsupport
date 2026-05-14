"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { UnitDashboardAggregate } from "@/lib/habit-types";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import {
  useDashboardVersion,
  useFocusBump,
  useUnitsVersion,
} from "@/lib/me-sync";

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function MyUnitsPage() {
  // Re-fetch when either the units surface or the dashboard surface bumps
  // (dashboard bumps include habit mutations, which can shift bucket
  // counts on the unit cards). `useFocusBump()` covers tab refocus.
  const unitsVersion = useUnitsVersion();
  const dashboardVersion = useDashboardVersion();
  useFocusBump();

  const [units, setUnits] = useState<UnitDashboardAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Retry counter — wired to the error band's "Thử lại" button so the user
  // can re-run the fetch after a network blip without leaving the page.
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    // setTimeout(0) keeps setState out of the synchronous effect tick
    // (project convention; same as admin/tasks/page.tsx). The `cancelled`
    // flag prevents stale state writes if the effect re-runs (or the
    // component unmounts) before the in-flight fetch settles.
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void (async () => {
        try {
          // /api/me/units is the dedicated dashboard for the unit switcher —
          // skips the `personal` payload that /api/me/dashboard ships with.
          const data = await api<UnitDashboardAggregate[]>("/api/me/units");
          if (cancelled) return;
          setUnits(data);
        } catch (err) {
          if (cancelled) return;
          setUnits([]);
          setError(getErrorMessage(err, "Không tải được danh sách đơn vị"));
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [unitsVersion, dashboardVersion, reloadTick]);

  return (
    <>
      <PageHeader
        title="Đơn vị của tôi"
        description="Mọi phòng ban và đơn vị bạn đang là thành viên. Nhấn vào một đơn vị để xem công việc của đơn vị đó."
      />

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3"
          role="alert"
        >
          <span className="flex items-start gap-2 flex-1">
            <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
              error_outline
            </span>
            <span>{error}</span>
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={reload}
            className="min-h-[40px] sm:min-h-7 self-start sm:self-auto border-destructive/30 text-destructive hover:bg-destructive/10"
          >
            <span className="material-symbols-outlined text-sm">refresh</span>
            Thử lại
          </Button>
        </div>
      )}

      {loading ? (
        <UnitsGridSkeleton />
      ) : units.length === 0 ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
          <EmptyState
            icon="domain"
            title="Bạn chưa thuộc đơn vị nào"
            description="Liên hệ quản trị viên để được thêm vào một đơn vị. Khi đó, công việc của đơn vị sẽ hiển thị tại đây."
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {units.map((unit) => (
            <UnitCard key={unit.unit_id} unit={unit} />
          ))}
        </div>
      )}
    </>
  );
}

function UnitCard({ unit }: { unit: UnitDashboardAggregate }) {
  const { buckets } = unit;
  return (
    <Link
      href={`/me/units/${unit.unit_id}`}
      className="group flex flex-col gap-4 rounded-xl border border-border bg-card p-5 shadow-sahara transition-colors hover:bg-secondary/30 hover:border-primary/30"
    >
      <div className="flex items-start gap-3">
        <span
          className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0"
          aria-hidden="true"
        >
          <span
            className="material-symbols-outlined text-xl"
            style={{
              fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24",
            }}
          >
            domain
          </span>
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-foreground truncate">
            {unit.unit_name}
          </h3>
          <p className="text-xs text-muted-foreground capitalize truncate">
            {unit.unit_type}
          </p>
        </div>
        <span className="material-symbols-outlined text-base text-muted-foreground/40 group-hover:text-primary transition-colors">
          arrow_forward
        </span>
      </div>

      <div className="grid grid-cols-4 gap-2 pt-3 border-t border-border">
        <BucketCell label="Tổng" value={buckets.total} tone="primary" />
        <BucketCell
          label="Quá hạn"
          value={buckets.overdue}
          tone={buckets.overdue > 0 ? "red" : "muted"}
        />
        <BucketCell
          label="Sắp tới"
          value={buckets.due_soon}
          tone={buckets.due_soon > 0 ? "amber" : "muted"}
        />
        <BucketCell
          label="Chưa hạn"
          value={buckets.not_due_yet}
          tone="muted"
        />
      </div>
    </Link>
  );
}

/**
 * Skeleton grid that mirrors the real UnitCard shape: icon block + title +
 * subtitle, then a 4-cell bucket row underneath. Three placeholder cards
 * fill the responsive grid without committing to a specific column count.
 */
function UnitsGridSkeleton() {
  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
      aria-busy="true"
      aria-label="Đang tải đơn vị"
    >
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-card p-5 shadow-sahara flex flex-col gap-4 animate-pulse"
        >
          <div className="flex items-start gap-3">
            <div className="h-11 w-11 rounded-lg bg-muted shrink-0" />
            <div className="flex-1 flex flex-col gap-1.5 min-w-0">
              <div className="h-5 w-3/4 rounded bg-muted" />
              <div className="h-3 w-1/3 rounded bg-muted" />
            </div>
          </div>
          <div className="grid grid-cols-4 gap-2 pt-3 border-t border-border">
            {[0, 1, 2, 3].map((j) => (
              <div key={j} className="flex flex-col gap-1.5">
                <div className="h-6 w-8 rounded bg-muted" />
                <div className="h-2.5 w-10 rounded bg-muted" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function BucketCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "primary" | "red" | "amber" | "muted";
}) {
  const TONE: Record<typeof tone, string> = {
    primary: "text-primary",
    red: "text-red-700",
    amber: "text-amber-700",
    muted: "text-foreground/80",
  };
  return (
    <div className="flex flex-col gap-0.5">
      <span className={`text-lg font-semibold tabular-nums ${TONE[tone]}`}>
        {value}
      </span>
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
    </div>
  );
}
