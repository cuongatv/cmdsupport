"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getWikiTaxonomyGroup } from "@/lib/wiki-labels";

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeType: KnowledgeType | null;
  onSaved: () => void;
};

const PRESET_COLORS = [
  "#6B7280", "#10B981", "#8B5CF6", "#F59E0B",
  "#3B82F6", "#EF4444", "#EC4899", "#14B8A6",
  "#F97316", "#6366F1",
];

export function KnowledgeTypeDialog({
  open,
  onOpenChange,
  knowledgeType,
  onSaved,
}: Props) {
  const isEdit = !!knowledgeType;
  const isSystemSeeded = knowledgeType
    ? getWikiTaxonomyGroup(knowledgeType.slug) !== "unknown"
    : false;
  const [name, setName] = useState("");
  const [color, setColor] = useState("#6366F1");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const colorInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (knowledgeType) {
      setName(knowledgeType.name);
      setColor(knowledgeType.color);
      setDescription(knowledgeType.description || "");
    } else {
      setName("");
      setColor("#6366F1");
      setDescription("");
    }
    setError("");
  }, [knowledgeType, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      const body = { name, color, description };
      if (isEdit) {
        await api(`/api/knowledge-types/${knowledgeType.id}`, {
          method: "PUT",
          body,
        });
      } else {
        await api("/api/knowledge-types", { method: "POST", body });
      }
      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {isEdit ? "Sửa loại tri thức" : "Tạo loại tri thức"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          {knowledgeType && (
            <div className="flex flex-col gap-2">
              <Label>Slug</Label>
              <Input
                value={knowledgeType.slug}
                disabled
                readOnly
                className="bg-muted font-mono text-xs"
              />
              {isSystemSeeded && (
                <p className="text-xs text-muted-foreground">
                  Slug hệ thống không thể đổi
                </p>
              )}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Label>Tên</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ví dụ: Tài liệu sản phẩm"
              required
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Màu sắc</Label>
            <div className="flex flex-wrap gap-2">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`w-7 h-7 rounded-full border-2 transition-all ${
                    color === c ? "border-foreground scale-110" : "border-transparent"
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
              <div className="relative w-7 h-7">
                <button
                  type="button"
                  onClick={() => colorInputRef.current?.click()}
                  className="w-7 h-7 rounded-full p-[2px] transition-all hover:scale-110 cursor-pointer"
                  style={{
                    background:
                      "conic-gradient(#f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00)",
                  }}
                  title="Chọn màu tuỳ chỉnh"
                >
                  <span className="w-full h-full rounded-full bg-background flex items-center justify-center">
                    <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: "14px" }}>
                      add
                    </span>
                  </span>
                </button>
                <input
                  ref={colorInputRef}
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="absolute inset-0 opacity-0 pointer-events-none"
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Mô tả</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả (tuỳ chọn)..."
              rows={2}
              className="bg-background"
            />
          </div>

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Huỷ
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? "Đang lưu..." : isEdit ? "Cập nhật" : "Tạo"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
