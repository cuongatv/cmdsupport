import React from "react";
import { Source } from "./types";

export function StatusDot({ source }: { source: Source }) {
  const colors: Record<string, string> = {
    ready: "bg-green-500",
    processing: "bg-yellow-500",
    plan_ready: "bg-sky-500",
    error: "bg-destructive",
    pending: "bg-muted-foreground",
  };
  const labels: Record<string, string> = {
    ready: "ready",
    processing: "processing",
    plan_ready: "review plan",
    error: "error",
    pending: "pending",
  };

  const status = source.status;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${colors[status] || colors.pending}`} />
        <span className="text-xs capitalize text-muted-foreground">{labels[status] || status}</span>
        {status === "processing" && source.progress !== undefined && (
          <span className="text-xs text-muted-foreground">({source.progress}%)</span>
        )}
      </div>
      {(status === "processing" || status === "pending") && source.progress_message && (
        <span className="text-[10px] text-muted-foreground truncate max-w-[150px]" title={source.progress_message}>
          {source.progress_message}
        </span>
      )}
      {status === "error" && source.progress_message && (
        <span className="text-[10px] text-destructive truncate max-w-[150px]" title={source.progress_message}>
          {source.progress_message}
        </span>
      )}
    </div>
  );
}
