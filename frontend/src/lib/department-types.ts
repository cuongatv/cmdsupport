export type UnitType = "business_group" | "squad_team";

export const UNIT_TYPE_LABEL = {
  business_group: "Nhóm nghiệp vụ",
  squad_team: "Squad Team",
} as const satisfies Record<UnitType, string>;

export type MembershipRole =
  | "lead"
  | "deputy_lead"
  | "controller"
  | "member"
  | "product_owner"
  | "scrum_master"
  | "developer";

export const MEMBERSHIP_ROLE_LABEL = {
  lead: "Trưởng nhóm",
  deputy_lead: "Phó trưởng nhóm",
  controller: "Kiểm soát viên",
  member: "Thành viên",
  product_owner: "Product Owner",
  scrum_master: "Scrum Master",
  developer: "Developer",
} as const satisfies Record<MembershipRole, string>;

export const BUSINESS_GROUP_ROLES: MembershipRole[] = [
  "lead",
  "deputy_lead",
  "controller",
  "member",
];

export const SQUAD_TEAM_ROLES: MembershipRole[] = [
  "lead",
  "deputy_lead",
  "controller",
  "member",
  "product_owner",
  "scrum_master",
  "developer",
];

export function getRolesForUnitType(unitType: UnitType): MembershipRole[] {
  return unitType === "business_group" ? BUSINESS_GROUP_ROLES : SQUAD_TEAM_ROLES;
}

export function getMembershipRoleLabel(role: MembershipRole): string {
  return MEMBERSHIP_ROLE_LABEL[role];
}

export interface Department {
  id: string;
  name: string;
  description?: string | null;
  unit_type: UnitType;
  is_archived: boolean;
  archived_at?: string | null;
  member_count?: number;
  user_count?: number;
}

export interface DepartmentMember {
  id: string;
  employee_id: string;
  department_id: string;
  role: MembershipRole;
  capacity_percent?: number | null;
  is_primary: boolean;
  is_active: boolean;
  employee_name?: string | null;
}

export interface DepartmentSkill {
  id: string;
  name: string;
  slug: string;
  current_version: number;
  status: string;
  updated_at: string;
}

export interface DepartmentSource {
  source_id: string;
  title?: string | null;
  source_type?: string | null;
  file_name?: string | null;
  status: string;
  knowledge_type_name?: string | null;
}
