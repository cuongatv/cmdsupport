"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { RoleList } from "@/components/roles/role-list";
import { RoleDialog, type Role, type PermissionInfo } from "@/components/roles/role-dialog";

export default function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<PermissionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editRole, setEditRole] = useState<Role | null>(null);

  const loadRoles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Role[]>("/api/roles");
      setRoles(data);
    } catch {
      setRoles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRoles();
    api<PermissionInfo[]>("/api/roles/permissions").then(setPermissions).catch(() => {});
  }, [loadRoles]);

  const handleCreate = () => {
    setEditRole(null);
    setDialogOpen(true);
  };

  const handleEdit = (role: Role) => {
    setEditRole(role);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Vai trò"
        description="Định nghĩa bộ quyền có thể gán cho người dùng."
        action={
          <Button
            onClick={handleCreate}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-base mr-1">add</span>
            Tạo vai trò
          </Button>
        }
      />

      <RoleList
        roles={roles}
        loading={loading}
        permissions={permissions}
        onEdit={handleEdit}
        onRefresh={loadRoles}
      />

      <RoleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        role={editRole}
        permissions={permissions}
        onSaved={loadRoles}
      />
    </>
  );
}
