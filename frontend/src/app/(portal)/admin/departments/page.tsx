"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { DepartmentCards } from "@/components/departments/department-cards";
import { DepartmentDialog } from "@/components/departments/department-dialog";
import { type Department as DepartmentModel } from "@/lib/department-types";

type Department = DepartmentModel & {
  employee_count?: number;
  open_task_count?: number;
  task_count?: number;
  active_task_count?: number;
};

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editDept, setEditDept] = useState<Department | null>(null);

  const loadDepartments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Department[]>("/api/departments");
      setDepartments(data);
    } catch {
      setDepartments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDepartments();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [loadDepartments]);

  const handleCreate = () => {
    setEditDept(null);
    setDialogOpen(true);
  };

  const handleEdit = (dept: Department) => {
    setEditDept(dept);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Đơn vị"
        description="Tổ chức người dùng theo đơn vị và quản lý quyền truy cập tri thức."
        action={
          <Button
            onClick={handleCreate}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-base mr-1">
              add
            </span>
            Thêm đơn vị
          </Button>
        }
      />

      <DepartmentCards
        departments={departments}
        loading={loading}
        onEdit={handleEdit}
        onRefresh={loadDepartments}
      />

      <DepartmentDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        department={editDept}
        onSaved={loadDepartments}
      />
    </>
  );
}
