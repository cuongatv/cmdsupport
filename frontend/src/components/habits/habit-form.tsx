"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  HabitCreate,
  HabitRead,
  TaskPriority,
} from "@/lib/habit-types";
import { cn } from "@/lib/utils";

// 0 = Mon … 6 = Sun. Matches Python's `date.weekday()` AND the
// `personal_habits.active_days` JSONB schema (see decisions.md).
const WEEKDAY_LABELS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const WEEKDAY_TITLES = [
  "Thứ Hai",
  "Thứ Ba",
  "Thứ Tư",
  "Thứ Năm",
  "Thứ Sáu",
  "Thứ Bảy",
  "Chủ Nhật",
];

const PRIORITY_OPTIONS: Array<{ value: TaskPriority; label: string }> = [
  { value: "none", label: "Không có" },
  { value: "low", label: "Thấp" },
  { value: "medium", label: "Trung bình" },
  { value: "high", label: "Cao" },
  { value: "urgent", label: "Khẩn cấp" },
];

const DEFAULT_ACTIVE_DAYS = [0, 1, 2, 3, 4]; // Mon..Fri
const DEFAULT_PREFERRED_TIME = "09:00";
const DEFAULT_DURATION = 30;
const DEFAULT_PRIORITY: TaskPriority = "medium";

/** "HH:MM:SS" → "HH:MM" for the HTML <input type="time"> control. */
function trimTime(value: string): string {
  return value.length >= 5 ? value.slice(0, 5) : value;
}

/** "HH:MM" → "HH:MM:SS" for the API. Already-suffixed values pass through. */
function normalizeTime(value: string): string {
  return value.length === 5 ? `${value}:00` : value;
}

type HabitFormProps = {
  open: boolean;
  initial: HabitRead | null;
  submitting: boolean;
  serverError: string;
  onClose: () => void;
  onSubmit: (body: HabitCreate, mode: "create" | "edit") => Promise<void>;
};

/**
 * Headless dialog wrapper. Internal `HabitFormBody` is keyed by
 * `${initial?.id ?? "new"}-${open}` so re-opening the dialog (or switching
 * which habit to edit) remounts the form and resets every field — same
 * pattern as `DepartmentDialog`. Avoids the useEffect-as-reset trap.
 */
export function HabitForm({
  open,
  initial,
  submitting,
  serverError,
  onClose,
  onSubmit,
}: HabitFormProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {initial ? "Chỉnh sửa thói quen" : "Thêm thói quen mới"}
          </DialogTitle>
          <DialogDescription>
            {initial
              ? "Cập nhật thông tin và lịch lặp lại của thói quen."
              : "Tạo một thói quen lặp lại theo các ngày trong tuần. Bạn có thể đánh dấu hoàn thành mỗi ngày."}
          </DialogDescription>
        </DialogHeader>
        <HabitFormBody
          key={`${initial?.id ?? "new"}-${open ? "open" : "closed"}`}
          initial={initial}
          submitting={submitting}
          serverError={serverError}
          onClose={onClose}
          onSubmit={onSubmit}
        />
      </DialogContent>
    </Dialog>
  );
}

type HabitFormBodyProps = Omit<HabitFormProps, "open">;

function HabitFormBody({
  initial,
  submitting,
  serverError,
  onClose,
  onSubmit,
}: HabitFormBodyProps) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [priority, setPriority] = useState<TaskPriority>(
    initial?.priority ?? DEFAULT_PRIORITY,
  );
  const [preferredTime, setPreferredTime] = useState(
    trimTime(initial?.preferred_time ?? `${DEFAULT_PREFERRED_TIME}:00`),
  );
  const [durationMinutes, setDurationMinutes] = useState<number>(
    initial?.duration_minutes ?? DEFAULT_DURATION,
  );
  const [activeDays, setActiveDays] = useState<number[]>(() => {
    if (!initial) return DEFAULT_ACTIVE_DAYS;
    return [...initial.active_days].sort((a, b) => a - b);
  });
  const [isActive, setIsActive] = useState<boolean>(initial?.is_active ?? true);
  const [validationError, setValidationError] = useState("");

  const toggleDay = (day: number) => {
    setActiveDays((prev) => {
      if (prev.includes(day)) return prev.filter((d) => d !== day);
      const next = [...prev, day];
      next.sort((a, b) => a - b);
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setValidationError("");

    // Client-side validation. The backend (Pydantic) is the security
    // boundary; this is purely UX so the user gets feedback before a
    // round-trip.
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setValidationError("Tên thói quen không được để trống.");
      return;
    }
    if (
      !Number.isFinite(durationMinutes) ||
      durationMinutes < 5 ||
      durationMinutes > 480
    ) {
      setValidationError("Thời lượng phải nằm trong khoảng 5–480 phút.");
      return;
    }
    if (activeDays.length === 0) {
      setValidationError("Chọn ít nhất một ngày trong tuần.");
      return;
    }

    const body: HabitCreate = {
      title: trimmedTitle,
      priority,
      preferred_time: normalizeTime(preferredTime),
      duration_minutes: durationMinutes,
      active_days: activeDays,
      is_active: isActive,
    };
    await onSubmit(body, initial ? "edit" : "create");
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-1">
      {/* Title */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="habit-title">Tên thói quen</Label>
        <Input
          id="habit-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Ví dụ: Đọc sách 30 phút"
          required
          autoFocus
          maxLength={200}
          className="bg-background"
        />
      </div>

      {/* Priority + Time + Duration */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="habit-priority">Mức ưu tiên</Label>
          {/* Native <select>: 5 static options is below the threshold
              where Base UI Select earns its bundle weight. */}
          <select
            id="habit-priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value as TaskPriority)}
            className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {PRIORITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="habit-time">Giờ ưa thích</Label>
          <Input
            id="habit-time"
            type="time"
            value={preferredTime}
            onChange={(e) => setPreferredTime(e.target.value)}
            required
            className="bg-background tabular-nums"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="habit-duration">Thời lượng (phút)</Label>
          <Input
            id="habit-duration"
            type="number"
            min={5}
            max={480}
            step={5}
            value={Number.isFinite(durationMinutes) ? durationMinutes : ""}
            onChange={(e) => {
              const parsed = Number.parseInt(e.target.value, 10);
              setDurationMinutes(Number.isFinite(parsed) ? parsed : 0);
            }}
            required
            className="bg-background tabular-nums"
          />
        </div>
      </div>

      {/* Active days */}
      <div className="flex flex-col gap-1.5">
        <Label>Ngày lặp lại trong tuần</Label>
        <div className="flex flex-wrap items-center gap-1.5">
          {WEEKDAY_LABELS.map((label, idx) => {
            const active = activeDays.includes(idx);
            return (
              <button
                key={idx}
                type="button"
                onClick={() => toggleDay(idx)}
                aria-pressed={active}
                title={WEEKDAY_TITLES[idx]}
                className={cn(
                  // 40px tap target on mobile (meets accessibility floor),
                  // back to 32px on sm+ so the row stays compact in the dialog.
                  "h-10 min-w-[2.5rem] sm:h-8 sm:min-w-[2.25rem] rounded-md border px-2 text-xs font-semibold transition-colors",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Chọn các ngày bạn muốn thực hiện thói quen này.
        </p>
      </div>

      {/* Is active toggle */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="habit-active"
          checked={isActive}
          onCheckedChange={(checked) => setIsActive(checked)}
        />
        <Label htmlFor="habit-active" className="cursor-pointer">
          Đang hoạt động
        </Label>
        <span className="text-[11px] text-muted-foreground">
          Bỏ chọn để lưu trữ thói quen mà không xoá dữ liệu.
        </span>
      </div>

      {(validationError || serverError) && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive flex items-start gap-2">
          <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
            error
          </span>
          <span>{validationError || serverError}</span>
        </p>
      )}

      <div className="flex justify-end gap-2 mt-1">
        <Button
          type="button"
          variant="outline"
          onClick={onClose}
          disabled={submitting}
          className="min-h-[40px] sm:min-h-8"
        >
          Huỷ
        </Button>
        <Button
          type="submit"
          disabled={submitting}
          className="min-h-[40px] sm:min-h-8 bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {submitting
            ? "Đang lưu…"
            : initial
              ? "Cập nhật"
              : "Tạo thói quen"}
        </Button>
      </div>
    </form>
  );
}
