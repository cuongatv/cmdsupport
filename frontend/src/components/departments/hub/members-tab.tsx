"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox";
import { CheckIcon, ChevronDownIcon } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import {
  addDepartmentMember,
  listDepartmentMembers,
  patchMembership,
  removeMembership,
  setMembershipPrimary,
} from "@/lib/department-api";
import {
  getMembershipRoleLabel,
  getRolesForUnitType,
  type DepartmentMember,
  type MembershipRole,
  type UnitType,
} from "@/lib/department-types";

type Props = {
  departmentId: string;
  unitType: UnitType;
};

type EmployeeOption = {
  id: string;
  name: string;
  email: string;
};

type EmployeesResponse = {
  items: EmployeeOption[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

type ParsedCapacity =
  | { ok: true; value: number | null }
  | { ok: false };

function parseCapacityInput(raw: string): ParsedCapacity {
  const trimmed = raw.trim();
  if (trimmed === "") return { ok: true, value: null };
  if (!/^[0-9]+$/.test(trimmed)) return { ok: false };
  const n = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(n) || n < 0 || n > 100) return { ok: false };
  return { ok: true, value: n };
}

export function MembersTab({ departmentId, unitType }: Props) {
  const allowedRoles = useMemo(
    () => getRolesForUnitType(unitType),
    [unitType],
  );

  const [members, setMembers] = useState<DepartmentMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyRowId, setBusyRowId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] =
    useState<DepartmentMember | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  const loadMembers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDepartmentMembers(departmentId);
      setMembers(data);
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được danh sách thành viên"));
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  useEffect(() => {
    // Defer to next tick — same pattern the hub page uses to keep the React
    // 19 compiler happy about set-state-in-effect chains.
    const timer = window.setTimeout(() => {
      void loadMembers();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadMembers]);

  const handleChangeRole = async (
    member: DepartmentMember,
    role: MembershipRole,
  ) => {
    if (role === member.role) return;
    setBusyRowId(member.id);
    setError(null);
    try {
      await patchMembership(member.id, { role });
      await loadMembers();
    } catch (err) {
      setError(getErrorMessage(err, "Cập nhật vai trò thất bại"));
    } finally {
      setBusyRowId(null);
    }
  };

  const handleCommitCapacity = async (
    member: DepartmentMember,
    raw: string,
  ) => {
    const parsed = parseCapacityInput(raw);
    if (!parsed.ok) {
      setError("Tỉ lệ tham gia phải là số nguyên từ 0 đến 100");
      return;
    }
    const current = member.capacity_percent ?? null;
    if (parsed.value === current) return;
    setBusyRowId(member.id);
    setError(null);
    try {
      await patchMembership(member.id, { capacity_percent: parsed.value });
      await loadMembers();
    } catch (err) {
      setError(getErrorMessage(err, "Cập nhật tỉ lệ tham gia thất bại"));
    } finally {
      setBusyRowId(null);
    }
  };

  const handleSetPrimary = async (member: DepartmentMember) => {
    if (member.is_primary) return;
    setBusyRowId(member.id);
    setError(null);
    try {
      await setMembershipPrimary(member.id);
      await loadMembers();
    } catch (err) {
      setError(getErrorMessage(err, "Đặt làm đơn vị chính thất bại"));
    } finally {
      setBusyRowId(null);
    }
  };

  const handleToggleActive = async (member: DepartmentMember) => {
    setBusyRowId(member.id);
    setError(null);
    try {
      await patchMembership(member.id, { is_active: !member.is_active });
      await loadMembers();
    } catch (err) {
      setError(getErrorMessage(err, "Đổi trạng thái thất bại"));
    } finally {
      setBusyRowId(null);
    }
  };

  const handleConfirmRemove = async () => {
    if (!removeTarget) return;
    setRemoveBusy(true);
    setError(null);
    try {
      await removeMembership(removeTarget.id);
      setRemoveTarget(null);
      await loadMembers();
    } catch (err) {
      setError(getErrorMessage(err, "Xoá thành viên thất bại"));
    } finally {
      setRemoveBusy(false);
    }
  };

  const existingMemberIds = useMemo(
    () => new Set(members.map((m) => m.employee_id)),
    [members],
  );

  if (loading) {
    return (
      <div
        className="flex flex-col gap-3"
        data-testid="dept-tab-panel-members"
        data-department-id={departmentId}
      >
        <div className="h-9 w-44 self-end bg-muted/60 animate-pulse rounded" />
        <div className="h-56 w-full bg-muted/40 animate-pulse rounded-xl" />
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-3"
      data-testid="dept-tab-panel-members"
      data-department-id={departmentId}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-muted-foreground">
          Tổng cộng {members.length} thành viên
        </div>
        <Button
          size="sm"
          onClick={() => setAddOpen(true)}
          data-testid="member-add"
        >
          <span className="material-symbols-outlined text-base">
            person_add
          </span>
          Thêm thành viên
        </Button>
      </div>

      {error && (
        <p
          role="alert"
          className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
        >
          {error}
        </p>
      )}

      {/* List or empty */}
      {members.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sahara">
          <EmptyState
            icon="group_off"
            title="Chưa có thành viên"
            description="Bấm 'Thêm thành viên' để gán nhân sự vào đơn vị này."
          />
        </div>
      ) : (
        <div className="bg-card rounded-xl border border-border shadow-sahara overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Họ tên</TableHead>
                <TableHead className="w-44">Vai trò</TableHead>
                <TableHead className="w-32" title="Tỉ lệ thời gian nhân sự dành cho đơn vị này (tham khảo)">Tỉ lệ tham gia (%)</TableHead>
                <TableHead className="w-32">Trạng thái</TableHead>
                <TableHead className="w-36">Primary</TableHead>
                <TableHead className="w-44 text-right">Hành động</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <MemberRow
                  key={member.id}
                  member={member}
                  allowedRoles={allowedRoles}
                  busy={busyRowId === member.id}
                  onChangeRole={(role) => handleChangeRole(member, role)}
                  onCommitCapacity={(raw) => handleCommitCapacity(member, raw)}
                  onSetPrimary={() => handleSetPrimary(member)}
                  onToggleActive={() => handleToggleActive(member)}
                  onRequestRemove={() => setRemoveTarget(member)}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddMemberDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        departmentId={departmentId}
        unitType={unitType}
        existingMemberIds={existingMemberIds}
        onAdded={async () => {
          setAddOpen(false);
          await loadMembers();
        }}
      />

      {/* Remove confirm */}
      <Dialog
        open={removeTarget !== null}
        onOpenChange={(open) => {
          if (!open && !removeBusy) setRemoveTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xoá khỏi đơn vị?</DialogTitle>
            <DialogDescription>
              {removeTarget ? (
                <>
                  Thành viên &ldquo;
                  {removeTarget.employee_name ?? removeTarget.employee_id}
                  &rdquo; sẽ bị gỡ khỏi đơn vị. Hành động này không thể hoàn
                  tác từ giao diện.
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRemoveTarget(null)}
              disabled={removeBusy}
            >
              Huỷ
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleConfirmRemove}
              disabled={removeBusy}
              data-testid="member-remove-confirm"
            >
              {removeBusy ? "Đang xoá…" : "Xoá khỏi đơn vị"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

type RowProps = {
  member: DepartmentMember;
  allowedRoles: ReadonlyArray<MembershipRole>;
  busy: boolean;
  onChangeRole: (role: MembershipRole) => void;
  onCommitCapacity: (raw: string) => void;
  onSetPrimary: () => void;
  onToggleActive: () => void;
  onRequestRemove: () => void;
};

function MemberRow({
  member,
  allowedRoles,
  busy,
  onChangeRole,
  onCommitCapacity,
  onSetPrimary,
  onToggleActive,
  onRequestRemove,
}: RowProps) {
  const baseCapacity =
    member.capacity_percent === null || member.capacity_percent === undefined
      ? ""
      : String(member.capacity_percent);

  const [capacityDraft, setCapacityDraft] = useState(baseCapacity);
  // Track the last-seen base value so we can resync the local draft when
  // the underlying member capacity changes (e.g. after a refetch). This
  // setState-during-render comparator pattern avoids the React 19
  // set-state-in-effect warning that a useEffect-based resync would
  // trigger.
  const [prevBaseCapacity, setPrevBaseCapacity] = useState(baseCapacity);
  if (baseCapacity !== prevBaseCapacity) {
    setPrevBaseCapacity(baseCapacity);
    setCapacityDraft(baseCapacity);
  }

  return (
    <TableRow data-testid={`member-row-${member.employee_id}`}>
      <TableCell className="font-medium">
        {member.employee_name ?? member.employee_id}
      </TableCell>
      <TableCell>
        <Select
          value={member.role}
          onValueChange={(val) => {
            if (val) onChangeRole(val as MembershipRole);
          }}
          disabled={busy}
        >
          <SelectTrigger size="sm" className="h-7 w-full">
            <SelectValue>
              {(v: string | null) =>
                v ? getMembershipRoleLabel(v as MembershipRole) : ""
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {allowedRoles.map((r) => (
              <SelectItem key={r} value={r}>
                {getMembershipRoleLabel(r)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Input
          type="text"
          inputMode="numeric"
          value={capacityDraft}
          onChange={(e) => setCapacityDraft(e.target.value)}
          onBlur={() => {
            if (capacityDraft !== baseCapacity) {
              onCommitCapacity(capacityDraft);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.currentTarget.blur();
            } else if (e.key === "Escape") {
              setCapacityDraft(baseCapacity);
              e.currentTarget.blur();
            }
          }}
          disabled={busy}
          placeholder="—"
          className="h-7 w-20"
              aria-label="Tỉ lệ tham gia"
        />
      </TableCell>
      <TableCell>
        <Badge
          variant={member.is_active ? "outline" : "secondary"}
          className="text-xs"
        >
          {member.is_active ? "Hoạt động" : "Tạm dừng"}
        </Badge>
      </TableCell>
      <TableCell>
        {member.is_primary ? (
          <Badge variant="default" className="text-xs">
            Đơn vị chính
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <div className="inline-flex items-center gap-1 justify-end">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={busy || member.is_primary}
            onClick={onSetPrimary}
            title="Đặt làm đơn vị chính"
            aria-label="Đặt làm đơn vị chính"
            data-testid={`member-set-primary-${member.employee_id}`}
          >
            <span className="material-symbols-outlined text-base">
              push_pin
            </span>
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={busy}
            onClick={onToggleActive}
            title={member.is_active ? "Bỏ kích hoạt" : "Kích hoạt"}
            aria-label={member.is_active ? "Bỏ kích hoạt" : "Kích hoạt"}
            data-testid={`member-toggle-active-${member.employee_id}`}
          >
            <span className="material-symbols-outlined text-base">
              {member.is_active ? "pause_circle" : "play_circle"}
            </span>
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={busy}
            onClick={onRequestRemove}
            title="Xoá khỏi đơn vị"
            aria-label="Xoá khỏi đơn vị"
            data-testid={`member-remove-${member.employee_id}`}
          >
            <span className="material-symbols-outlined text-base text-destructive">
              person_remove
            </span>
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

type AddDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  departmentId: string;
  unitType: UnitType;
  existingMemberIds: ReadonlySet<string>;
  onAdded: () => Promise<void>;
};

function AddMemberDialog({
  open,
  onOpenChange,
  departmentId,
  unitType,
  existingMemberIds,
  onAdded,
}: AddDialogProps) {
  const allowedRoles = useMemo(
    () => getRolesForUnitType(unitType),
    [unitType],
  );
  const defaultRole: MembershipRole = allowedRoles[0] ?? "member";

  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [loadingEmployees, setLoadingEmployees] = useState(false);
  const [employeesError, setEmployeesError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedEmpId, setSelectedEmpId] = useState("");
  const [role, setRole] = useState<MembershipRole>(defaultRole);
  const [capacityRaw, setCapacityRaw] = useState("");
  const [isPrimaryChecked, setIsPrimaryChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Reset the form whenever the dialog transitions from closed to open.
  // setState-during-render comparator pattern (cf. React 19 docs) — avoids
  // the set-state-in-effect warning a useEffect-based reset would raise.
  const [wasOpen, setWasOpen] = useState(false);
  if (open && !wasOpen) {
    setWasOpen(true);
    setSearch("");
    setSelectedEmpId("");
    setRole(defaultRole);
    setCapacityRaw("");
    setIsPrimaryChecked(false);
    setSubmitError(null);
    setEmployeesError(null);
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  // Debounced employee search.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const handle = window.setTimeout(async () => {
      setLoadingEmployees(true);
      try {
        const params = new URLSearchParams({
          page: "1",
          page_size: "50",
        });
        const trimmed = search.trim();
        if (trimmed) params.set("search", trimmed);
        const data = await api<EmployeesResponse>(
          `/api/employees?${params.toString()}`,
        );
        if (cancelled) return;
        setEmployees(data.items ?? []);
        setEmployeesError(null);
      } catch (err) {
        if (cancelled) return;
        setEmployees([]);
        setEmployeesError(
          getErrorMessage(err, "Không tải được danh sách nhân sự"),
        );
      } finally {
        if (!cancelled) setLoadingEmployees(false);
      }
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [open, search]);

  const availableEmployees = useMemo(
    () => employees.filter((e) => !existingMemberIds.has(e.id)),
    [employees, existingMemberIds],
  );

  const handleSubmit = async () => {
    if (!selectedEmpId) {
      setSubmitError("Vui lòng chọn nhân sự");
      return;
    }
    const parsed = parseCapacityInput(capacityRaw);
    if (!parsed.ok) {
      setSubmitError("Tỉ lệ tham gia phải là số nguyên từ 0 đến 100");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await addDepartmentMember(departmentId, {
        employee_id: selectedEmpId,
        role,
        ...(parsed.value !== null ? { capacity_percent: parsed.value } : {}),
        set_primary: isPrimaryChecked,
      });
      await onAdded();
    } catch (err) {
      setSubmitError(getErrorMessage(err, "Thêm thành viên thất bại"));
    } finally {
      setSubmitting(false);
    }
  };

  const selectedEmployee = employees.find((e) => e.id === selectedEmpId);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && submitting) return;
        onOpenChange(next);
      }}
    >
      <DialogContent
        className="sm:max-w-md"
        data-testid="member-add-dialog"
      >
        <DialogHeader>
          <DialogTitle>Thêm thành viên</DialogTitle>
          <DialogDescription>
            Tìm và chọn nhân sự, đặt vai trò trong đơn vị, và tỉ lệ tham gia
            (tuỳ chọn — chỉ là metadata cho việc lập kế hoạch).
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-member-employee">Nhân sự</Label>
            <ComboboxPrimitive.Root
              items={availableEmployees}
              value={selectedEmployee ?? null}
              onValueChange={(item) =>
                setSelectedEmpId(
                  item && typeof item === "object" && "id" in item
                    ? (item as EmployeeOption).id
                    : "",
                )
              }
              inputValue={search}
              onInputValueChange={(v) => setSearch(v)}
              itemToStringLabel={(item: EmployeeOption) =>
                `${item.name} — ${item.email}`
              }
              itemToStringValue={(item: EmployeeOption) => item.id}
              isItemEqualToValue={(item: EmployeeOption, value: EmployeeOption) =>
                item.id === value.id
              }
              disabled={submitting}
              openOnInputClick
            >
              <div className="relative">
                <ComboboxPrimitive.Input
                  id="add-member-employee"
                  placeholder={
                    loadingEmployees
                      ? "Đang tải…"
                      : "Gõ tên hoặc email để tìm…"
                  }
                  className="flex w-full items-center rounded-lg border border-input bg-background px-3 py-2 pr-10 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <ComboboxPrimitive.Trigger
                  aria-label="Mở danh sách"
                  className="absolute right-2 top-1/2 -translate-y-1/2 flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  <ChevronDownIcon className="size-4" />
                </ComboboxPrimitive.Trigger>
              </div>
              <ComboboxPrimitive.Portal>
                <ComboboxPrimitive.Positioner sideOffset={4} className="outline-none z-50">
                  <ComboboxPrimitive.Popup className="max-h-72 overflow-y-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md min-w-[var(--anchor-width)]">
                    <ComboboxPrimitive.Empty className="px-3 py-2 text-xs text-muted-foreground">
                      {loadingEmployees
                        ? "Đang tải…"
                        : "Không có nhân sự nào phù hợp"}
                    </ComboboxPrimitive.Empty>
                    <ComboboxPrimitive.List>
                      {(item: EmployeeOption) => (
                        <ComboboxPrimitive.Item
                          key={item.id}
                          value={item}
                          className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
                        >
                          <ComboboxPrimitive.ItemIndicator className="flex h-4 w-4 items-center justify-center">
                            <CheckIcon className="size-4" />
                          </ComboboxPrimitive.ItemIndicator>
                          <span className="flex-1 truncate pl-1 data-[selected]:font-medium">
                            <span className="font-medium">{item.name}</span>
                            <span className="text-muted-foreground ml-2 text-xs">
                              {item.email}
                            </span>
                          </span>
                        </ComboboxPrimitive.Item>
                      )}
                    </ComboboxPrimitive.List>
                  </ComboboxPrimitive.Popup>
                </ComboboxPrimitive.Positioner>
              </ComboboxPrimitive.Portal>
            </ComboboxPrimitive.Root>
            {employeesError && (
              <p className="text-xs text-destructive">{employeesError}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-member-role">Vai trò</Label>
            <Select
              value={role}
              onValueChange={(val) => {
                if (val) setRole(val as MembershipRole);
              }}
              disabled={submitting}
            >
              <SelectTrigger id="add-member-role" className="w-full">
                <SelectValue>
                  {(v: string | null) =>
                    v ? getMembershipRoleLabel(v as MembershipRole) : "Chọn vai trò"
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {allowedRoles.map((r) => (
                  <SelectItem key={r} value={r}>
                    {getMembershipRoleLabel(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-member-capacity">
              Tỉ lệ tham gia (%) — tuỳ chọn
            </Label>
            <Input
              id="add-member-capacity"
              inputMode="numeric"
              placeholder="0 – 100"
              value={capacityRaw}
              onChange={(e) => setCapacityRaw(e.target.value)}
              disabled={submitting}
            />
            <p className="text-xs text-muted-foreground">
              Phần trăm thời gian nhân sự dành cho đơn vị này. Mang tính tham
              khảo (lập kế hoạch nhân sự, không ảnh hưởng phân quyền). Để trống
              nếu không cần.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <Checkbox
              checked={isPrimaryChecked}
              onCheckedChange={setIsPrimaryChecked}
              disabled={submitting}
            />
            Đặt làm đơn vị chính của nhân sự
          </label>

          {submitError && (
            <p
              role="alert"
              className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
            >
              {submitError}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Huỷ
            </Button>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={submitting || !selectedEmpId}
              data-testid="member-add-submit"
            >
              {submitting ? "Đang thêm…" : "Thêm thành viên"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
