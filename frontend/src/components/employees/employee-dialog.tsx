"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  MEMBERSHIP_ROLE_LABEL,
  UNIT_TYPE_LABEL,
  getRolesForUnitType,
  type MembershipRole,
  type UnitType,
} from "@/lib/department-types";
import {
  addDepartmentMember,
  listEmployeeMemberships,
  patchMembership,
  removeMembership,
} from "@/lib/department-api";

// jpg/jpeg/png/webp only — server enforces the same list.
const AVATAR_ACCEPT = "image/jpeg,image/jpg,image/png,image/webp";
const AVATAR_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const AVATAR_MAX_BYTES = 5 * 1024 * 1024;

type Department = { id: string; name: string; unit_type?: UnitType };
type Role = { id: string; name: string; is_system?: boolean };
type Employee = {
  id: string;
  name: string;
  email: string;
  /** Optional for backwards compatibility; backend now always populates it. */
  username?: string;
  role: string;
  department_id: string;
  custom_role_id?: string;
  phone?: string | null;
  zalo_phone?: string | null;
  slogan?: string | null;
  avatar_url?: string | null;
};

const USERNAME_RE = /^[a-z0-9._-]{3,100}$/;

// Local row state for the "Các đơn vị khác" editable list. `membershipId` is
// null until the row is persisted; the `original*` fields snapshot the
// loaded values so we can diff against them on submit without re-fetching.
type SecondaryRow = {
  rowKey: string;
  membershipId: string | null;
  originalDepartmentId: string | null;
  originalRole: MembershipRole | null;
  originalCapacity: number | null;
  departmentId: string;
  role: MembershipRole | "";
  capacityPercent: string;
};

let SECONDARY_ROW_SEQ = 0;
function nextRowKey(): string {
  SECONDARY_ROW_SEQ += 1;
  return `row-${SECONDARY_ROW_SEQ}`;
}

function unitTypeOf(dept: Department | undefined): UnitType {
  return dept?.unit_type ?? "business_group";
}

function parseCapacity(raw: string): { ok: true; value: number | null } | { ok: false } {
  const trimmed = raw.trim();
  if (trimmed === "") return { ok: true, value: null };
  if (!/^[0-9]+$/.test(trimmed)) return { ok: false };
  const n = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(n) || n < 0 || n > 100) return { ok: false };
  return { ok: true, value: n };
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee: Employee | null; // null = create mode
  departments: Department[];
  roles?: Role[];
  onSaved: () => void;
};

export function EmployeeDialog({
  open,
  onOpenChange,
  employee,
  departments,
  roles = [],
  onSaved,
}: Props) {
  const isEdit = !!employee;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("employee");
  const [deptId, setDeptId] = useState("");
  const [customRoleId, setCustomRoleId] = useState("");
  const [phone, setPhone] = useState("");
  const [zaloPhone, setZaloPhone] = useState("");
  const [slogan, setSlogan] = useState("");
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [localRoles, setLocalRoles] = useState<Role[]>([]);
  const [localDepartments, setLocalDepartments] = useState<Department[]>([]);
  const [secondaries, setSecondaries] = useState<SecondaryRow[]>([]);
  const [removedMembershipIds, setRemovedMembershipIds] = useState<string[]>([]);
  const [loadingMemberships, setLoadingMemberships] = useState(false);
  const [inlinePrompt, setInlinePrompt] = useState({
    open: false,
    title: "",
    label: "",
    value: "",
    saving: false,
    error: "",
    onSubmit: async (val: string) => {},
  });

  useEffect(() => {
    setLocalRoles(roles.filter(r => !r.is_system));
  }, [roles]);

  useEffect(() => {
    setLocalDepartments(departments);
  }, [departments]);

  const handleCreateDepartment = () => {
    setInlinePrompt({
      open: true,
      title: "Tạo đơn vị",
      label: "Tên đơn vị",
      value: "",
      saving: false,
      error: "",
      onSubmit: async (val) => {
        const newDept = await api<Department>("/api/departments", {
          method: "POST",
          body: { name: val, description: "" }
        });
        setLocalDepartments(prev => [...prev, newDept]);
        setDeptId(newDept.id);
        setInlinePrompt(p => ({ ...p, open: false }));
      }
    });
  };

  const handleCreateRole = () => {
    setInlinePrompt({
      open: true,
      title: "Tạo chức vụ",
      label: "Tên chức vụ",
      value: "",
      saving: false,
      error: "",
      onSubmit: async (val) => {
        const newRole = await api<Role>("/api/roles", {
          method: "POST",
          body: { name: val, permissions: [] }
        });
        setLocalRoles(prev => [...prev, newRole]);
        setCustomRoleId(newRole.id);
        setInlinePrompt(p => ({ ...p, open: false }));
      }
    });
  };

  const submitInlinePrompt = async () => {
    if (!inlinePrompt.value.trim()) return;
    setInlinePrompt(p => ({ ...p, saving: true, error: "" }));
    try {
      await inlinePrompt.onSubmit(inlinePrompt.value.trim());
    } catch (err) {
      setInlinePrompt(p => ({ ...p, saving: false, error: err instanceof Error ? err.message : String(err) }));
    }
  };

  useEffect(() => {
    if (employee) {
      setName(employee.name);
      setEmail(employee.email);
      setUsername(employee.username ?? "");
      setRole(employee.role);
      setDeptId(employee.department_id);
      setCustomRoleId(employee.custom_role_id || "");
      setPassword("");
      setPhone(employee.phone ?? "");
      setZaloPhone(employee.zalo_phone ?? "");
      setSlogan(employee.slogan ?? "");
      setAvatarPreview(employee.avatar_url ?? null);
    } else {
      setName("");
      setEmail("");
      setUsername("");
      setPassword("");
      setRole("employee");
      setDeptId(departments[0]?.id || "");
      setCustomRoleId("");
      setPhone("");
      setZaloPhone("");
      setSlogan("");
      setAvatarPreview(null);
    }
    setAvatarFile(null);
    setRemoveAvatar(false);
    if (avatarInputRef.current) avatarInputRef.current.value = "";
    setError("");
    setSecondaries([]);
    setRemovedMembershipIds([]);
  }, [employee, open, departments]);

  // Load secondary memberships when editing an existing employee. The primary
  // membership is identified by the employee's `department_id` and excluded
  // from the secondaries list — the primary select handles it.
  useEffect(() => {
    if (!open || !employee) return;
    let cancelled = false;
    const employeeId = employee.id;
    const primaryDeptId = employee.department_id;
    setLoadingMemberships(true);
    listEmployeeMemberships(employeeId)
      .then((rows) => {
        if (cancelled) return;
        const filtered = rows
          .filter((m) => m.is_active)
          .filter((m) => !(m.is_primary && m.department_id === primaryDeptId))
          .filter((m) => m.department_id !== primaryDeptId);
        setSecondaries(
          filtered.map((m) => ({
            rowKey: nextRowKey(),
            membershipId: m.id,
            originalDepartmentId: m.department_id,
            originalRole: m.role,
            originalCapacity: m.capacity_percent ?? null,
            departmentId: m.department_id,
            role: m.role,
            capacityPercent:
              m.capacity_percent === null || m.capacity_percent === undefined
                ? ""
                : String(m.capacity_percent),
          }))
        );
      })
      .catch(() => {
        // Surface as form-level error so the admin sees the failure but the
        // primary section remains usable.
        if (!cancelled) {
          setError("Không thể tải danh sách đơn vị khác. Hãy thử lại.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingMemberships(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, employee]);

  const handleAddSecondary = () => {
    setSecondaries((prev) => [
      ...prev,
      {
        rowKey: nextRowKey(),
        membershipId: null,
        originalDepartmentId: null,
        originalRole: null,
        originalCapacity: null,
        departmentId: "",
        role: "",
        capacityPercent: "",
      },
    ]);
  };

  const handleRemoveSecondary = (rowKey: string) => {
    setSecondaries((prev) => {
      const target = prev.find((r) => r.rowKey === rowKey);
      if (target?.membershipId) {
        setRemovedMembershipIds((ids) =>
          ids.includes(target.membershipId!) ? ids : [...ids, target.membershipId!]
        );
      }
      return prev.filter((r) => r.rowKey !== rowKey);
    });
  };

  const handleSecondaryDeptChange = (rowKey: string, newDeptId: string) => {
    setSecondaries((prev) =>
      prev.map((r) => {
        if (r.rowKey !== rowKey) return r;
        // If unit_type changes, drop the role so the next pick is valid.
        const prevDept = localDepartments.find((d) => d.id === r.departmentId);
        const nextDept = localDepartments.find((d) => d.id === newDeptId);
        const sameUnitType =
          prevDept && nextDept && unitTypeOf(prevDept) === unitTypeOf(nextDept);
        return {
          ...r,
          departmentId: newDeptId,
          role: sameUnitType ? r.role : "",
        };
      })
    );
  };

  const handleSecondaryRoleChange = (rowKey: string, value: MembershipRole) => {
    setSecondaries((prev) =>
      prev.map((r) => (r.rowKey === rowKey ? { ...r, role: value } : r))
    );
  };

  const handleSecondaryCapacityChange = (rowKey: string, value: string) => {
    setSecondaries((prev) =>
      prev.map((r) => (r.rowKey === rowKey ? { ...r, capacityPercent: value } : r))
    );
  };

  const handleAvatarChange = (file: File | null) => {
    if (!file) {
      setAvatarFile(null);
      return;
    }
    const nameLower = file.name.toLowerCase();
    const extOk = AVATAR_ALLOWED_EXTENSIONS.some((ext) => nameLower.endsWith(ext));
    if (!extOk) {
      setError("Định dạng ảnh không hợp lệ. Chỉ chấp nhận jpg, jpeg, png, webp.");
      if (avatarInputRef.current) avatarInputRef.current.value = "";
      return;
    }
    if (file.size > AVATAR_MAX_BYTES) {
      setError(`Ảnh quá lớn (tối đa ${AVATAR_MAX_BYTES / 1024 / 1024} MB).`);
      if (avatarInputRef.current) avatarInputRef.current.value = "";
      return;
    }
    setError("");
    setAvatarFile(file);
    setRemoveAvatar(false);
    // Local preview without a network round-trip.
    const reader = new FileReader();
    reader.onload = () => setAvatarPreview(typeof reader.result === "string" ? reader.result : null);
    reader.readAsDataURL(file);
  };

  const handleRemoveAvatar = () => {
    setAvatarFile(null);
    setAvatarPreview(null);
    setRemoveAvatar(true);
    if (avatarInputRef.current) avatarInputRef.current.value = "";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      // Pre-validate secondary rows before touching the network so a typo in
      // capacity_percent doesn't leave the employee half-saved.
      type SecondaryPlan = {
        row: SecondaryRow;
        capacity: number | null;
      };
      const effective: SecondaryPlan[] = [];
      const seenDepts = new Set<string>();
      for (const r of secondaries) {
        const hasDept = !!r.departmentId;
        const hasRole = !!r.role;
        if (!hasDept && !hasRole && r.capacityPercent.trim() === "") {
          continue; // empty draft row
        }
        if (!hasDept) {
          throw new Error("Hãy chọn đơn vị cho mọi dòng đơn vị khác.");
        }
        if (!hasRole) {
          throw new Error("Hãy chọn vai trò cho mọi đơn vị khác đã chọn.");
        }
        if (r.departmentId === deptId) {
          throw new Error("Đơn vị khác không được trùng với đơn vị chính.");
        }
        if (seenDepts.has(r.departmentId)) {
          throw new Error("Mỗi đơn vị chỉ được thêm một lần.");
        }
        seenDepts.add(r.departmentId);
        const cap = parseCapacity(r.capacityPercent);
        if (!cap.ok) {
          throw new Error("Tỉ lệ tham gia (%) phải là số nguyên từ 0 đến 100.");
        }
        effective.push({ row: r, capacity: cap.value });
      }

      const normalisedUsername = username.trim().toLowerCase();
      if (!USERNAME_RE.test(normalisedUsername)) {
        throw new Error(
          "Tên đăng nhập chỉ chấp nhận chữ thường, số và các ký tự . _ - (3-100 ký tự).",
        );
      }
      const body: Record<string, string | null> = {
        name,
        email,
        username: normalisedUsername,
        role,
        department_id: deptId,
        custom_role_id: customRoleId || null,
        phone: phone.trim() || null,
        zalo_phone: zaloPhone.trim() || null,
        slogan: slogan.trim() || null,
      };
      if (password) body.password = password;

      let targetId: string;
      if (isEdit) {
        await api(`/api/employees/${employee.id}`, { method: "PUT", body });
        targetId = employee.id;
      } else {
        if (!password) {
          setError("Mật khẩu là bắt buộc");
          setSaving(false);
          return;
        }
        const created = await api<{ id: string }>("/api/employees", { method: "POST", body });
        targetId = created.id;
      }

      // Avatar is uploaded in a second request — keeps the create payload as
      // plain JSON and mirrors how sources.py handles files.
      if (avatarFile) {
        const fd = new FormData();
        fd.append("file", avatarFile);
        await apiUpload(`/api/employees/${targetId}/avatar`, fd);
      } else if (isEdit && removeAvatar) {
        await api(`/api/employees/${targetId}/avatar`, { method: "DELETE" });
      }

      // Sync secondary memberships: removes first, then patches, then adds.
      // Each step runs sequentially so a partial failure (e.g. role/unit_type
      // mismatch returned by the server) surfaces immediately with context.
      type Op =
        | { kind: "remove"; membershipId: string }
        | {
            kind: "patch";
            membershipId: string;
            role: MembershipRole;
            capacity: number | null;
          }
        | {
            kind: "add";
            departmentId: string;
            role: MembershipRole;
            capacity: number | null;
          };

      const ops: Op[] = [];
      for (const id of removedMembershipIds) {
        ops.push({ kind: "remove", membershipId: id });
      }
      for (const { row, capacity } of effective) {
        // role is non-empty here (validated above).
        const role = row.role as MembershipRole;
        if (row.membershipId) {
          if (row.departmentId !== row.originalDepartmentId) {
            ops.push({ kind: "remove", membershipId: row.membershipId });
            ops.push({
              kind: "add",
              departmentId: row.departmentId,
              role,
              capacity,
            });
          } else {
            const roleChanged = role !== row.originalRole;
            const capacityChanged = capacity !== (row.originalCapacity ?? null);
            if (roleChanged || capacityChanged) {
              ops.push({
                kind: "patch",
                membershipId: row.membershipId,
                role,
                capacity,
              });
            }
          }
        } else {
          ops.push({
            kind: "add",
            departmentId: row.departmentId,
            role,
            capacity,
          });
        }
      }

      const removes = ops.filter((op) => op.kind === "remove");
      const patches = ops.filter((op) => op.kind === "patch");
      const adds = ops.filter((op) => op.kind === "add");
      const ordered: Op[] = [...removes, ...patches, ...adds];

      for (const op of ordered) {
        if (op.kind === "remove") {
          await removeMembership(op.membershipId);
        } else if (op.kind === "patch") {
          await patchMembership(op.membershipId, {
            role: op.role,
            capacity_percent: op.capacity,
          });
        } else {
          await addDepartmentMember(op.departmentId, {
            employee_id: targetId,
            role: op.role,
            ...(op.capacity !== null ? { capacity_percent: op.capacity } : {}),
          });
        }
      }

      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {isEdit ? "Sửa người dùng" : "Thêm người dùng"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <fieldset disabled={saving} className="contents">
          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-name">Tên</Label>
            <Input
              id="emp-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-email">Email</Label>
            <Input
              id="emp-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-username">Tên đăng nhập</Label>
            <Input
              id="emp-username"
              type="text"
              value={username}
              onChange={(e) =>
                setUsername(
                  // Live-normalise: lowercase, strip whitespace inside the
                  // field so the user can't accidentally store "Admin " and
                  // wonder why login fails.
                  e.target.value.toLowerCase().replace(/\s+/g, ""),
                )
              }
              required
              autoComplete="off"
              minLength={3}
              maxLength={100}
              pattern="[a-z0-9._\-]{3,100}"
              placeholder="vd: nguyen.van.a"
              className="bg-background"
            />
            <span className="text-[11px] text-muted-foreground">
              Chữ thường, số và <code>. _ -</code> · 3–100 ký tự · phải duy
              nhất trong hệ thống.
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-password">
              Mật khẩu {isEdit && "(để trống nếu giữ nguyên)"}
            </Label>
            <Input
              id="emp-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isEdit ? "••••••••" : "Tối thiểu 8 ký tự"}
              className="bg-background"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label>Vai trò hệ thống</Label>
              <Select value={role} onValueChange={(v) => v && setRole(v)}>
                <SelectTrigger className="bg-background">
                  {role === "admin" ? "Admin" : role === "employee" ? "Employee" : <SelectValue />}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="employee">Nhân viên</SelectItem>
                  <SelectItem value="admin">Quản trị</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <Label>Đơn vị chính</Label>
              <Select 
                value={deptId} 
                onValueChange={(v) => {
                  if (v === "__new__") {
                    handleCreateDepartment();
                    return;
                  }
                  if (v) setDeptId(v);
                }}
              >
                <SelectTrigger className="bg-background">
                  {deptId ? (localDepartments.find(d => d.id === deptId)?.name || deptId) : <SelectValue placeholder="Chọn" />}
                </SelectTrigger>
                <SelectContent className="!w-max min-w-(--anchor-width)">
                  {localDepartments.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                  <div className="h-px bg-border my-1 -mx-1" />
                  <SelectItem value="__new__" className="text-primary font-medium focus:text-primary">
                    <span className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm">add</span>
                      Tạo đơn vị mới…
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <Label>Các đơn vị khác</Label>
              {loadingMemberships && (
                <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1">
                  <span className="material-symbols-outlined text-sm animate-spin">
                    progress_activity
                  </span>
                  Đang tải…
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Tham gia thêm đơn vị khác ngoài đơn vị chính. Vai trò được lọc theo loại đơn vị.
            </p>
            <div className="flex flex-col gap-2">
              {secondaries.map((row) => {
                const dept = localDepartments.find((d) => d.id === row.departmentId);
                const unitType = unitTypeOf(dept);
                const availableRoles = getRolesForUnitType(unitType);
                const availableDepartments = localDepartments.filter(
                  (d) =>
                    d.id !== deptId &&
                    (d.id === row.departmentId ||
                      !secondaries.some(
                        (other) =>
                          other.rowKey !== row.rowKey &&
                          other.departmentId === d.id
                      ))
                );
                return (
                  <div
                    key={row.rowKey}
                    className="rounded-lg border border-border bg-background p-3 flex flex-col gap-2 sm:flex-row sm:items-end"
                  >
                    <div className="flex flex-col gap-1 flex-1 min-w-0">
                      <Label className="text-[11px] text-muted-foreground">
                        Đơn vị
                      </Label>
                      <Select
                        value={row.departmentId}
                        onValueChange={(v) => {
                          if (v) handleSecondaryDeptChange(row.rowKey, v);
                        }}
                      >
                        <SelectTrigger className="bg-background">
                          {row.departmentId ? (
                            <span className="flex items-center gap-2 truncate">
                              <span className="truncate">
                                {dept?.name || row.departmentId}
                              </span>
                              {dept && (
                                <span className="text-[10px] text-muted-foreground shrink-0">
                                  {UNIT_TYPE_LABEL[unitTypeOf(dept)]}
                                </span>
                              )}
                            </span>
                          ) : (
                            <SelectValue placeholder="Chọn đơn vị" />
                          )}
                        </SelectTrigger>
                        <SelectContent className="!w-max min-w-(--anchor-width)">
                          {availableDepartments.length === 0 ? (
                            <SelectItem value="__none__" disabled>
                              Không có đơn vị khả dụng
                            </SelectItem>
                          ) : (
                            availableDepartments.map((d) => (
                              <SelectItem key={d.id} value={d.id}>
                                <span className="flex items-center gap-2">
                                  <span>{d.name}</span>
                                  <span className="text-[10px] text-muted-foreground">
                                    {UNIT_TYPE_LABEL[unitTypeOf(d)]}
                                  </span>
                                </span>
                              </SelectItem>
                            ))
                          )}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex flex-col gap-1 flex-1 min-w-0">
                      <Label className="text-[11px] text-muted-foreground">
                        Vai trò
                      </Label>
                      <Select
                        value={row.role || ""}
                        onValueChange={(v) => {
                          if (v) handleSecondaryRoleChange(row.rowKey, v as MembershipRole);
                        }}
                      >
                        <SelectTrigger className="bg-background" disabled={!row.departmentId}>
                          {row.role ? (
                            MEMBERSHIP_ROLE_LABEL[row.role]
                          ) : (
                            <SelectValue
                              placeholder={
                                row.departmentId ? "Chọn vai trò" : "Chọn đơn vị trước"
                              }
                            />
                          )}
                        </SelectTrigger>
                        <SelectContent className="!w-max min-w-(--anchor-width)">
                          {availableRoles.map((r) => (
                            <SelectItem key={r} value={r}>
                              {MEMBERSHIP_ROLE_LABEL[r]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex flex-col gap-1 w-full sm:w-28">
                      <Label
                        className="text-[11px] text-muted-foreground"
                        title="Phần trăm thời gian dành cho đơn vị này (tham khảo)"
                      >
                        Tỉ lệ tham gia (%)
                      </Label>
                      <Input
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={100}
                        step={1}
                        value={row.capacityPercent}
                        onChange={(e) =>
                          handleSecondaryCapacityChange(row.rowKey, e.target.value)
                        }
                        placeholder="Trống"
                        className="bg-background"
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive shrink-0"
                      onClick={() => handleRemoveSecondary(row.rowKey)}
                    >
                      Xóa
                    </Button>
                  </div>
                );
              })}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddSecondary}
              className="self-start"
            >
              <span className="material-symbols-outlined text-base mr-1" style={{ fontSize: 16 }}>
                add
              </span>
              Thêm đơn vị
            </Button>
          </div>

          {role === "employee" && (
            <div className="flex flex-col gap-2">
              <Label>Chức vụ</Label>
              <Select
                value={customRoleId || "__none__"}
                onValueChange={(v) => {
                  if (v === "__new__") {
                    handleCreateRole();
                    return;
                  }
                  setCustomRoleId(v === "__none__" ? "" : (v ?? ""));
                }}
              >
                <SelectTrigger className="bg-background">
                  {customRoleId ? (localRoles.find(r => r.id === customRoleId)?.name || customRoleId) : "Không"}
                </SelectTrigger>
                <SelectContent className="!w-max min-w-(--anchor-width)">
                  <SelectItem value="__none__">Không</SelectItem>
                  {localRoles.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                    </SelectItem>
                  ))}
                  <div className="h-px bg-border my-1 -mx-1" />
                  <SelectItem value="__new__" className="text-primary font-medium focus:text-primary">
                    <span className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm">add</span>
                      Tạo chức vụ mới…
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="emp-phone">Số điện thoại</Label>
              <Input
                id="emp-phone"
                type="tel"
                inputMode="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="VD: 0901234567"
                className="bg-background"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="emp-zalo">Số điện thoại dùng Zalo</Label>
              <Input
                id="emp-zalo"
                type="tel"
                inputMode="tel"
                value={zaloPhone}
                onChange={(e) => setZaloPhone(e.target.value)}
                placeholder="Để trống sẽ dùng SĐT phía trên"
                className="bg-background"
              />
              <p className="text-[11px] text-muted-foreground">
                Bỏ trống: hệ thống tự dùng Số điện thoại cho tác vụ Zalo.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Ảnh đại diện</Label>
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full overflow-hidden bg-secondary flex items-center justify-center shrink-0 border border-border">
                {avatarPreview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={avatarPreview}
                    alt="Avatar preview"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="material-symbols-outlined text-2xl text-muted-foreground">
                    account_circle
                  </span>
                )}
              </div>
              <div className="flex flex-col gap-2 min-w-0">
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => avatarInputRef.current?.click()}
                  >
                    <span className="material-symbols-outlined text-base mr-1" style={{ fontSize: 16 }}>
                      upload
                    </span>
                    {avatarPreview ? "Đổi ảnh" : "Tải ảnh lên"}
                  </Button>
                  {avatarPreview && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleRemoveAvatar}
                      className="text-destructive hover:text-destructive"
                    >
                      Xoá ảnh
                    </Button>
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Định dạng: jpg, jpeg, png, webp. Tối đa 5 MB.
                </p>
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept={AVATAR_ACCEPT}
                  className="hidden"
                  onChange={(e) => handleAvatarChange(e.target.files?.[0] ?? null)}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-slogan">Slogan</Label>
            <textarea
              id="emp-slogan"
              value={slogan}
              onChange={(e) => setSlogan(e.target.value)}
              rows={2}
              placeholder="Câu nói/khẩu hiệu cá nhân"
              className="bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 resize-none"
            />
          </div>

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Huỷ
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? (
                <span className="inline-flex items-center gap-1">
                  <span className="material-symbols-outlined text-base animate-spin" style={{ fontSize: 16 }}>
                    progress_activity
                  </span>
                  Đang lưu…
                </span>
              ) : isEdit ? (
                "Cập nhật"
              ) : (
                "Tạo"
              )}
            </Button>
          </div>
          </fieldset>
        </form>
      </DialogContent>
    </Dialog>

      <Dialog open={inlinePrompt.open} onOpenChange={(o) => setInlinePrompt(p => ({ ...p, open: o }))}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{inlinePrompt.title}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-2">
              <Label>{inlinePrompt.label}</Label>
              <Input 
                value={inlinePrompt.value}
                onChange={e => setInlinePrompt(p => ({ ...p, value: e.target.value }))}
                autoFocus
                onKeyDown={e => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    submitInlinePrompt();
                  }
                }}
              />
            </div>
            {inlinePrompt.error && (
              <p className="text-destructive text-sm">{inlinePrompt.error}</p>
            )}
          </div>
          <div className="flex justify-end gap-2 mt-2">
            <Button type="button" variant="outline" onClick={() => setInlinePrompt(p => ({ ...p, open: false }))}>
              Huỷ
            </Button>
            <Button 
              disabled={inlinePrompt.saving || !inlinePrompt.value.trim()} 
              onClick={submitInlinePrompt}
            >
              {inlinePrompt.saving ? "Đang lưu…" : "Tạo"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
