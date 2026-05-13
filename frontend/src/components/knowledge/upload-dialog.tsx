"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
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

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
};

type Department = {
  id: string;
  name: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  types: KnowledgeType[];
  departments: Department[];
  onUploaded: () => void;
};

const ACCEPTED_EXTENSIONS = ["pdf", "docx", "doc", "xlsx", "csv", "txt", "md", "pptx"];
const ACCEPTED_MIMES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
  "text/csv",
  "text/markdown",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
];
const ACCEPT_STRING = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(",");

function getFileExtension(name: string): string {
  return (name.split(".").pop() || "").toLowerCase();
}

function validateFile(f: File): string | null {
  const ext = getFileExtension(f.name);
  if (!ACCEPTED_EXTENSIONS.includes(ext) && !ACCEPTED_MIMES.includes(f.type)) {
    return `Unsupported file type ".${ext}". Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`;
  }
  if (f.size > 50 * 1024 * 1024) {
    return "File too large. Maximum size is 50 MB.";
  }
  return null;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadDialog({ open, onOpenChange, types, departments, onUploaded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [typeId, setTypeId] = useState("");
  const [scopeType, setScopeType] = useState("global");
  const [scopeId, setScopeId] = useState("");
  const [pipeline, setPipeline] = useState<"legacy" | "mrp">("mrp");
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    api<{ id: string; name: string }[]>("/api/projects")
      .then((data) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]));
  }, [open]);

  const handleFile = useCallback((f: File) => {
    const validationError = validateFile(f);
    if (validationError) {
      setError(validationError);
      setFile(null);
      return;
    }
    setError("");
    setFile(f);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      const f = e.dataTransfer.files?.[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", file);
      if (typeId) formData.append("knowledge_type_id", typeId);

      formData.append("scope_type", scopeType);
      if (scopeType !== "global" && scopeId) {
        formData.append("scope_id", scopeId);
      }
      // Luôn gửi ingestion_pipeline lên server. Backend mặc định cũng là MRP,
      // nhưng gửi tường minh giúp người dùng switch về legacy nếu cần.
      formData.append("ingestion_pipeline", pipeline);

      await apiUpload("/api/sources/upload", formData);
      onUploaded();
      onOpenChange(false);
      setFile(null);
      setTypeId("");
      setScopeType("global");
      setScopeId("");
      setPipeline("mrp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tải lên thất bại");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl font-heading">Tải lên tài liệu</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2 overflow-hidden">
          {/* Drag & drop zone */}
          <div className="flex flex-col gap-2 min-w-0">
            <Label>Tệp</Label>
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`
                relative flex flex-col items-center justify-center gap-2 px-4 py-6
                rounded-xl border-2 border-dashed cursor-pointer transition-all duration-200 overflow-hidden
                ${dragOver
                  ? "border-primary bg-primary/5 scale-[1.01]"
                  : file
                    ? "border-primary/40 bg-primary/[0.02]"
                    : "border-border hover:border-primary/40 hover:bg-accent/30"
                }
              `}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPT_STRING}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                  // Reset input so same file can be re-selected
                  e.target.value = "";
                }}
                className="hidden"
              />

              {file ? (
                /* File selected state */
                <div className="flex items-center gap-3 w-full min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <span className="material-symbols-outlined text-primary" style={{ fontSize: 20 }}>
                      description
                    </span>
                  </div>
                  <div className="flex-1 min-w-0 overflow-hidden">
                    <p className="text-sm font-medium text-foreground truncate">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatFileSize(file.size)} · .{getFileExtension(file.name).toUpperCase()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                      setError("");
                    }}
                    className="p-1 rounded-md hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
                  </button>
                </div>
              ) : (
                /* Empty state — prompt */
                <>
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
                    dragOver ? "bg-primary/15" : "bg-accent/60"
                  }`}>
                    <span className={`material-symbols-outlined transition-colors ${
                      dragOver ? "text-primary" : "text-muted-foreground"
                    }`} style={{ fontSize: 22 }}>
                      upload_file
                    </span>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-foreground font-medium">
                      {dragOver ? "Thả tệp tại đây" : "Kéo thả hoặc nhấn để chọn tệp"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      PDF, DOCX, XLSX, CSV, TXT, MD, PPTX · Max 50 MB
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Knowledge Type */}
          <div className="flex flex-col gap-2">
            <Label>Loại tri thức</Label>
            <Select value={typeId} onValueChange={(v) => setTypeId(v ?? "")}>
              <SelectTrigger className="bg-background w-full">
                {typeId ? (() => { const t = types.find(x => x.id === typeId); return t ? (
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: t.color }} />
                    <span>{t.name}</span>
                  </div>
                 ) : <SelectValue placeholder="Chọn loại (tuỳ chọn)" />; })() : <SelectValue placeholder="Chọn loại (tuỳ chọn)" />}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Không chọn</SelectItem>
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

          {/* Visibility / Scope */}
          <div className="flex flex-col gap-2">
            <Label>Phạm vi truy cập</Label>
            <Select value={scopeType} onValueChange={(v) => {
              const val = v ?? "global";
              setScopeType(val);
              if (val === "global") setScopeId("");
            }}>
              <SelectTrigger className="bg-background w-full">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                    {scopeType === "global" ? "public" : scopeType === "department" ? "domain" : "folder_special"}
                  </span>
                  <span className="capitalize">{scopeType === "global" ? "Toàn bộ" : scopeType === "project" ? "Không gian" : "Đơn vị"}</span>
                </div>
              </SelectTrigger>
              <SelectContent className="min-w-[220px]">
                <SelectItem value="global">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>public</span>
                    Toàn bộ (Tất cả người dùng)
                  </div>
                </SelectItem>
                <SelectItem value="department">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>domain</span>
                    Đơn vị
                  </div>
                </SelectItem>
                <SelectItem value="project">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>folder_special</span>
                    Không gian
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-0.5">
              Giới hạn truy cập hoặc để Toàn bộ để mọi người đều đọc được.
            </p>
          </div>

          {/* Scope entity picker */}
          {scopeType === "department" && (
            <div className="flex flex-col gap-1.5">
              <Label>Đơn vị đích</Label>
              <Select value={scopeId} onValueChange={(v) => setScopeId(v ?? "")}>
                <SelectTrigger className="bg-background">
                  <span>{scopeId ? (departments.find(d => d.id === scopeId)?.name ?? "Chọn…") : "Chọn đơn vị…"}</span>
                </SelectTrigger>
                <SelectContent>
                  {departments.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {scopeType === "project" && (
            <div className="flex flex-col gap-1.5">
              <Label>Không gian đích</Label>
              <Select value={scopeId} onValueChange={(v) => setScopeId(v ?? "")}>
                <SelectTrigger className="bg-background">
                  <span>{scopeId ? (projects.find(p => p.id === scopeId)?.name ?? "Chọn…") : "Chọn không gian…"}</span>
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

          <div className="flex flex-col gap-1.5">
            <Label>Luồng xử lý</Label>
            <Select
              value={pipeline}
              onValueChange={(v) => setPipeline((v ?? "legacy") as "legacy" | "mrp")}
            >
              <SelectTrigger className="bg-background w-full">
                <span>
                  {pipeline === "mrp"
                    ? "MRP - có bước duyệt kế hoạch"
                    : "Agent biên dịch trực tiếp (legacy)"}
                </span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="mrp">MRP - có bước duyệt kế hoạch</SelectItem>
                <SelectItem value="legacy">Agent biên dịch trực tiếp (legacy)</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-0.5">
              MRP chia tài liệu, gom bằng chứng, đợi bạn duyệt kế hoạch rồi mới tạo trang wiki. Chọn legacy nếu muốn agent biên dịch trực tiếp như trước đây.
            </p>
          </div>

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2">
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Huỷ
            </Button>
            <Button
              disabled={!file || uploading}
              onClick={handleUpload}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {uploading ? (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined animate-spin text-sm">
                    progress_activity
                  </span>
                  Đang tải lên…
                </span>
              ) : (
                "Tải lên"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

