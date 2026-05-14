"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { UNIT_TYPE_LABEL, type Department as DepartmentModel } from "@/lib/department-types";

type Department = DepartmentModel & {
  employee_count?: number;
  open_task_count?: number;
  task_count?: number;
  active_task_count?: number;
};

type Props = {
  departments: Department[];
  loading: boolean;
  onEdit: (dept: Department) => void;
  onRefresh: () => void;
};

export function DepartmentCards({ departments, loading, onEdit, onRefresh }: Props) {
  const handleDelete = async (id: string) => {
    if (!confirm("Xoá đơn vị này và tất cả người dùng thuộc đơn vị?")) return;
    await api(`/api/departments/${id}`, { method: "DELETE" });
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

  if (departments.length === 0) {
    return (
      <EmptyState
        icon="business"
        title="Chưa có đơn vị"
        description="Tạo đơn vị đầu tiên để tổ chức người dùng"
      />
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {departments.map((dept) => {
        const memberCount = dept.member_count ?? dept.employee_count ?? 0;
        const taskCount =
          dept.open_task_count ?? dept.task_count ?? dept.active_task_count;
        const stats = [`${memberCount} thành viên`];

        if (typeof taskCount === "number") {
          stats.push(`${taskCount} công việc mở`);
        }

        return (
          <div
            key={dept.id}
            className="bg-card rounded-xl p-6 border border-border shadow-sahara flex flex-col gap-4 hover:border-primary/30 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined text-primary">
                    business
                  </span>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-semibold text-foreground truncate">
                      {dept.name}
                    </h3>
                    {dept.unit_type && (
                      <Badge variant="secondary" className="text-[10px] h-5 px-2">
                        {UNIT_TYPE_LABEL[dept.unit_type]}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {stats.map((stat) => (
                <span
                  key={stat}
                  className="inline-flex items-center rounded-full bg-secondary/60 px-2.5 py-1"
                >
                  {stat}
                </span>
              ))}
            </div>

            {dept.description && (
              <p className="text-sm text-muted-foreground line-clamp-2">
                {dept.description}
              </p>
            )}

            <div className="flex flex-wrap gap-2 mt-auto pt-2 border-t border-border">
              <Link
                href={`/admin/departments/${dept.id}?tab=members`}
                data-testid="dept-card-open-hub"
                className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <span className="material-symbols-outlined text-sm mr-1">
                  open_in_new
                </span>
                Mở hub
              </Link>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onEdit(dept)}
                className="text-xs"
              >
                <span className="material-symbols-outlined text-sm mr-1">
                  edit
                </span>
                Sửa
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDelete(dept.id)}
                className="text-xs text-destructive hover:text-destructive"
              >
                <span className="material-symbols-outlined text-sm mr-1">
                  delete
                </span>
                Xoá
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
