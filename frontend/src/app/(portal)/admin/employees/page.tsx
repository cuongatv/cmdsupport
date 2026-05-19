"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmployeeTable } from "@/components/employees/employee-table";
import { EmployeeDialog } from "@/components/employees/employee-dialog";
import { ProvinceAssignmentTab } from "@/components/employees/province-assignment-tab";

export type Department = {
  id: string;
  name: string;
};

export type Role = {
  id: string;
  name: string;
};

export type Employee = {
  id: string;
  name: string;
  email: string;
  /** Optional in legacy responses; backend now guarantees it post-035. */
  username?: string;
  role: string;
  department_id: string;
  department_name: string;
  is_active: boolean;
  has_token: boolean;
  last_connected?: string;
  custom_role_id?: string;
  custom_role_name?: string;
  phone?: string | null;
  zalo_phone?: string | null;
  effective_zalo_phone?: string | null;
  slogan?: string | null;
  avatar_url?: string | null;
};

type PaginatedResponse = {
  items: Employee[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export default function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<string>("users");
  const pageSize = 20;

  const loadEmployees = useCallback(async (p = 1, s = "") => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: String(pageSize) });
      if (s) params.set("search", s);
      const data = await api<PaginatedResponse>(`/api/employees?${params}`);
      setEmployees(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch {
      setEmployees([]);
    } finally {
      setLoading(false);
    }
     
  }, []);

  useEffect(() => {
    loadEmployees();
    api<Department[]>("/api/departments").then(setDepartments).catch(() => {});
    api<Role[]>("/api/roles").then(setRoles).catch(() => {});
  }, [loadEmployees]);

  const handleCreate = () => {
    setEditEmployee(null);
    setDialogOpen(true);
  };

  const handleEdit = (emp: Employee) => {
    setEditEmployee(emp);
    setDialogOpen(true);
  };

  const handleSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    loadEmployees(1, q);
  };

  return (
    <>
      <PageHeader
        title="Tổ chức"
        description="Quản lý tài khoản người dùng và thông tin cán bộ phụ trách Chi nhánh."
        action={
          tab === "users" ? (
            <Button
              onClick={handleCreate}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base mr-1">
                person_add
              </span>
              Thêm người dùng
            </Button>
          ) : null
        }
      />

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList variant="line" className="mb-4">
          <TabsTrigger value="users">Người dùng</TabsTrigger>
          <TabsTrigger value="branch-assignments">
            Thông tin phụ trách Chi nhánh
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <EmployeeTable
            employees={employees}
            loading={loading}
            onEdit={handleEdit}
            onRefresh={() => loadEmployees(page, search)}
            page={page}
            totalPages={totalPages}
            total={total}
            onPageChange={(p) => { setPage(p); loadEmployees(p, search); }}
            search={search}
            onSearch={handleSearch}
          />
        </TabsContent>

        <TabsContent value="branch-assignments">
          <ProvinceAssignmentTab />
        </TabsContent>
      </Tabs>

      <EmployeeDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        employee={editEmployee}
        departments={departments}
        roles={roles}
        onSaved={() => loadEmployees(page, search)}
      />
    </>
  );
}
