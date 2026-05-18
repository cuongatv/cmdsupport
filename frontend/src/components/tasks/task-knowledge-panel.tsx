"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import { FEATURE_AGILE_PHASE_4 } from "@/lib/feature-flags";
import {
  addKnowledgeLink,
  listKnowledgeLinks,
  removeKnowledgeLink,
} from "@/lib/task-api";
import type {
  KnowledgeLinkType,
  TaskKnowledgeLink,
} from "@/lib/task-types";
import { formatTaskDateTime } from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Phase 4 (FEATURE_AGILE_PHASE_4) — Vietnamese task ↔ wiki knowledge-links
// panel. Hidden entirely when the flag is OFF so legacy deployments stay
// untouched. Strings are hardcoded Vietnamese per the project decision to
// avoid pulling in an i18n framework.
//
// The panel surfaces the read-only link list (open under the OFF flag too)
// and gates its add/remove buttons behind the same feature flag the backend
// enforces. The wiki page is referenced by id only — no content read.

type TaskKnowledgePanelProps = {
  taskId: string;
};

const LINK_TYPE_LABELS: Record<KnowledgeLinkType, string> = {
  reference: "Tài liệu tham khảo",
  solution: "Giải pháp",
  blocker: "Điểm nghẽn",
  related: "Liên quan",
};

const LINK_TYPE_BADGE_CLASS: Record<KnowledgeLinkType, string> = {
  reference: "bg-secondary text-secondary-foreground",
  solution:
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-100",
  blocker: "bg-destructive/10 text-destructive",
  related: "bg-primary/15 text-primary",
};

// Simple RFC 4122-ish UUID v1–v5 sanity check. Mirrors the loose validation
// the backend applies — the server rejects anything that does not parse as
// a UUID with 422, so this is a fast UX guard, not a security boundary.
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

function isFlagOn(): boolean {
  return FEATURE_AGILE_PHASE_4;
}

function isKnownLinkType(value: string): value is KnowledgeLinkType {
  return (
    value === "reference" ||
    value === "solution" ||
    value === "blocker" ||
    value === "related"
  );
}

export function TaskKnowledgePanel({ taskId }: TaskKnowledgePanelProps) {
  const [links, setLinks] = React.useState<TaskKnowledgeLink[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string>("");
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const refresh = React.useCallback(async () => {
    if (!isFlagOn()) return;
    setLoading(true);
    setError("");
    try {
      const items = await listKnowledgeLinks(taskId);
      setLinks(items);
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được liên kết tri thức"));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  React.useEffect(() => {
    // Defer to a microtask so we don't trip the
    // `react-hooks/set-state-in-effect` rule the project downgrades to warn.
    const timerId = window.setTimeout(() => {
      refresh();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [refresh]);

  if (!isFlagOn()) {
    // Phase 4 OFF — render nothing. Caller can still mount this component
    // unconditionally; the flag check lives here so the gate is co-located
    // with the feature.
    return null;
  }

  const handleAdded = async () => {
    setDialogOpen(false);
    await refresh();
  };

  const handleRemove = async (wikiPageId: string) => {
    setError("");
    try {
      await removeKnowledgeLink(taskId, wikiPageId);
      await refresh();
    } catch (err) {
      setError(getErrorMessage(err, "Xóa liên kết tri thức thất bại"));
    }
  };

  return (
    <section
      className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4"
      data-testid="knowledge-panel"
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            Tri thức liên quan
          </h2>
          <p className="text-xs text-muted-foreground">
            Gắn các trang wiki liên quan để Claude và đồng đội có ngữ cảnh khi
            xử lý công việc này.
          </p>
        </div>
        <Button
          data-testid="add-knowledge-link-btn"
          onClick={() => setDialogOpen(true)}
          className="bg-primary text-primary-foreground hover:bg-primary/90"
        >
          <span className="material-symbols-outlined mr-1 text-sm">add_link</span>
          Thêm liên kết tri thức
        </Button>
      </header>

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          data-testid="knowledge-panel-error"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div
          className="text-sm text-muted-foreground"
          data-testid="knowledge-panel-loading"
        >
          Đang tải liên kết tri thức…
        </div>
      ) : links.length === 0 ? (
        <div
          className="rounded-lg border border-dashed border-border bg-secondary/30 px-4 py-6 text-center text-sm text-muted-foreground"
          data-testid="knowledge-panel-empty"
        >
          Chưa có liên kết tri thức nào
        </div>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="knowledge-link-list">
          {links.map((link) => {
            const wikiPageId = link.wiki_page_id;
            return (
              <KnowledgeLinkRow
                key={link.id}
                link={link}
                onRemove={
                  wikiPageId ? () => handleRemove(wikiPageId) : undefined
                }
              />
            );
          })}
        </ul>
      )}

      {dialogOpen && (
        <KnowledgeLinkFormDialog
          taskId={taskId}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          onSaved={handleAdded}
        />
      )}
    </section>
  );
}

type KnowledgeLinkRowProps = {
  link: TaskKnowledgeLink;
  onRemove?: () => void;
};

function KnowledgeLinkRow({ link, onRemove }: KnowledgeLinkRowProps) {
  const typeKey: KnowledgeLinkType = isKnownLinkType(link.link_type)
    ? link.link_type
    : "reference";
  const targetId = link.wiki_page_id ?? link.source_id ?? link.id;
  const targetLabel = link.wiki_page_id ? "Wiki" : "Nguồn";
  return (
    <li
      className="flex items-start justify-between gap-2 rounded-lg border border-border bg-background p-3"
      data-testid={`knowledge-link-row-${targetId}`}
    >
      <div className="flex min-w-0 flex-col">
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${LINK_TYPE_BADGE_CLASS[typeKey]}`}
            data-testid={`knowledge-link-type-${targetId}`}
          >
            {LINK_TYPE_LABELS[typeKey]}
          </span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            {targetLabel}
          </span>
          <code className="truncate font-mono text-xs text-foreground">
            {targetId}
          </code>
        </div>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Đã liên kết lúc {formatTaskDateTime(link.created_at)}
        </p>
      </div>
      {onRemove && (
        <Button
          size="sm"
          variant="outline"
          onClick={onRemove}
          data-testid={`knowledge-link-remove-${targetId}`}
          className="text-destructive hover:bg-destructive/10"
        >
          Xóa liên kết
        </Button>
      )}
    </li>
  );
}

type KnowledgeLinkFormDialogProps = {
  taskId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
};

function KnowledgeLinkFormDialog({
  taskId,
  open,
  onOpenChange,
  onSaved,
}: KnowledgeLinkFormDialogProps) {
  const [wikiPageId, setWikiPageId] = React.useState<string>("");
  const [linkType, setLinkType] = React.useState<KnowledgeLinkType>("reference");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string>("");

  const handleSave = async () => {
    setError("");
    const trimmed = wikiPageId.trim();
    if (trimmed === "") {
      setError("Vui lòng nhập mã trang wiki");
      return;
    }
    if (!UUID_RE.test(trimmed)) {
      setError("Mã trang wiki phải là UUID hợp lệ");
      return;
    }
    setSaving(true);
    try {
      await addKnowledgeLink(taskId, trimmed, linkType);
      onSaved();
    } catch (err) {
      // Translate the documented duplicate-link error to Vietnamese.
      if (err instanceof ApiError && err.status === 409) {
        const detail = (err.data as { detail?: { code?: string } } | null)
          ?.detail;
        if (detail?.code === "DUPLICATE_KNOWLEDGE_LINK") {
          setError("Trang wiki này đã được liên kết với công việc");
          setSaving(false);
          return;
        }
      }
      setError(getErrorMessage(err, "Thêm liên kết tri thức thất bại"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        data-testid="knowledge-link-form-dialog"
      >
        <DialogHeader>
          <DialogTitle className="text-xl">Thêm liên kết tri thức</DialogTitle>
        </DialogHeader>

        <div className="mt-2 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="knowledge-link-wiki-page-input">Mã trang wiki</Label>
            <Input
              id="knowledge-link-wiki-page-input"
              data-testid="knowledge-link-wiki-page-input"
              value={wikiPageId}
              onChange={(event) => setWikiPageId(event.target.value)}
              placeholder="ví dụ: 6f2c0d6b-3f4a-4e7e-b6a4-1f1f2c8d4a11"
              className="bg-background font-mono text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              Sao chép mã trang từ URL trang wiki tương ứng.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="knowledge-link-type-select">Loại liên kết</Label>
            <Select
              value={linkType}
              onValueChange={(value) => {
                if (value && isKnownLinkType(value)) setLinkType(value);
              }}
            >
              <SelectTrigger
                id="knowledge-link-type-select"
                data-testid="knowledge-link-type-select"
                className="w-full bg-background"
              >
                <SelectValue placeholder="Chọn loại liên kết" />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(LINK_TYPE_LABELS) as KnowledgeLinkType[]).map(
                  (key) => (
                    <SelectItem key={key} value={key}>
                      {LINK_TYPE_LABELS[key]}
                    </SelectItem>
                  ),
                )}
              </SelectContent>
            </Select>
          </div>

          {error && (
            <p
              className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
              data-testid="knowledge-link-form-error"
            >
              {error}
            </p>
          )}

          <div className="mt-2 flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Hủy
            </Button>
            <Button
              data-testid="knowledge-link-save-btn"
              disabled={saving}
              onClick={handleSave}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? "Đang lưu…" : "Lưu liên kết"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
