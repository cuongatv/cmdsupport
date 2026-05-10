"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
  sort_order: number;
  source_count?: number;
};

type Props = {
  types: KnowledgeType[];
  loading: boolean;
  onEdit: (type: KnowledgeType) => void;
  onRefresh: () => void;
};

export function KnowledgeTypeCards({ types, loading, onEdit, onRefresh }: Props) {
  const handleDelete = async (id: string) => {
    if (!confirm("Xoá loại tri thức này?")) return;
    await api(`/api/knowledge-types/${id}`, { method: "DELETE" });
    onRefresh();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  if (types.length === 0) {
    return (
      <EmptyState
        icon="category"
        title="Chưa có loại tri thức"
        description="Tạo loại tri thức để phân loại tài liệu"
      />
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {types.map((type) => (
        <div
          key={type.id}
          className="bg-card rounded-xl p-5 border border-border shadow-sahara hover:border-primary/30 transition-colors"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <span
                className="w-4 h-4 rounded-full shrink-0"
                style={{ backgroundColor: type.color }}
              />
              <div>
                <h3 className="text-sm font-semibold text-foreground">{type.name}</h3>
                <p className="text-xs text-muted-foreground font-mono">{type.slug}</p>
              </div>
            </div>
            {type.source_count !== undefined && (
              <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
                {type.source_count} tài liệu
              </span>
            )}
          </div>

          {type.description && (
            <p className="text-xs text-muted-foreground mb-3 line-clamp-2">
              {type.description}
            </p>
          )}

          <div className="flex gap-2 pt-2 border-t border-border">
            <Button variant="ghost" size="sm" onClick={() => onEdit(type)} className="text-xs">
              <span className="material-symbols-outlined text-sm mr-1">edit</span>
              Sửa
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleDelete(type.id)}
              className="text-xs text-destructive hover:text-destructive"
            >
              <span className="material-symbols-outlined text-sm mr-1">delete</span>
              Xoá
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
