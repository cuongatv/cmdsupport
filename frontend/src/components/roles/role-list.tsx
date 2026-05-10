"use client";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import type { Role, PermissionInfo } from "./role-dialog";

type Props = {
  roles: Role[];
  loading: boolean;
  permissions: PermissionInfo[];
  onEdit: (role: Role) => void;
  onRefresh: () => void;
};

export function RoleList({ roles, loading, permissions, onEdit, onRefresh }: Props) {
  const labelMap = Object.fromEntries(permissions.map((p) => [p.key, p.label]));

  const handleDelete = async (role: Role) => {
    if (!confirm(`Xoá vai trò "${role.name}"? Người dùng được gán vai trò này sẽ mất quyền.`)) return;
    try {
      await api(`/api/roles/${role.id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Xoá thất bại");
    }
  };

  if (loading) {
    return (
      <div className="bg-card rounded-xl border border-border flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  if (roles.length === 0) {
    return (
      <div className="bg-card rounded-xl border border-border">
        <EmptyState
          icon="admin_panel_settings"
          title="Chưa có vai trò"
          description="Tạo vai trò để gán quyền cho người dùng"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {roles.map((role) => (
        <div
          key={role.id}
          className="bg-card rounded-xl border border-border px-5 py-4 flex items-start justify-between gap-4"
        >
          <div className="flex flex-col gap-2 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{role.name}</span>
              {role.is_system && (
                <Badge variant="secondary" className="text-xs">Hệ thống</Badge>
              )}
            </div>
            {role.description && (
              <p className="text-xs text-muted-foreground">{role.description}</p>
            )}
            <div className="flex flex-wrap gap-1.5 mt-1">
              {role.permissions.length === 0 ? (
                <span className="text-xs text-muted-foreground">Không có quyền</span>
              ) : (
                role.permissions.map((p) => (
                  <Badge key={p} variant="outline" className="text-xs font-normal">
                    {labelMap[p] ?? p}
                  </Badge>
                ))
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Button variant="outline" size="sm" onClick={() => onEdit(role)}>
              <span className="material-symbols-outlined text-base mr-1">edit</span>
              Sửa
            </Button>
            {!role.is_system && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => handleDelete(role)}
              >
                <span className="material-symbols-outlined text-base mr-1">delete</span>
                Xoá
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
