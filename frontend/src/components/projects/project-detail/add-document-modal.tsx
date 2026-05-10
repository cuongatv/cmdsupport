import React, { useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
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
import { Source } from "./types";

const ALLOWED_EXTS = [".pdf", ".docx", ".doc", ".xlsx", ".csv", ".txt", ".md", ".pptx"];
const MAX_SIZE = 50 * 1024 * 1024; // 50 MB

export function AddDocumentModal({
  open,
  onOpenChange,
  projectId,
  availableSources,
  onDone,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projectId: string;
  availableSources: Source[];
  onDone: () => void;
}) {
  const [mode, setMode] = useState<"upload" | "link">("upload");
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const reset = () => {
    setSelectedFile(null);
    setFileError(null);
    setError(null);
    setSelectedSourceId("");
    setUploading(false);
    setLinking(false);
  };

  const validateFile = (file: File): string | null => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) return `Định dạng không hỗ trợ: ${ext}`;
    if (file.size > MAX_SIZE) return `Tệp quá lớn (${(file.size / 1024 / 1024).toFixed(1)} MB). Tối đa: 50 MB`;
    return null;
  };

  const handleFile = (file: File) => {
    setFileError(null);
    const err = validateFile(file);
    if (err) { setFileError(err); return; }
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("title", selectedFile.name);
      await apiUpload(`/api/projects/${projectId}/sources/upload`, formData);
      reset();
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleLink = async () => {
    if (!selectedSourceId) return;
    setLinking(true);
    setError(null);
    try {
      await api(`/api/projects/${projectId}/sources`, {
        method: "POST",
        body: { source_id: selectedSourceId },
      });
      reset();
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to link document");
    } finally {
      setLinking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="sm:max-w-[520px] p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-0">
          <DialogTitle className="text-lg font-heading">Thêm tài liệu</DialogTitle>
        </DialogHeader>

        {/* Mode tabs */}
        <div className="flex border-b border-border mx-6">
          {(["upload", "link"] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(null); }}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${mode === m
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
            >
              <span className="material-symbols-outlined text-sm">
                {m === "upload" ? "cloud_upload" : "add"}
              </span>
              {m === "upload" ? "Tải lên tệp" : "Thêm tài liệu có sẵn"}
            </button>
          ))}
        </div>

        <div className="px-6 pb-6 pt-4">
          {/* Error */}
          {error && (
            <div className="mb-4 text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2">
              <span className="material-symbols-outlined text-sm">error</span>
              {error}
            </div>
          )}

          {mode === "upload" ? (
            /* ---- Upload tab ---- */
            <div className="flex flex-col gap-4">
              {/* Drop zone */}
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleFile(file);
                }}
                className={`cursor-pointer rounded-xl border-2 border-dashed p-8 flex flex-col items-center gap-3 transition-all ${dragOver
                  ? "border-primary bg-primary/5"
                  : selectedFile
                    ? "border-green-400/50 bg-green-500/5"
                    : "border-border hover:border-primary/40 hover:bg-primary/5"
                  }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept={ALLOWED_EXTS.join(",")}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                    e.target.value = "";
                  }}
                />
                {selectedFile ? (
                  <>
                    <div className="w-10 h-10 rounded-full bg-green-500/10 flex items-center justify-center">
                      <span className="material-symbols-outlined text-green-600" style={{ fontSize: 22 }}>check_circle</span>
                    </div>
                    <div className="text-center min-w-0 max-w-full">
                      <p className="text-sm font-medium text-foreground truncate max-w-[360px]">{selectedFile.name}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {(selectedFile.size / 1024).toFixed(0)} KB · Bấm để đổi tệp
                      </p>
                    </div>
                  </>
                ) : (
                  <>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${dragOver ? "bg-primary/20" : "bg-primary/10"
                      }`}>
                      <span className="material-symbols-outlined text-primary" style={{ fontSize: 22 }}>cloud_upload</span>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-foreground">
                        {dragOver ? "Thả tệp vào đây" : "Kéo thả hoặc bấm để chọn tệp"}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        PDF, DOCX, XLSX, CSV, TXT, MD, PPTX · Tối đa 50 MB
                      </p>
                    </div>
                  </>
                )}
              </div>

              {fileError && (
                <p className="text-sm text-destructive flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm">warning</span>
                  {fileError}
                </p>
              )}

              <Button
                disabled={!selectedFile || uploading}
                onClick={handleUpload}
                className="w-full bg-primary text-primary-foreground hover:bg-primary/90"
              >
                {uploading ? (
                  <>
                    <span className="material-symbols-outlined text-base mr-2 animate-spin">progress_activity</span>
                    Đang tải lên...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-base mr-2">upload</span>
                    Tải lên
                  </>
                )}
              </Button>
            </div>
          ) : (
            /* ---- Link tab ---- */
            <div className="flex flex-col gap-4">
              {availableSources.length === 0 ? (
                <div className="py-8 flex flex-col items-center gap-2">
                  <span className="material-symbols-outlined text-3xl text-muted-foreground/40">description</span>
                  <p className="text-sm text-muted-foreground">Không có tài liệu nào để liên kết</p>
                  <p className="text-xs text-muted-foreground">Tất cả tài liệu đã có trong không gian nghiệp vụ này.</p>
                </div>
              ) : (
                <>
                  <Select value={selectedSourceId} onValueChange={(v) => setSelectedSourceId(v ?? "")}>
                    <SelectTrigger className="bg-background w-full">
                      {selectedSourceId ? (
                        <span className="truncate">
                          {availableSources.find(s => s.id === selectedSourceId)?.title || selectedSourceId}
                        </span>
                      ) : (
                        <SelectValue placeholder="Chọn tài liệu có sẵn để thêm..." />
                      )}
                    </SelectTrigger>
                    <SelectContent>
                      {availableSources.map((s) => (
                        <SelectItem key={s.id} value={s.id}>
                          <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-sm text-muted-foreground">
                              {s.source_type === "url" ? "link" : "description"}
                            </span>
                            {s.title || s.id}
                            {s.knowledge_type_name && (
                              <span className="text-[10px] text-muted-foreground bg-accent/50 px-1.5 py-0.5 rounded">
                                {s.knowledge_type_name}
                              </span>
                            )}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Button
                    disabled={!selectedSourceId || linking}
                    onClick={handleLink}
                    className="w-full bg-primary text-primary-foreground hover:bg-primary/90"
                  >
                    {linking ? (
                      <>
                        <span className="material-symbols-outlined text-base mr-2 animate-spin">progress_activity</span>
                        Đang liên kết...
                      </>
                    ) : (
                      <>
                        <span className="material-symbols-outlined text-base mr-2">add_link</span>
                        Liên kết vào không gian nghiệp vụ
                      </>
                    )}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
