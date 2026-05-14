import { api } from "@/lib/api";
import type {
  Department,
  DepartmentMember,
  DepartmentSkill,
  DepartmentSource,
  MembershipRole,
} from "@/lib/department-types";

export function listDepartmentMembers(deptId: string): Promise<DepartmentMember[]> {
  return api<DepartmentMember[]>(`/api/departments/${deptId}/members`);
}

export function listEmployeeMemberships(
  employeeId: string,
  options?: { includeInactive?: boolean }
): Promise<DepartmentMember[]> {
  const qs = options?.includeInactive ? "?include_inactive=true" : "";
  return api<DepartmentMember[]>(`/api/employees/${employeeId}/memberships${qs}`);
}

export function addDepartmentMember(
  deptId: string,
  payload: {
    employee_id: string;
    role: MembershipRole;
    capacity_percent?: number;
    set_primary?: boolean;
  }
): Promise<DepartmentMember> {
  return api<DepartmentMember>(`/api/departments/${deptId}/members`, {
    method: "POST",
    body: payload,
  });
}

export function patchMembership(
  membershipId: string,
  payload: {
    role?: MembershipRole;
    capacity_percent?: number | null;
    is_active?: boolean;
  }
): Promise<DepartmentMember> {
  return api<DepartmentMember>(`/api/memberships/${membershipId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function setMembershipPrimary(membershipId: string): Promise<DepartmentMember> {
  return api<DepartmentMember>(`/api/memberships/${membershipId}/primary`, {
    method: "PATCH",
  });
}

export function removeMembership(membershipId: string): Promise<void> {
  return api<void>(`/api/memberships/${membershipId}`, {
    method: "DELETE",
  });
}

export function archiveDepartment(deptId: string): Promise<{ archived: boolean } | void> {
  return api<{ archived: boolean } | void>(`/api/departments/${deptId}/archive`, {
    method: "POST",
  });
}

export function unarchiveDepartment(deptId: string): Promise<{ unarchived: boolean } | void> {
  return api<{ unarchived: boolean } | void>(`/api/departments/${deptId}/unarchive`, {
    method: "POST",
  });
}

export function updateDepartment(
  deptId: string,
  payload: {
    name?: string;
    description?: string | null;
  }
): Promise<Department> {
  return api<Department>(`/api/departments/${deptId}`, {
    method: "PATCH",
    body: payload,
  });
}

// ---------------------------------------------------------------------------
// Department × Source (Knowledge tab)
// ---------------------------------------------------------------------------

export function listDepartmentSources(deptId: string): Promise<DepartmentSource[]> {
  return api<DepartmentSource[]>(`/api/departments/${deptId}/sources`);
}

export function attachDepartmentSource(
  deptId: string,
  sourceId: string
): Promise<{ attached: boolean; already?: boolean }> {
  return api<{ attached: boolean; already?: boolean }>(
    `/api/departments/${deptId}/sources/${sourceId}`,
    { method: "POST" }
  );
}

export function detachDepartmentSource(
  deptId: string,
  sourceId: string
): Promise<{ detached: boolean }> {
  return api<{ detached: boolean }>(
    `/api/departments/${deptId}/sources/${sourceId}`,
    { method: "DELETE" }
  );
}

// ---------------------------------------------------------------------------
// Department × Skill (Skills tab)
// ---------------------------------------------------------------------------

export function listDepartmentSkills(deptId: string): Promise<DepartmentSkill[]> {
  return api<DepartmentSkill[]>(`/api/departments/${deptId}/skills`);
}

export function attachDepartmentSkill(
  deptId: string,
  skillId: string
): Promise<DepartmentSkill> {
  return api<DepartmentSkill>(
    `/api/departments/${deptId}/skills/${skillId}`,
    { method: "POST" }
  );
}

export function detachDepartmentSkill(
  deptId: string,
  skillId: string
): Promise<{ detached: boolean }> {
  return api<{ detached: boolean }>(
    `/api/departments/${deptId}/skills/${skillId}`,
    { method: "DELETE" }
  );
}
