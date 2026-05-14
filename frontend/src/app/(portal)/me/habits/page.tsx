"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  createHabit,
  deleteHabit,
  listHabits,
  updateHabit,
  upsertOccurrence,
} from "@/lib/habit-api";
import type {
  HabitCreate,
  HabitOccurrenceStatus,
  HabitRead,
} from "@/lib/habit-types";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { HabitForm } from "@/components/habits/habit-form";
import { HabitCard } from "@/components/habits/habit-card";
import {
  bumpAfterHabitMutation,
  bumpAfterOccurrenceToggle,
  useFocusBump,
  useHabitsVersion,
} from "@/lib/me-sync";
import { cn } from "@/lib/utils";

/** Local-tz YYYY-MM-DD for "today". Personal habits live in the user's wall
 * clock, not UTC — `toISOString().slice(0,10)` would jump days late at
 * night in Asia/Ho_Chi_Minh. */
function todayLocalIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function MeHabitsPage() {
  // Subscribe to cross-surface invalidations. Habit C/U/D bump habits +
  // calendar + dashboard; the today-toggle deliberately skips bumping
  // `habits` so the optimistic toggle state below isn't clobbered by a
  // refetch.
  const habitsVersion = useHabitsVersion();
  useFocusBump();

  const [habits, setHabits] = useState<HabitRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [includeInactive, setIncludeInactive] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  // Today's optimistic occurrence states, keyed by habit id. The page
  // intentionally does not seed these from a server fetch — keeping it
  // simple per the plan's "or optimistic update — keep simple" guidance.
  const [todayStates, setTodayStates] = useState<
    Record<string, HabitOccurrenceStatus | null>
  >({});
  const [pendingByHabit, setPendingByHabit] = useState<
    Record<string, HabitOccurrenceStatus | "undo" | null>
  >({});

  // Form / dialog state
  const [formOpen, setFormOpen] = useState(false);
  const [editingHabit, setEditingHabit] = useState<HabitRead | null>(null);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  // Archive confirmation state
  const [archiveTarget, setArchiveTarget] = useState<HabitRead | null>(null);
  const [archiveSubmitting, setArchiveSubmitting] = useState(false);
  const [archiveError, setArchiveError] = useState("");

  const today = useMemo(() => todayLocalIso(), []);

  const reload = useCallback(() => {
    setReloadTick((t) => t + 1);
  }, []);

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    // setTimeout(0) defers the setLoading + fetch chain past the effect tick
    // to silence the downgraded `react-hooks/set-state-in-effect` lint. Same
    // pattern as the other /me pages.
    const timerId = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void (async () => {
        try {
          // When the toggle is ON, hit the include_inactive endpoint
          // directly (returns the full superset). When OFF, use the
          // default listHabits() wrapper which returns active-only.
          const data = includeInactive
            ? await api<HabitRead[]>("/api/me/habits?include_inactive=true")
            : await listHabits();
          if (cancelled) return;
          setHabits(data);
        } catch (err) {
          if (cancelled) return;
          setHabits([]);
          setError(getErrorMessage(err, "Không tải được danh sách thói quen"));
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [includeInactive, reloadTick, habitsVersion]);

  // ---------------------------------------------------------------------------
  // Form handlers
  // ---------------------------------------------------------------------------
  const openCreate = useCallback(() => {
    setEditingHabit(null);
    setFormError("");
    setFormOpen(true);
  }, []);

  const openEdit = useCallback((habit: HabitRead) => {
    setEditingHabit(habit);
    setFormError("");
    setFormOpen(true);
  }, []);

  const closeForm = useCallback(() => {
    if (formSubmitting) return;
    setFormOpen(false);
    setEditingHabit(null);
    setFormError("");
  }, [formSubmitting]);

  const handleSubmit = useCallback(
    async (body: HabitCreate, mode: "create" | "edit") => {
      setFormSubmitting(true);
      setFormError("");
      try {
        if (mode === "edit" && editingHabit) {
          await updateHabit(editingHabit.id, body);
        } else {
          await createHabit(body);
        }
        setFormOpen(false);
        setEditingHabit(null);
        // Broadcast to habits + calendar + dashboard surfaces.
        bumpAfterHabitMutation();
      } catch (err) {
        setFormError(
          getErrorMessage(
            err,
            mode === "edit"
              ? "Không cập nhật được thói quen"
              : "Không tạo được thói quen",
          ),
        );
      } finally {
        setFormSubmitting(false);
      }
    },
    [editingHabit],
  );

  // ---------------------------------------------------------------------------
  // Archive handlers
  // ---------------------------------------------------------------------------
  const requestArchive = useCallback((habit: HabitRead) => {
    setArchiveTarget(habit);
    setArchiveError("");
  }, []);

  const cancelArchive = useCallback(() => {
    if (archiveSubmitting) return;
    setArchiveTarget(null);
    setArchiveError("");
  }, [archiveSubmitting]);

  const confirmArchive = useCallback(async () => {
    if (!archiveTarget) return;
    setArchiveSubmitting(true);
    setArchiveError("");
    try {
      await deleteHabit(archiveTarget.id);
      setArchiveTarget(null);
      // Broadcast to habits + calendar + dashboard surfaces.
      bumpAfterHabitMutation();
    } catch (err) {
      setArchiveError(getErrorMessage(err, "Không lưu trữ được thói quen"));
    } finally {
      setArchiveSubmitting(false);
    }
  }, [archiveTarget]);

  // ---------------------------------------------------------------------------
  // Today's occurrence toggle
  // ---------------------------------------------------------------------------
  const handleToggleToday = useCallback(
    async (
      habit: HabitRead,
      state: HabitOccurrenceStatus,
      label: HabitOccurrenceStatus | "undo",
    ) => {
      // Optimistic: flip the local state right away so the buttons reflect
      // intent during the round-trip. On error, revert to whatever was
      // there before.
      const previous = todayStates[habit.id];
      setPendingByHabit((prev) => ({ ...prev, [habit.id]: label }));
      setTodayStates((prev) => ({ ...prev, [habit.id]: state }));
      try {
        await upsertOccurrence(habit.id, today, { state });
        // Bump calendar + dashboard only — deliberately NOT habits, so
        // the optimistic local toggle state above isn't clobbered by a
        // refetch of the habit list on this page.
        bumpAfterOccurrenceToggle();
      } catch (err) {
        // Revert optimistic update.
        setTodayStates((prev) => ({ ...prev, [habit.id]: previous ?? null }));
        setError(getErrorMessage(err, "Không cập nhật được trạng thái"));
      } finally {
        setPendingByHabit((prev) => ({ ...prev, [habit.id]: null }));
      }
    },
    [today, todayStates],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <>
      <PageHeader
        title="Thói quen"
        description="Quản lý các thói quen lặp lại hàng tuần. Đánh dấu hoàn thành mỗi ngày để duy trì chuỗi tích cực."
        action={
          <Button
            type="button"
            onClick={openCreate}
            className="min-h-[40px] sm:min-h-8 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Thêm thói quen
          </Button>
        }
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
            className="min-h-[40px] sm:min-h-7 self-start sm:self-auto px-2 border-destructive/30 text-destructive hover:bg-destructive/10"
          >
            <span className="material-symbols-outlined text-sm">refresh</span>
            Thử lại
          </Button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card shadow-sahara px-4 py-3">
        <div className="flex items-center gap-2">
          <Checkbox
            id="habits-include-inactive"
            checked={includeInactive}
            onCheckedChange={(checked) => setIncludeInactive(checked)}
          />
          <label
            htmlFor="habits-include-inactive"
            className="text-sm text-foreground cursor-pointer select-none"
          >
            Hiển thị đã lưu trữ
          </label>
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {loading
            ? "Đang tải…"
            : habits.length === 0
              ? "0 thói quen"
              : `${habits.length} thói quen`}
        </span>
      </div>

      {/* Habit list */}
      {loading ? (
        <HabitListSkeleton />
      ) : habits.length === 0 ? (
        <div className="rounded-xl border border-border bg-card shadow-sahara">
          <EmptyState
            icon="self_improvement"
            title="Chưa có thói quen nào — bắt đầu xây dựng thói quen tốt!"
            description="Tạo thói quen đầu tiên để theo dõi tiến độ hàng tuần và hình thành lối sống lành mạnh."
            action={
              <Button
                type="button"
                onClick={openCreate}
                className="min-h-[40px] sm:min-h-8 bg-primary text-primary-foreground hover:bg-primary/90"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                Thêm thói quen
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {habits.map((habit) => (
            <HabitCard
              key={habit.id}
              habit={habit}
              todayState={todayStates[habit.id]}
              pending={pendingByHabit[habit.id] ?? null}
              onEdit={openEdit}
              onArchive={requestArchive}
              onToggle={handleToggleToday}
            />
          ))}
        </div>
      )}

      {/* Create / Edit dialog */}
      <HabitForm
        open={formOpen}
        initial={editingHabit}
        submitting={formSubmitting}
        serverError={formError}
        onClose={closeForm}
        onSubmit={handleSubmit}
      />

      {/* Archive confirmation */}
      <Dialog
        open={archiveTarget !== null}
        onOpenChange={(next) => {
          if (!next) cancelArchive();
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Lưu trữ thói quen này?</DialogTitle>
            <DialogDescription>
              Thói quen{" "}
              <span className="font-semibold text-foreground">
                {archiveTarget?.title}
              </span>{" "}
              sẽ được lưu trữ và biến mất khỏi danh sách hoạt động. Dữ liệu
              lịch sử vẫn được giữ lại và bạn có thể khôi phục bằng cách bật
              lại trạng thái “Đang hoạt động” trong cửa sổ chỉnh sửa.
            </DialogDescription>
          </DialogHeader>

          {archiveError && (
            <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive flex items-start gap-2">
              <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
                error
              </span>
              <span>{archiveError}</span>
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button
              type="button"
              variant="outline"
              onClick={cancelArchive}
              disabled={archiveSubmitting}
              className="min-h-[40px] sm:min-h-8"
            >
              Huỷ
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmArchive}
              disabled={archiveSubmitting}
              className={cn("min-h-[40px] sm:min-h-8", archiveSubmitting && "opacity-70")}
            >
              <span className="material-symbols-outlined text-sm">archive</span>
              {archiveSubmitting ? "Đang lưu trữ…" : "Lưu trữ"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function HabitListSkeleton() {
  // Two faux cards on desktop (single column on mobile) — enough to signal
  // "content is loading" without simulating real data shape.
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-card shadow-sahara p-4 flex flex-col gap-3 animate-pulse"
        >
          <div className="h-5 w-2/3 rounded bg-muted" />
          <div className="flex gap-2">
            <div className="h-4 w-16 rounded bg-muted" />
            <div className="h-4 w-20 rounded bg-muted" />
          </div>
          <div className="flex gap-1.5">
            {Array.from({ length: 7 }).map((_, j) => (
              <div key={j} className="h-6 w-7 rounded bg-muted" />
            ))}
          </div>
          <div className="h-7 w-1/3 self-end rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}
