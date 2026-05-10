"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";

type Source = {
  id: string;
  title: string;
  status: string;
  knowledge_type_name?: string;
  knowledge_type_color?: string;
  created_at: string;
};

export function RecentSourcesCard() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await api<Source[]>("/api/sources?limit=5");
        setSources(data || []);
      } catch {
        setSources([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <h3 className="text-xl tracking-tight text-foreground border-b border-border pb-3 mb-4">
        Tài liệu gần đây
      </h3>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <span className="material-symbols-outlined text-2xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : sources.length === 0 ? (
        <EmptyState
          icon="description"
          title="Chưa có tài liệu"
          description="Tải lên tài liệu đầu tiên trong Kho tri thức"
        />
      ) : (
        <div className="flex flex-col gap-3">
          {sources.map((source) => (
            <div
              key={source.id}
              className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-secondary/50 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="material-symbols-outlined text-muted-foreground text-base">
                  description
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {source.title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(source.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {source.knowledge_type_name && (
                  <Badge
                    variant="outline"
                    style={{
                      borderColor: source.knowledge_type_color,
                      color: source.knowledge_type_color,
                    }}
                    className="text-xs"
                  >
                    {source.knowledge_type_name}
                  </Badge>
                )}
                <StatusBadge status={source.status} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    ready: "bg-green-50 text-green-700",
    processing: "bg-yellow-50 text-yellow-700",
    error: "bg-destructive/10 text-destructive",
    pending: "bg-secondary text-muted-foreground",
  };

  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
        variants[status] || variants.pending
      }`}
    >
      {status === "ready" ? "sẵn sàng" : status === "processing" ? "đang xử lý" : status === "error" ? "lỗi" : status === "pending" ? "đang chờ" : status}
    </span>
  );
}
