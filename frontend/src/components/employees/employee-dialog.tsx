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

// jpg/jpeg/png/webp only — server enforces the same list.
const AVATAR_ACCEPT = "image/jpeg,image/jpg,image/png,image/webp";
const AVATAR_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const AVATAR_MAX_BYTES = 5 * 1024 * 1024;

type Department = { id: string; name: string };
type Role = { id: string; name: string; is_system?: boolean };
type Employee = {
  id: string;
  name: string;
  email: string;
  role: string;
  department_id: string;
  custom_role_id?: string;
  phone?: string | null;
  zalo_phone?: string | null;
  slogan?: string | null;
  avatar_url?: string | null;
};

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
  }, [employee, open, departments]);

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
      const body: Record<string, string | null> = {
        name,
        email,
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
              <Label>Đơn vị</Label>
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
            >
              Huỷ
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? "Đang lưu…" : isEdit ? "Cập nhật" : "Tạo"}
            </Button>
          </div>
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
