import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, apiUpload } from "@/lib/api";
import { ProjectSource, Project, Source } from "./types";
import { getFileExt, fileIcons } from "./utils";
import { AddDocumentModal } from "./add-document-modal";

type Props = {
  project: Project;
  sources: ProjectSource[];
  isAdmin: boolean;
  availableSources: Source[];
  onChanged: () => Promise<void>;
  onError: (msg: string | null) => void;
};

export function SourcesTab({
  project,
  sources,
  isAdmin,
  availableSources,
  onChanged,
  onError,
}: Props) {
  const [showAddDocModal, setShowAddDocModal] = useState(false);

  const handleRemoveSource = async (sourceId: string) => {
    if (!confirm("Gỡ tài liệu này khỏi không gian nghiệp vụ?")) return;
    onError(null);
    try {
      await api(`/api/projects/${project.id}/sources/${sourceId}`, { method: "DELETE" });
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to remove document");
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Stats bar + Add button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {sources.length > 0 && (
            <>
              <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2 shadow-sahara">
                <span className="material-symbols-outlined text-sm text-primary">description</span>
                <span className="text-sm font-semibold">{sources.length}</span>
                <span className="text-xs text-muted-foreground">Tài liệu</span>
              </div>
              {(() => {
                const ready = sources.filter((s) => s.status === "ready").length;
                const processing = sources.filter(
                  (s) => s.status === "processing" || s.status === "pending"
                ).length;
                const errored = sources.filter((s) => s.status === "error").length;
                return (
                  <>
                    {ready > 0 && (
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="w-2 h-2 rounded-full bg-green-500" />
                        {ready} sẵn sàng
                      </div>
                    )}
                    {processing > 0 && (
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
                        {processing} đang xử lý
                      </div>
                    )}
                    {errored > 0 && (
                      <div className="flex items-center gap-1.5 text-xs text-destructive">
                        <span className="w-2 h-2 rounded-full bg-destructive" />
                        {errored} lỗi
                      </div>
                    )}
                  </>
                );
              })()}
            </>
          )}
        </div>
        {isAdmin && (
          <Button
            onClick={() => setShowAddDocModal(true)}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
            size="sm"
          >
            <span className="material-symbols-outlined text-base mr-1.5">add</span>
            Thêm tài liệu
          </Button>
        )}
      </div>

      {/* Document cards */}
      {sources.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sahara py-16 flex flex-col items-center gap-3">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
            <span className="material-symbols-outlined text-primary" style={{ fontSize: 28 }}>
              folder_open
            </span>
          </div>
          <h3 className="text-base font-heading text-foreground">Chưa có tài liệu</h3>
          <p className="text-sm text-muted-foreground max-w-sm text-center">
            Tải lên tệp hoặc liên kết tài liệu có sẵn để xây dựng kho tri thức cho không gian nghiệp vụ này.
          </p>
          {isAdmin && (
            <Button
              onClick={() => setShowAddDocModal(true)}
              variant="outline"
              size="sm"
              className="mt-2"
            >
              <span className="material-symbols-outlined text-base mr-1.5">add</span>
              Thêm tài liệu đầu tiên
            </Button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {sources.map((s) => {
            const ext = getFileExt(s);
            const icon = fileIcons[ext] || (s.source_type === "url" ? "link" : "description");
            const isProcessing = s.status === "processing" || s.status === "pending";
            return (
              <div
                key={s.source_id}
                className="group bg-card border border-border rounded-xl px-4 py-3.5 hover:border-primary/30 hover:shadow-sahara transition-all flex items-center gap-3"
              >
                {/* File icon */}
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                    s.status === "ready"
                      ? "bg-green-500/10"
                      : s.status === "error"
                      ? "bg-destructive/10"
                      : "bg-primary/10"
                  }`}
                >
                  <span
                    className={`material-symbols-outlined ${
                      s.status === "ready"
                        ? "text-green-600"
                        : s.status === "error"
                        ? "text-destructive"
                        : "text-primary"
                    }`}
                    style={{ fontSize: 18 }}
                  >
                    {icon}
                  </span>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground truncate">
                      {s.title || s.source_id}
                    </span>
                    {ext && (
                      <span className="text-[10px] font-medium text-muted-foreground uppercase bg-accent/50 px-1.5 py-0.5 rounded shrink-0">
                        {ext}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    {s.knowledge_type_name && (
                      <Badge variant="outline" className="text-[10px] h-4 px-1.5 font-medium">
                        {s.knowledge_type_name}
                      </Badge>
                    )}
                    {isProcessing && s.progress_message && (
                      <span
                        className="text-[10px] text-muted-foreground truncate max-w-[200px]"
                        title={s.progress_message}
                      >
                        {s.progress_message}
                      </span>
                    )}
                  </div>
                  {/* Progress bar for processing */}
                  {isProcessing && s.progress !== undefined && (
                    <div className="mt-1.5 h-1 bg-border rounded-full overflow-hidden w-full max-w-[200px]">
                      <div
                        className="h-full bg-primary/70 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(s.progress, 100)}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Status + date + actions */}
                <div className="flex items-center gap-3 shrink-0">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        s.status === "ready"
                          ? "bg-green-500"
                          : s.status === "processing"
                          ? "bg-yellow-500 animate-pulse"
                          : s.status === "error"
                          ? "bg-destructive"
                          : "bg-muted-foreground"
                      }`}
                    />
                    <span className="text-xs capitalize text-muted-foreground">{s.status}</span>
                    {s.status === "processing" && s.progress !== undefined && (
                      <span className="text-xs text-muted-foreground tabular-nums">
                        ({s.progress}%)
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {s.added_at
                      ? new Date(s.added_at).toLocaleDateString("vi-VN", {
                          day: "2-digit",
                          month: "2-digit",
                        })
                      : ""}
                  </span>
                  {isAdmin && (
                    <DropdownMenu>
                      <DropdownMenuTrigger className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent text-muted-foreground transition-opacity">
                        <span className="material-symbols-outlined text-base">more_vert</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => handleRemoveSource(s.source_id)}
                          className="text-destructive focus:text-destructive"
                        >
                          <span className="material-symbols-outlined text-base mr-2">delete</span>
                          Gỡ
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <AddDocumentModal
        open={showAddDocModal}
        onOpenChange={setShowAddDocModal}
        projectId={project.id}
        availableSources={availableSources}
        onDone={() => {
          onChanged();
          setShowAddDocModal(false);
        }}
      />
    </div>
  );
}
