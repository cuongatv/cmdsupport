"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CATEGORY_LABELS, STATUS_LABELS, STATUS_TONES } from "./constants";
import type { AdminIdea } from "./types";

export function AdminIdeaDetail({
  idea,
  open,
  onOpenChange,
  onUpdated,
  onDeleted,
}: {
  idea: AdminIdea | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUpdated: (next: AdminIdea) => void;
  onDeleted: (id: string) => void;
}) {
  const [status, setStatus] = useState<string>(idea?.status ?? "new");
  const [category, setCategory] = useState<string>(idea?.category ?? "feature");
  const [notes, setNotes] = useState<string>(idea?.admin_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Re-sync form state when a different idea is loaded.
  useEffect(() => {
    if (idea) {
      setStatus(idea.status);
      setCategory(idea.category);
      setNotes(idea.admin_notes ?? "");
      setErr(null);
    }
  }, [idea?.id, idea]);

  if (!idea) return null;

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const next = await api<AdminIdea>(`/api/admin/ideas/${idea.id}`, {
        method: "PATCH",
        body: { status, category, admin_notes: notes },
      });
      onUpdated(next);
      onOpenChange(false);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Lỗi khi cập nhật.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirm("Xoá góp ý này? Hành động không thể hoàn tác.")) return;
    setSaving(true);
    setErr(null);
    try {
      await api(`/api/admin/ideas/${idea.id}`, { method: "DELETE" });
      onDeleted(idea.id);
      onOpenChange(false);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Lỗi khi xoá.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                STATUS_TONES[idea.status] ?? "bg-muted text-foreground"
              }`}
            >
              {STATUS_LABELS[idea.status] ?? idea.status}
            </span>
            <span>{idea.title || "Góp ý"}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Contributor info */}
          <section className="rounded-xl border border-border bg-muted/30 p-4 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <Field label="Người gửi" value={idea.contributor_name} />
            <Field label="Đơn vị" value={idea.contributor_department} />
            <Field label="Điện thoại" value={idea.contributor_phone} mono />
            <Field label="Email" value={idea.contributor_email} mono />
            <Field
              label="Đã gửi lúc"
              value={new Date(idea.created_at).toLocaleString("vi-VN")}
            />
            <Field
              label="Loại"
              value={CATEGORY_LABELS[idea.category] ?? idea.category}
            />
          </section>

          {/* Body */}
          <section className="space-y-3">
            <Block label="Mô tả ý tưởng" value={idea.description} />
            {idea.current_pain && (
              <Block label="Vấn đề hiện tại" value={idea.current_pain} />
            )}
            {idea.expected_benefit && (
              <Block label="Lợi ích mong đợi" value={idea.expected_benefit} />
            )}
            {idea.reference_system && (
              <Block
                label="Hệ thống tham khảo"
                value={idea.reference_system}
                mono
              />
            )}
          </section>

          {/* Images */}
          {idea.images.length > 0 && (
            <section>
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Ảnh đính kèm
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {idea.images.map((img) => (
                  <a
                    key={img.id}
                    href={img.url ?? "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="relative aspect-square rounded-lg overflow-hidden border border-border bg-muted hover:ring-2 hover:ring-primary/40 transition-all"
                    title={img.file_name ?? undefined}
                  >
                    {img.url ? (
                      <Image
                        src={img.url}
                        alt={img.file_name ?? "Ảnh"}
                        fill
                        sizes="200px"
                        className="object-cover"
                        unoptimized
                      />
                    ) : (
                      <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                        Không tải được ảnh
                      </div>
                    )}
                  </a>
                ))}
              </div>
            </section>
          )}

          {/* Admin actions */}
          <section className="rounded-xl border border-primary/20 bg-primary/[0.03] p-4 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-primary">
              Quản trị
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Trạng thái</Label>
                <Select value={status} onValueChange={(v) => v && setStatus(v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(STATUS_LABELS).map(([v, lbl]) => (
                      <SelectItem key={v} value={v}>
                        {lbl}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Loại</Label>
                <Select value={category} onValueChange={(v) => v && setCategory(v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(CATEGORY_LABELS).map(([v, lbl]) => (
                      <SelectItem key={v} value={v}>
                        {lbl}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">Ghi chú nội bộ</Label>
              <Textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Ghi chú cho team, link JIRA, kế hoạch xử lý..."
              />
            </div>

            {err && (
              <p className="text-sm text-destructive">{err}</p>
            )}

            <div className="flex items-center justify-between gap-2">
              <Button
                variant="destructive"
                size="sm"
                onClick={remove}
                disabled={saving}
              >
                <span className="material-symbols-outlined text-[16px]">
                  delete
                </span>
                Xoá góp ý
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenChange(false)}
                  disabled={saving}
                >
                  Đóng
                </Button>
                <Button size="sm" onClick={save} disabled={saving}>
                  {saving ? "Đang lưu…" : "Lưu thay đổi"}
                </Button>
              </div>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span
        className={`text-sm text-foreground break-words ${
          mono ? "font-mono" : ""
        }`}
      >
        {value || <span className="text-muted-foreground/60">—</span>}
      </span>
    </div>
  );
}

function Block({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
        {label}
      </div>
      <div
        className={`text-sm text-foreground whitespace-pre-wrap leading-relaxed ${
          mono ? "font-mono break-all" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}
