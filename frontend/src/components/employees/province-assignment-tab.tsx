"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";

type EmployeeContact = {
  id: string;
  name: string;
  email: string;
  department_name: string;
  phone: string | null;
  zalo_phone: string | null;
  effective_zalo_phone: string | null;
  avatar_url: string | null;
  slogan: string | null;
  is_active: boolean;
};

type ProvinceAssignment = {
  province_id: string;
  province_code: string;
  province_name: string;
  province_short_name: string;
  province_type: string;
  region: string;
  assigned_employee_id: string | null;
  assigned_employee: EmployeeContact | null;
};

type EmployeeListItem = {
  id: string;
  name: string;
  email: string;
  department_name: string;
  is_active: boolean;
};

type EmployeesResponse = {
  items: EmployeeListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

const NONE_VALUE = "__none__";

const REGION_LABELS: Record<string, string> = {
  BAC: "Miền Bắc",
  TRUNG: "Miền Trung",
  NAM: "Miền Nam",
};

function regionLabel(region: string): string {
  return REGION_LABELS[region] ?? region;
}

export function ProvinceAssignmentTab() {
  const [assignments, setAssignments] = useState<ProvinceAssignment[]>([]);
  const [employees, setEmployees] = useState<EmployeeListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [provs, emps] = await Promise.all([
        api<ProvinceAssignment[]>("/api/province-assignments"),
        api<EmployeesResponse>("/api/employees?page=1&page_size=500"),
      ]);
      setAssignments(provs);
      setEmployees(emps.items.filter((e) => e.is_active));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dữ liệu");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const assignedCount = useMemo(
    () => assignments.filter((a) => a.assigned_employee_id).length,
    [assignments],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return assignments;
    return assignments.filter(
      (a) =>
        a.province_name.toLowerCase().includes(q) ||
        a.province_short_name.toLowerCase().includes(q) ||
        a.province_code.toLowerCase().includes(q),
    );
  }, [assignments, search]);

  const handleChange = useCallback(
    async (province: ProvinceAssignment, employeeId: string | null) => {
      setSavingId(province.province_id);
      setError(null);
      try {
        const updated = await api<ProvinceAssignment>(
          `/api/province-assignments/${province.province_id}`,
          {
            method: "PATCH",
            body: { employee_id: employeeId },
          },
        );
        setAssignments((prev) =>
          prev.map((p) =>
            p.province_id === updated.province_id ? updated : p,
          ),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Cập nhật thất bại");
      } finally {
        setSavingId(null);
      }
    },
    [],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h3 className="text-base font-semibold">
              Cán bộ Trụ sở chính phụ trách Chi nhánh
            </h3>
            <p className="text-sm text-muted-foreground max-w-2xl">
              Khai báo cán bộ phụ trách từng tỉnh/thành phố. Thông tin này sẽ
              được hiển thị ở cuối phần kết quả màn hình Tư vấn KHDN tương ứng
              với tỉnh khách hàng chọn.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground tabular-nums">
            <Badge variant="secondary" className="h-6 px-2 text-xs">
              {assignedCount}/{assignments.length} đã phân công
            </Badge>
          </div>
        </div>
        <div className="mt-3 relative max-w-sm">
          <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
            search
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm tỉnh/thành phố…"
            className="h-9 w-full pl-9 pr-3 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50"
          />
        </div>
      </div>

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg flex items-center gap-2">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </div>
      )}

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon="location_on"
            title="Không có tỉnh/thành phố"
            description={
              search
                ? `Không tìm thấy tỉnh/thành phố phù hợp "${search}"`
                : "Chưa có dữ liệu tỉnh/thành phố."
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Tỉnh/Thành phố
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Vùng
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Cán bộ phụ trách
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Liên hệ
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((row) => {
                const selectedId = row.assigned_employee_id ?? NONE_VALUE;
                const saving = savingId === row.province_id;
                return (
                  <TableRow
                    key={row.province_id}
                    className="hover:bg-secondary/30 transition-colors"
                  >
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-foreground">
                          {row.province_name}
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {row.province_short_name} · {row.province_type}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {regionLabel(row.region)}
                      </span>
                    </TableCell>
                    <TableCell className="min-w-[240px]">
                      <Select
                        value={selectedId}
                        onValueChange={(v) => {
                          const nextId = v === NONE_VALUE ? null : v;
                          if ((row.assigned_employee_id ?? null) === nextId) return;
                          handleChange(row, nextId);
                        }}
                      >
                        <SelectTrigger
                          className="bg-background h-9 w-full"
                          disabled={saving}
                        >
                          {saving ? (
                            <span className="flex items-center gap-2 text-sm">
                              <span className="material-symbols-outlined text-sm animate-spin">
                                progress_activity
                              </span>
                              Đang lưu…
                            </span>
                          ) : row.assigned_employee ? (
                            <span className="flex items-center gap-2 min-w-0">
                              <span className="text-sm truncate">
                                {row.assigned_employee.name}
                              </span>
                              <span className="text-[11px] text-muted-foreground truncate">
                                {row.assigned_employee.department_name}
                              </span>
                            </span>
                          ) : (
                            <span className="text-sm text-muted-foreground">
                              Chưa phân công
                            </span>
                          )}
                        </SelectTrigger>
                        <SelectContent className="!w-max min-w-(--anchor-width) max-h-[320px]">
                          <SelectItem value={NONE_VALUE}>
                            <span className="text-muted-foreground">
                              Bỏ phân công
                            </span>
                          </SelectItem>
                          <div className="h-px bg-border my-1 -mx-1" />
                          {employees.map((emp) => (
                            <SelectItem key={emp.id} value={emp.id}>
                              <span className="flex flex-col gap-0.5">
                                <span className="text-sm">{emp.name}</span>
                                <span className="text-[11px] text-muted-foreground">
                                  {emp.department_name} · {emp.email}
                                </span>
                              </span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      {row.assigned_employee ? (
                        <div className="flex flex-col gap-0.5 text-xs">
                          <span className="text-foreground">
                            {row.assigned_employee.phone || "—"}
                          </span>
                          <span className="text-muted-foreground">
                            Zalo:{" "}
                            {row.assigned_employee.effective_zalo_phone || "—"}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground/60">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
