"use client";

import React from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

type Project = {
  id: string;
  name: string;
  description?: string;
  workspace_type?: string;
  status: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project | null;
  onSaved: () => void;
};

export function ProjectDialog({ open, onOpenChange, project, onSaved }: Props) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [workspaceType, setWorkspaceType] = React.useState("project");
  const [status, setStatus] = React.useState("active");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setName(project?.name || "");
      setDescription(project?.description || "");
      setWorkspaceType(project?.workspace_type || "project");
      setStatus(project?.status || "active");
      setError("");
    }
  }, [open, project]);

  const handleSave = async () => {
    if (!name.trim()) { setError("Tên là bắt buộc"); return; }
    setSaving(true);
    setError("");
    try {
      if (project) {
        await api(`/api/projects/${project.id}`, {
          method: "PUT",
          body: { name: name.trim(), description: description.trim() || undefined, status, workspace_type: workspaceType },
        });
      } else {
        await api("/api/projects", {
          method: "POST",
          body: { name: name.trim(), description: description.trim() || undefined, workspace_type: workspaceType },
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {project ? "Sửa không gian" : "Tạo không gian mới"}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Tên</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: ACME Corp, Q3 Board Deck, Alpha Launch"
              className="bg-background"
            />
          </div>

          {/* Workspace Type */}
          {!project && (
            <div className="flex flex-col gap-1.5">
              <Label>Loại</Label>
              <Select value={workspaceType} onValueChange={(v) => { if (v) setWorkspaceType(v); }}>
                <SelectTrigger className="w-full bg-background">
                  {workspaceType === "project" ? (
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm">folder_special</span>
                      Dự án
                    </div>
                  ) : workspaceType === "customer" ? (
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm">domain</span>
                      Khách hàng
                    </div>
                  ) : (
                    <SelectValue placeholder="Chọn loại" />
                  )}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="project">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm">folder_special</span>
                      Dự án
                    </div>
                  </SelectItem>
                  <SelectItem value="customer">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm">domain</span>
                      Khách hàng
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label>Mô tả <span className="text-muted-foreground font-normal">(tuỳ chọn)</span></Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả ngắn gọn về không gian này"
              className="bg-background"
            />
          </div>

          {project && (
            <div className="flex flex-col gap-1.5">
              <Label>Trạng thái</Label>
              <Select value={status} onValueChange={(v) => { if (v) setStatus(v); }}>
                <SelectTrigger className="w-full bg-background">
                  <SelectValue>
                    {(v: string | null) =>
                      v === "archived" ? "Đã lưu trữ" : v === "active" ? "Hoạt động" : "Chọn trạng thái"
                    }
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Hoạt động</SelectItem>
                  <SelectItem value="archived">Đã lưu trữ</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">{error}</p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Huỷ</Button>
            <Button
              disabled={saving}
              onClick={handleSave}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                  Đang lưu…
                </span>
              ) : project ? "Lưu" : "Tạo"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
