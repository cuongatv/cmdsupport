"use client";

import { useEffect, useState } from "react";
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

type Department = { id: string; name: string; description?: string };

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  department: Department | null;
  onSaved: () => void;
};

export function DepartmentDialog({
  open,
  onOpenChange,
  department,
  onSaved,
}: Props) {
  const isEdit = !!department;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (department) {
      setName(department.name);
      setDescription(department.description || "");
    } else {
      setName("");
      setDescription("");
    }
    setError("");
  }, [department, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      const body = { name, description };
      if (isEdit) {
        await api(`/api/departments/${department.id}`, { method: "PUT", body });
      } else {
        await api("/api/departments", { method: "POST", body });
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
            {isEdit ? "Sửa đơn vị" : "Tạo đơn vị"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="dept-name">Tên</Label>
            <Input
              id="dept-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sales, Engineering"
              required
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="dept-desc">Mô tả</Label>
            <Textarea
              id="dept-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả (tuỳ chọn)…"
              rows={3}
              className="bg-background"
            />
          </div>

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Huỷ
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? "Đang lưu…" : isEdit ? "Cập nhật" : "Tạo"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
