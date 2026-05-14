"use client";

import { useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  type Department as DepartmentModel,
  type UnitType,
  UNIT_TYPE_LABEL,
} from "@/lib/department-types";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  department: DepartmentModel | null;
  onSaved: () => void;
};

type DepartmentDialogFormProps = {
  department: DepartmentModel | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
};

function DepartmentDialogForm({ department, onOpenChange, onSaved }: DepartmentDialogFormProps) {
  const isEdit = !!department;
  const [name, setName] = useState(() => department?.name ?? "");
  const [description, setDescription] = useState(() => department?.description ?? "");
  const [unitType, setUnitType] = useState<UnitType>(
    () => department?.unit_type ?? "business_group"
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      if (isEdit) {
        // unit_type immutable after creation — backend rejects with 400.
        await api(`/api/departments/${department.id}`, {
          method: "PUT",
          body: { name, description },
        });
      } else {
        await api("/api/departments", {
          method: "POST",
          body: { name, description, unit_type: unitType },
        });
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
        <Label htmlFor="dept-unit-type">Loại đơn vị</Label>
        {isEdit ? (
          <div className="bg-muted/50 px-3 py-2 rounded-md text-sm">
            {UNIT_TYPE_LABEL[unitType]}
            <span className="text-muted-foreground ml-2">
              (không thể đổi sau khi tạo)
            </span>
          </div>
        ) : (
          <Select
            value={unitType}
            onValueChange={(v) => setUnitType(v as UnitType)}
          >
            <SelectTrigger id="dept-unit-type" className="bg-background">
              <SelectValue>
                {(v: string | null) =>
                  v ? UNIT_TYPE_LABEL[v as UnitType] : "Chọn loại đơn vị"
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="business_group">
                {UNIT_TYPE_LABEL.business_group} — Nhóm nghiệp vụ, chiến dịch, hỗ trợ Chi nhánh
              </SelectItem>
              <SelectItem value="squad_team">
                {UNIT_TYPE_LABEL.squad_team} — Squad delivery Agile/Scrum
              </SelectItem>
            </SelectContent>
          </Select>
        )}
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
  );
}

export function DepartmentDialog({
  open,
  onOpenChange,
  department,
  onSaved,
}: Props) {
  const isEdit = !!department;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {isEdit ? "Sửa đơn vị" : "Tạo đơn vị"}
          </DialogTitle>
        </DialogHeader>

        <DepartmentDialogForm
          key={`${department?.id ?? "new"}-${open ? "open" : "closed"}`}
          department={department}
          onOpenChange={onOpenChange}
          onSaved={onSaved}
        />
      </DialogContent>
    </Dialog>
  );
}
