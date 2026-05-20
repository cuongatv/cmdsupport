"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { listDepartmentMembers } from "@/lib/department-api";
import type { MembershipRole } from "@/lib/department-types";
import { listTaskProjects } from "@/lib/task-api";
import {
  createTelegramBindCode,
  disableTelegramBinding,
  listTelegramBindings,
} from "@/lib/telegram-api";
import type { TelegramBinding } from "@/lib/telegram-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";

type Props = {
  departmentId: string;
  isLead: boolean;
  defaultProjectId: string | null;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("vi-VN");
  } catch {
    return iso;
  }
}

function isPendingBinding(binding: TelegramBinding): boolean {
  // The /bind code flow inserts a row with chat_id=0 (sentinel) and
  // bot_status=null before the Telegram group is actually joined. Once the
  // squad lead runs /bind in Telegram and the bot acknowledges, chat_id is
  // updated to the real (negative) supergroup id and bot_status becomes set.
  return binding.chat_id === 0 || binding.bot_status === null;
}

function bindingStatusLabel(binding: TelegramBinding): string {
  if (!binding.is_active) return "Đã huỷ";
  if (isPendingBinding(binding)) return "Đang chờ /bind";
  switch (binding.bot_status) {
    case "joined":
      return "Đã kết nối";
    case "kicked":
      return "Bot bị kick";
    case "migrated":
      return "Đã chuyển nhóm";
    default:
      return binding.bot_status ?? "Đã kết nối";
  }
}

function bindingStatusVariant(
  binding: TelegramBinding,
): "default" | "secondary" | "outline" | "destructive" {
  if (!binding.is_active) return "secondary";
  if (isPendingBinding(binding)) return "outline";
  if (binding.bot_status === "kicked") return "destructive";
  return "default";
}

type BindCodeDisplay = {
  command: string;
  expiresAt: string | null;
};

export function SquadTelegramSection({
  departmentId,
  isLead,
  defaultProjectId,
}: Props) {
  const [bindings, setBindings] = useState<TelegramBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [bindCode, setBindCode] = useState<BindCodeDisplay | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );
  const [disableTarget, setDisableTarget] = useState<TelegramBinding | null>(
    null,
  );
  const [disabling, setDisabling] = useState(false);
  const [disableError, setDisableError] = useState<string | null>(null);

  const loadBindings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTelegramBindings(departmentId);
      setBindings(data);
    } catch (err) {
      setBindings([]);
      setError(getErrorMessage(err, "Không tải được danh sách liên kết Telegram"));
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  useEffect(() => {
    // Deferred load matches the pattern used in the surrounding hub tabs so
    // the React 19 compiler does not flag the set-state chain inside the
    // loader.
    const handle = window.setTimeout(() => {
      void loadBindings();
    }, 0);
    return () => window.clearTimeout(handle);
  }, [loadBindings]);

  const handleGenerate = async () => {
    if (!isLead || !defaultProjectId) return;
    setGenerating(true);
    setError(null);
    setCopyState("idle");
    try {
      const binding = await createTelegramBindCode({
        department_id: departmentId,
        default_task_project_id: defaultProjectId,
      });
      const code = binding.bind_code ?? "";
      setBindCode({
        command: code ? `/bind ${code}` : "/bind",
        expiresAt: binding.bind_code_expires_at,
      });
      await loadBindings();
    } catch (err) {
      setError(getErrorMessage(err, "Không tạo được mã /bind"));
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!bindCode) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(bindCode.command);
        setCopyState("copied");
      } else {
        setCopyState("error");
      }
    } catch {
      setCopyState("error");
    }
  };

  const handleConfirmDisable = async () => {
    if (!disableTarget) return;
    setDisabling(true);
    setDisableError(null);
    try {
      await disableTelegramBinding(disableTarget.id);
      setDisableTarget(null);
      await loadBindings();
    } catch (err) {
      setDisableError(getErrorMessage(err, "Không huỷ được liên kết Telegram"));
    } finally {
      setDisabling(false);
    }
  };

  const generateDisabledReason = !isLead
    ? "Chỉ Lead/Deputy/PO/SM của Squad mới có thể tạo mã /bind."
    : !defaultProjectId
      ? "Squad chưa có TaskProject mặc định. Tạo một dự án công việc trong tab Công việc trước khi liên kết Telegram."
      : null;

  return (
    <div
      className="flex flex-col gap-5"
      data-testid="dept-tab-panel-telegram"
      data-department-id={departmentId}
    >
      {/* Intro */}
      <div className="bg-card rounded-xl border border-border shadow-sahara p-5 flex flex-col gap-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-primary">forum</span>
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <h3 className="text-base font-medium text-foreground">
              Liên kết nhóm Telegram
            </h3>
            <p className="text-sm text-muted-foreground">
              Cho phép Squad nhận thông báo và tạo công việc trực tiếp từ nhóm
              Telegram. Quản trị viên không nhập <code>chat_id</code> thủ công —
              hãy tạo mã <code>/bind CMD-XXXXX</code> tại đây rồi chạy lệnh
              trong nhóm Telegram để hoàn tất liên kết.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs text-muted-foreground">
            {generateDisabledReason ?? "Mã có hiệu lực trong 24 giờ."}
          </div>
          <Button
            data-testid="telegram-generate-bind-code"
            onClick={handleGenerate}
            disabled={!isLead || !defaultProjectId || generating}
            title={generateDisabledReason ?? undefined}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-base mr-1">
              {generating ? "progress_activity" : "qr_code_2"}
            </span>
            {generating ? "Đang tạo mã…" : "Tạo mã /bind"}
          </Button>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2"
          data-testid="telegram-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      {/* Bindings list */}
      {loading ? (
        <div
          className="h-48 w-full bg-muted/40 animate-pulse rounded-xl"
          data-testid="telegram-loading"
        />
      ) : bindings.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sahara">
          <EmptyState
            icon="link_off"
            title="Chưa có liên kết Telegram"
            description="Bấm 'Tạo mã /bind' để lấy lệnh, sau đó chạy trong nhóm Telegram để kết nối."
          />
        </div>
      ) : (
        <div className="bg-card rounded-xl border border-border shadow-sahara overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nhóm Telegram</TableHead>
                <TableHead className="w-44">Chat ID</TableHead>
                <TableHead className="w-40">Trạng thái</TableHead>
                <TableHead className="w-48">Thời điểm liên kết</TableHead>
                <TableHead className="w-32 text-right">Hành động</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bindings.map((binding) => {
                const pending = isPendingBinding(binding);
                const canDisable = isLead && binding.is_active;
                return (
                  <TableRow
                    key={binding.id}
                    data-testid={`telegram-binding-row-${binding.id}`}
                  >
                    <TableCell className="font-medium">
                      {binding.chat_title ?? (
                        <span className="text-muted-foreground italic">
                          (chưa nhận được /bind)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {pending ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        binding.chat_id
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={bindingStatusVariant(binding)}
                        className="text-xs"
                      >
                        {bindingStatusLabel(binding)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {binding.is_active
                        ? formatDateTime(binding.bound_at)
                        : formatDateTime(binding.disabled_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        disabled={!canDisable}
                        onClick={() => {
                          setDisableError(null);
                          setDisableTarget(binding);
                        }}
                        title={
                          canDisable
                            ? "Huỷ liên kết"
                            : isLead
                              ? "Liên kết đã không hoạt động"
                              : "Chỉ Lead/Deputy/PO/SM mới được huỷ"
                        }
                        aria-label="Huỷ liên kết Telegram"
                        data-testid={`telegram-binding-disable-${binding.id}`}
                      >
                        <span className="material-symbols-outlined text-base text-destructive">
                          link_off
                        </span>
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Bind code result dialog */}
      <Dialog
        open={bindCode !== null}
        onOpenChange={(open) => {
          if (!open) {
            setBindCode(null);
            setCopyState("idle");
          }
        }}
      >
        <DialogContent
          className="sm:max-w-md"
          data-testid="telegram-bind-code-dialog"
        >
          <DialogHeader>
            <DialogTitle>Mã liên kết Telegram</DialogTitle>
            <DialogDescription>
              Mở nhóm Telegram, thêm bot vào nhóm, sau đó nhập lệnh dưới đây.
              Mã sẽ hết hạn sau 24 giờ.
            </DialogDescription>
          </DialogHeader>

          {bindCode && (
            <div className="flex flex-col gap-3">
              <div
                className="rounded-lg border border-dashed border-border bg-muted/40 px-3 py-3 font-mono text-sm flex items-center justify-between gap-2"
                data-testid="telegram-bind-code-command"
              >
                <code className="truncate">{bindCode.command}</code>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopy}
                  data-testid="telegram-bind-code-copy"
                >
                  <span className="material-symbols-outlined text-base">
                    {copyState === "copied" ? "check" : "content_copy"}
                  </span>
                  {copyState === "copied" ? "Đã sao chép" : "Sao chép"}
                </Button>
              </div>

              {copyState === "error" && (
                <p className="text-xs text-destructive">
                  Trình duyệt không cho phép sao chép tự động. Hãy chọn và sao
                  chép thủ công.
                </p>
              )}

              <div className="text-xs text-muted-foreground">
                Hết hạn lúc:{" "}
                <span className="text-foreground">
                  {formatDateTime(bindCode.expiresAt)}
                </span>
              </div>

              <ol className="text-sm text-foreground/90 list-decimal pl-5 flex flex-col gap-1">
                <li>Thêm bot CMD Support vào nhóm Telegram của Squad.</li>
                <li>
                  Gửi lệnh ở trên trong nhóm. Bot sẽ phản hồi khi kết nối thành
                  công.
                </li>
                <li>
                  Quay lại trang này — trạng thái liên kết sẽ chuyển sang
                  &ldquo;Đã kết nối&rdquo;.
                </li>
              </ol>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setBindCode(null);
                setCopyState("idle");
              }}
            >
              Đóng
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Disable binding confirm */}
      <Dialog
        open={disableTarget !== null}
        onOpenChange={(open) => {
          if (!open && !disabling) {
            setDisableTarget(null);
            setDisableError(null);
          }
        }}
      >
        <DialogContent data-testid="telegram-disable-dialog">
          <DialogHeader>
            <DialogTitle>Huỷ liên kết Telegram?</DialogTitle>
            <DialogDescription>
              {disableTarget?.chat_title ? (
                <>
                  Nhóm &ldquo;{disableTarget.chat_title}&rdquo; sẽ ngừng nhận
                  thông báo và lệnh từ Squad này. Bạn có thể tạo lại mã /bind
                  sau.
                </>
              ) : (
                <>
                  Liên kết Telegram sẽ bị huỷ. Bạn có thể tạo lại mã /bind sau.
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          {disableError && (
            <p
              role="alert"
              className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
            >
              {disableError}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDisableTarget(null)}
              disabled={disabling}
            >
              Huỷ
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleConfirmDisable}
              disabled={disabling}
              data-testid="telegram-disable-confirm"
            >
              {disabling ? "Đang huỷ…" : "Huỷ liên kết"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SquadTelegramTab — thin wrapper that resolves `isLead` and
// `defaultProjectId` from the surrounding department context before
// rendering the spec-mandated SquadTelegramSection. Lets the department hub
// page stay declarative and avoids leaking the membership/project fetch into
// the parent file.
// ---------------------------------------------------------------------------

const LEAD_ROLES: ReadonlyArray<MembershipRole> = [
  "lead",
  "deputy_lead",
  "product_owner",
  "scrum_master",
];

type SquadTelegramTabProps = {
  departmentId: string;
};

export function SquadTelegramTab({ departmentId }: SquadTelegramTabProps) {
  const { user } = useAuth();
  const [isLead, setIsLead] = useState(false);
  const [defaultProjectId, setDefaultProjectId] = useState<string | null>(null);
  const [resolving, setResolving] = useState(true);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const isAdmin = useMemo(() => user?.role === "admin", [user]);

  const resolve = useCallback(async () => {
    setResolving(true);
    setResolveError(null);
    try {
      const [members, projects] = await Promise.all([
        isAdmin ? Promise.resolve([]) : listDepartmentMembers(departmentId),
        listTaskProjects({ department_id: departmentId }),
      ]);

      if (isAdmin) {
        setIsLead(true);
      } else {
        const mine = members.find(
          (m) => m.employee_id === user?.id && m.is_active,
        );
        setIsLead(
          mine !== undefined && LEAD_ROLES.includes(mine.role),
        );
      }

      const candidate =
        projects.find((p) => !p.is_archived) ?? projects[0] ?? null;
      setDefaultProjectId(candidate ? candidate.id : null);
    } catch (err) {
      setIsLead(false);
      setDefaultProjectId(null);
      setResolveError(getErrorMessage(err, "Không tải được dữ liệu Squad"));
    } finally {
      setResolving(false);
    }
  }, [departmentId, isAdmin, user?.id]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void resolve();
    }, 0);
    return () => window.clearTimeout(handle);
  }, [resolve]);

  if (resolving) {
    return (
      <div
        className="h-48 w-full bg-muted/40 animate-pulse rounded-xl"
        data-testid="telegram-tab-loading"
      />
    );
  }

  if (resolveError) {
    return (
      <div
        role="alert"
        className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2"
        data-testid="telegram-tab-error"
      >
        <span className="material-symbols-outlined text-base">error</span>
        {resolveError}
      </div>
    );
  }

  return (
    <SquadTelegramSection
      departmentId={departmentId}
      isLead={isLead}
      defaultProjectId={defaultProjectId}
    />
  );
}
