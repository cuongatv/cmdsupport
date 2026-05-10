import React from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Source, KnowledgeType, Department } from "./types";

export function EditSourceDialog({
  source,
  types,
  departments,
  onClose,
  onSaved,
}: {
  source: Source;
  types: KnowledgeType[];
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = React.useState(source.title);
  const [typeId, setTypeId] = React.useState(source.knowledge_type_id || "");
  const [selectedDepts, setSelectedDepts] = React.useState<string[]>(source.department_ids || []);
  const [scopeType, setScopeType] = React.useState(source.scope_type || "global");
  const [scopeId, setScopeId] = React.useState(source.scope_id || "");
  const [projects, setProjects] = React.useState<{ id: string; name: string }[]>([]);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  // Fetch projects for workspace scope picker
  React.useEffect(() => {
    api<{ id: string; name: string }[]>("/api/projects")
      .then((data) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]));
  }, []);

  const toggleDept = (deptId: string) => {
    setSelectedDepts((prev) =>
      prev.includes(deptId) ? prev.filter((d) => d !== deptId) : [...prev, deptId]
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await api(`/api/sources/${source.id}`, {
        method: "PATCH",
        body: {
          title: title || undefined,
          knowledge_type_id: typeId || null,
          department_ids: selectedDepts,
          scope_type: scopeType,
          scope_id: scopeType === "global" ? null : (scopeId || null),
        },
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">Sửa tài liệu</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Tiêu đề</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Loại tri thức</Label>
            <Select value={typeId} onValueChange={(v) => setTypeId(v ?? "")}>
              <SelectTrigger className="bg-background">
                {typeId ? (() => { const t = types.find(x => x.id === typeId); return t ? (
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: t.color }} />
                    <span>{t.name}</span>
                  </div>
                ) : <SelectValue placeholder="Không có loại" />; })() : <SelectValue placeholder="Không có loại" />}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Không có loại</SelectItem>
                {types.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: t.color }} />
                      {t.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Multi-department selection */}
          <div className="flex flex-col gap-1.5">
            <Label>Đơn vị</Label>
            <p className="text-xs text-muted-foreground">
              Chọn đơn vị có quyền truy cập tài liệu này. Để trống nếu muốn toàn hệ thống truy cập.
            </p>
            <div className="border rounded-lg p-2 max-h-40 overflow-y-auto bg-background">
              {departments.length === 0 ? (
                <span className="text-xs text-muted-foreground">Không có đơn vị nào</span>
              ) : (
                departments.map((d) => (
                  <label
                    key={d.id}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedDepts.includes(d.id)}
                      onChange={() => toggleDept(d.id)}
                      className="rounded border-border"
                    />
                    <span className="text-sm">{d.name}</span>
                  </label>
                ))
              )}
            </div>
            {selectedDepts.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {selectedDepts.map((id) => {
                  const name = departments.find((d) => d.id === id)?.name ?? id;
                  return (
                    <span
                      key={id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary"
                    >
                      {name}
                      <button
                        type="button"
                        onClick={() => toggleDept(id)}
                        className="hover:text-destructive"
                      >
                        ×
                      </button>
                    </span>
                  );
                })}
              </div>
            )}
          </div>

          {/* Visibility / Scope */}
          <div className="flex flex-col gap-1.5">
            <Label>Phạm vi</Label>
            <Select value={scopeType} onValueChange={(v) => {
              const val = v ?? "global";
              setScopeType(val);
              if (val === "global") setScopeId("");
            }}>
              <SelectTrigger className="bg-background">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                    {scopeType === "global" ? "public" : "folder_special"}
                  </span>
                   <span className="capitalize">{scopeType === "project" ? "Không gian nghiệp vụ" : "Toàn hệ thống"}</span>
                </div>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>public</span>
                    Toàn hệ thống
                  </div>
                </SelectItem>
                <SelectItem value="project">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>folder_special</span>
                    Không gian nghiệp vụ
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {scopeType === "project" && (
            <div className="flex flex-col gap-1.5">
              <Label>Không gian nghiệp vụ đích</Label>
              <Select value={scopeId} onValueChange={(v) => setScopeId(v ?? "")}>
                <SelectTrigger className="bg-background">
                   <span>{scopeId ? (projects.find(p => p.id === scopeId)?.name ?? "Chọn...") : "Chọn không gian nghiệp vụ..."}</span>
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button variant="outline" onClick={onClose}>Huỷ</Button>
            <Button
              disabled={saving}
              onClick={handleSave}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? (
               <span className="flex items-center gap-2">
                 <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                 Đang lưu...
               </span>
              ) : "Lưu"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
