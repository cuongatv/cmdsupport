"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/task-api";
import type { Notification } from "@/lib/task-types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const POLL_INTERVAL_MS = 30_000;

// Keys MUST mirror the verb strings emitted by the backend
// (`app/services/task_notification_service.py`): `assigned`, `mentioned`,
// `commented`, `state_changed`, `due_soon`. The fallback covers any future
// notification verb the backend may add.
const SUBTITLE_BY_TYPE: Record<string, string> = {
  assigned: "Bạn được giao công việc",
  mentioned: "Bạn được nhắc đến",
  commented: "Có bình luận mới",
  state_changed: "Trạng thái công việc thay đổi",
  due_soon: "Công việc sắp đến hạn",
};
const SUBTITLE_FALLBACK = "Thông báo công việc";

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function NotificationBadge() {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const userId = user?.id ?? null;

  useEffect(() => {
    if (!userId) return;

    let intervalId: number | null = null;
    let initialId: number | null = null;
    let cancelled = false;

    const load = async () => {
      try {
        const data = await listNotifications({
          unread_only: true,
          limit: 10,
        });
        if (cancelled) return;
        setItems(data);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(getErrorMessage(err, "Không thể tải thông báo"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    const tick = () => {
      setLoading(true);
      void load();
    };

    const start = () => {
      if (intervalId !== null) return;
      initialId = window.setTimeout(tick, 0);
      intervalId = window.setInterval(tick, POLL_INTERVAL_MS);
    };

    const stop = () => {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
      if (initialId !== null) {
        window.clearTimeout(initialId);
        initialId = null;
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        start();
      } else {
        stop();
      }
    };

    if (document.visibilityState === "visible") {
      start();
    }
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      stop();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [userId]);

  if (!user) return null;

  const unreadCount = items.length;

  const handleClickNotification = async (n: Notification) => {
    setOpen(false);
    setItems((prev) => prev.filter((x) => x.id !== n.id));
    try {
      await markNotificationRead(n.id);
    } catch {
      // best-effort; next poll will resync if it failed
    }
    if (n.task_id) {
      // The task detail UI is a modal on `/admin/tasks` (no per-task route
      // exists); the listing page reads `?task=<id>` and auto-opens the panel.
      router.push(`/admin/tasks?task=${encodeURIComponent(n.task_id)}`);
    }
  };

  const handleMarkAllRead = async () => {
    const snapshot = items;
    setItems([]);
    setError(null);
    try {
      await markAllNotificationsRead();
    } catch (err) {
      setItems(snapshot);
      setError(getErrorMessage(err, "Không thể đánh dấu thông báo"));
    }
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        data-testid="notification-badge"
        data-unread-count={unreadCount}
        aria-label="Thông báo"
        className="relative inline-flex items-center justify-center w-9 h-9 rounded-full hover:bg-black/[0.04] transition-colors text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <span
          className="material-symbols-outlined text-[20px]"
          style={{
            fontVariationSettings:
              "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20",
          }}
        >
          notifications
        </span>
        {unreadCount > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-destructive text-destructive-foreground text-[10px] font-semibold leading-none ring-2 ring-background"
            data-testid="notification-badge-count"
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        className="w-[360px] max-w-[calc(100vw-1.5rem)] p-0"
      >
        <div className="flex items-center justify-between gap-3 px-3 py-2.5 border-b border-border">
          <span className="text-sm font-semibold text-foreground">Thông báo</span>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={() => void handleMarkAllRead()}
              className="text-xs text-primary hover:underline"
              data-testid="notification-mark-all-read"
            >
              Đánh dấu tất cả đã đọc
            </button>
          )}
        </div>
        <div
          className="max-h-[420px] overflow-y-auto"
          data-testid="notification-list"
        >
          {loading && items.length === 0 ? (
            <div className="px-3 py-6 text-center text-sm text-muted-foreground">
              Đang tải…
            </div>
          ) : error ? (
            <div
              className="px-3 py-6 text-center text-sm text-destructive"
              data-testid="notification-error"
            >
              {error}
            </div>
          ) : items.length === 0 ? (
            <div
              className="px-3 py-6 text-center text-sm text-muted-foreground"
              data-testid="notification-empty"
            >
              Không có thông báo mới
            </div>
          ) : (
            items.map((n) => {
              const subtitle =
                SUBTITLE_BY_TYPE[n.notification_type] ?? SUBTITLE_FALLBACK;
              const taskMissing = n.task_id === null;
              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => void handleClickNotification(n)}
                  className="w-full text-left flex flex-col gap-1 px-3 py-2.5 border-b border-border last:border-b-0 hover:bg-muted/50 transition-colors"
                  data-testid={`notification-item-${n.id}`}
                  data-task-id={n.task_id ?? ""}
                >
                  <span className="text-[11px] uppercase tracking-wider text-muted-foreground/80">
                    {subtitle}
                  </span>
                  <span className="text-sm font-medium text-foreground line-clamp-2">
                    {n.title}
                  </span>
                  {n.body && (
                    <span className="text-xs text-muted-foreground line-clamp-2">
                      {n.body}
                    </span>
                  )}
                  <span className="text-[11px] text-muted-foreground/70">
                    {formatRelativeTime(n.created_at)}
                    {taskMissing && " · Công việc đã bị xóa"}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
