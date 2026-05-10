import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EmptyState } from "@/components/shared/empty-state";
import { api } from "@/lib/api";
import { Member, Employee, Project } from "./types";

const ROLE_DESCRIPTIONS: Record<string, string[]> = {
  viewer: [
    "Xem thành viên, tài liệu và trang tri thức của không gian nghiệp vụ",
    "Xem đồ thị tri thức và mục lục wiki",
    "Không có quyền khác",
  ],
  contributor: [
    "Tất cả quyền của Xem",
    "Đề xuất bản nháp trang tri thức (chờ biên tập duyệt)",
    "Đề xuất chỉnh sửa qua MCP (propose_wiki_edit)",
  ],
  editor: [
    "Tất cả quyền của Đóng góp",
    "Sửa trực tiếp trang tri thức (không cần duyệt)",
    "Duyệt hoặc từ chối bản nháp",
    "Thêm hoặc gỡ tài liệu nguồn (liên kết, tải lên, thêm URL)",
    "Duyệt bản nháp qua MCP (list_pending_drafts, review_draft, approve_draft, reject_draft)",
    "Sửa wiki qua MCP (edit_wiki_page)",
  ],
  admin: [
    "Tất cả quyền của Biên tập",
    "Thêm hoặc gỡ thành viên",
    "Thay đổi vai trò thành viên",
    "Đổi tên hoặc lưu trữ không gian nghiệp vụ",
    "Không thể xoá không gian nghiệp vụ (chỉ quản trị hệ thống mới xoá được)",
    "Không thể xoá hoặc hạ quyền chính mình nếu là quản trị cuối cùng",
  ],
};

type Props = {
  project: Project;
  members: Member[];
  isAdmin: boolean;
  availableEmployees: Employee[];
  onChanged: () => Promise<void>;
  onError: (msg: string | null) => void;
};

export function MembersTab({
  project,
  members,
  isAdmin,
  availableEmployees,
  onChanged,
  onError,
}: Props) {
  const [selectedEmpId, setSelectedEmpId] = useState("");
  const [updatingRoleFor, setUpdatingRoleFor] = useState<string | null>(null);

  const handleAddMember = async () => {
    if (!selectedEmpId) return;
    onError(null);
    try {
      await api(`/api/projects/${project.id}/members`, {
        method: "POST",
        body: { employee_id: selectedEmpId, role: "member" },
      });
      setSelectedEmpId("");
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to add member");
    }
  };

  const handleRemoveMember = async (empId: string) => {
    if (!confirm("Gỡ thành viên này khỏi không gian nghiệp vụ?")) return;
    onError(null);
    try {
      await api(`/api/projects/${project.id}/members/${empId}`, { method: "DELETE" });
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to remove member");
    }
  };

  const handleUpdateRole = async (empId: string, newRole: string) => {
    onError(null);
    setUpdatingRoleFor(empId);
    try {
      await api(`/api/projects/${project.id}/members/${empId}`, {
        method: "PATCH",
        body: { role: newRole },
      });
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to update role");
    } finally {
      setUpdatingRoleFor(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {isAdmin && (
        <div className="bg-card rounded-xl border border-border shadow-sahara p-4 flex gap-2">
          <Select value={selectedEmpId} onValueChange={(v) => setSelectedEmpId(v ?? "")}>
            <SelectTrigger className="bg-background flex-1">
              {selectedEmpId ? (
                <span className="truncate">
                  {(() => {
                    const emp = availableEmployees.find((e) => e.id === selectedEmpId);
                    return emp ? `${emp.name} — ${emp.email}` : selectedEmpId;
                  })()}
                </span>
              ) : (
                <SelectValue placeholder="Chọn người dùng để thêm..." />
              )}
            </SelectTrigger>
            <SelectContent>
              {availableEmployees.map((e) => (
                <SelectItem key={e.id} value={e.id}>
                  {e.name} — {e.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            disabled={!selectedEmpId}
            onClick={handleAddMember}
            className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0"
          >
            Thêm
          </Button>
        </div>
      )}

      {members.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sahara">
          <EmptyState icon="group" title="Chưa có thành viên" description="Thêm người dùng để cấp quyền truy cập tri thức của không gian nghiệp vụ này." />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {members.map((m) => (
            <div
              key={m.employee_id}
              className="bg-card rounded-xl border border-border shadow-sahara p-4 flex items-start gap-3 group hover:border-primary/20 transition-all"
            >
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-primary text-sm">person</span>
              </div>
              <div className="flex flex-col flex-1 min-w-0">
                <span className="text-sm font-medium truncate">{m.employee_name}</span>
                <span className="text-xs text-muted-foreground truncate">{m.employee_email}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger render={<div className="relative cursor-help" />}>
                        {isAdmin ? (
                          <Select
                            value={m.role}
                            onValueChange={(val) => { if (val) handleUpdateRole(m.employee_id, val) }}
                            disabled={updatingRoleFor === m.employee_id}
                          >
                            <SelectTrigger className="h-6 rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold capitalize bg-transparent shadow-sm focus:ring-0 w-auto min-w-[90px]">
                              {updatingRoleFor === m.employee_id ? (
                                <span className="material-symbols-outlined text-[14px] animate-spin mx-auto">progress_activity</span>
                              ) : (
                                <SelectValue placeholder={m.role} />
                              )}
                            </SelectTrigger>
                            <SelectContent side="bottom" align="end" alignItemWithTrigger={false} className="w-[480px]">
                              {Object.entries(ROLE_DESCRIPTIONS).map(([role, lines]) => (
                                <SelectItem key={role} value={role} className="whitespace-normal items-start p-3">
                                  <div className="flex flex-col text-left w-full pr-2">
                                    <span className="font-medium capitalize mb-1.5">{role}</span>
                                    <ul className="list-disc pl-3.5 text-[11px] text-muted-foreground space-y-1">
                                      {lines.map((line, i) => (
                                        <li key={i}>{line}</li>
                                      ))}
                                    </ul>
                                  </div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Badge variant="outline" className="text-xs capitalize">{m.role}</Badge>
                        )}
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-[480px] text-left p-3.5">
                      <div className="flex flex-col">
                        <span className="font-semibold capitalize mb-1.5 border-b border-background/20 pb-1.5">{m.role}</span>
                        <ul className="list-disc pl-4 text-[11px] opacity-90 space-y-1 mt-1.5">
                          {(ROLE_DESCRIPTIONS[m.role as keyof typeof ROLE_DESCRIPTIONS] || []).map((line, i) => (
                            <li key={i}>{line}</li>
                          ))}
                        </ul>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                {isAdmin && (
                  <button
                    onClick={() => handleRemoveMember(m.employee_id)}
                    className="text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <span className="material-symbols-outlined text-base">close</span>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
