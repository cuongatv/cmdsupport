"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import {
  attachDepartmentSkill,
  detachDepartmentSkill,
  listDepartmentSkills,
} from "@/lib/department-api";
import { useAuth } from "@/lib/auth";
import type { DepartmentSkill, UnitType } from "@/lib/department-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SkillSearchDialog } from "@/components/skills/skill-search-dialog";
import type { Skill } from "@/components/skills/skill-card";

// Hub page passes both fields to every tab for symmetry. Skills aren't
// restricted by business_group vs squad_team, so `unitType` is accepted
// (for the contract) but not destructured.
type Props = {
  departmentId: string;
  unitType: UnitType;
};

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getDate()).padStart(2, "0")}/${String(
    d.getMonth() + 1
  ).padStart(2, "0")}/${d.getFullYear()}`;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function SkillsTab(props: Props) {
  const { departmentId } = props;
  const { canAccess } = useAuth();
  const canManage = canAccess("skill", "edit");

  const [skills, setSkills] = useState<DepartmentSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDetach, setConfirmDetach] = useState<DepartmentSkill | null>(
    null
  );

  const loadSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDepartmentSkills(departmentId);
      setSkills(data);
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được danh sách kỹ năng"));
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  useEffect(() => {
    // Defer one tick to keep React 19 compiler happy with the
    // setState-in-effect chain inside loadSkills — matches the hub page.
    const timerId = window.setTimeout(() => {
      void loadSkills();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadSkills]);

  const handleAttach = async (skill: Skill) => {
    setActionError(null);
    setBusyId(skill.id);
    try {
      await attachDepartmentSkill(departmentId, skill.id);
      await loadSkills();
    } catch (err) {
      setActionError(getErrorMessage(err, "Gắn kỹ năng thất bại"));
    } finally {
      setBusyId(null);
    }
  };

  const handleConfirmDetach = async () => {
    if (!confirmDetach) return;
    setActionError(null);
    setBusyId(confirmDetach.id);
    try {
      await detachDepartmentSkill(departmentId, confirmDetach.id);
      setConfirmDetach(null);
      await loadSkills();
    } catch (err) {
      setActionError(getErrorMessage(err, "Gỡ kỹ năng thất bại"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      className="flex flex-col gap-4"
      data-testid="dept-tab-panel-skills"
      data-department-id={departmentId}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="material-symbols-outlined text-base">
            psychology
          </span>
          <span>
            <strong className="text-foreground">{skills.length}</strong> kỹ năng
            đã gắn
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void loadSkills()}
            disabled={loading}
            data-testid="dept-skills-refresh"
            aria-label="Làm mới danh sách kỹ năng"
          >
            <span className="material-symbols-outlined text-base">refresh</span>
          </Button>
          {canManage && (
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                setActionError(null);
                setPickerOpen(true);
              }}
              data-testid="dept-skills-attach-btn"
            >
              <span className="material-symbols-outlined text-base">add</span>
              Gắn kỹ năng
            </Button>
          )}
        </div>
      </div>

      {actionError && (
        <p
          className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
          role="alert"
          data-testid="dept-skills-action-error"
        >
          {actionError}
        </p>
      )}

      {/* Body */}
      {loading ? (
        <div
          className="flex flex-col gap-2"
          data-testid="dept-skills-loading"
          aria-busy="true"
        >
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-16 w-full bg-muted/40 animate-pulse rounded-xl"
            />
          ))}
        </div>
      ) : error ? (
        <div
          className="flex flex-col items-center justify-center py-12 px-4 rounded-xl border border-destructive/30 bg-destructive/5 gap-3"
          data-testid="dept-skills-error"
        >
          <span className="material-symbols-outlined text-3xl text-destructive">
            error
          </span>
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={() => void loadSkills()}>
            Thử lại
          </Button>
        </div>
      ) : skills.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-16 px-4 rounded-xl border border-dashed border-border bg-card/50"
          data-testid="dept-skills-empty"
        >
          <span className="material-symbols-outlined text-5xl text-muted-foreground/40 mb-4">
            psychology
          </span>
          <h3 className="text-lg font-medium text-foreground mb-1">
            Chưa có kỹ năng nào
          </h3>
          <p className="text-sm text-muted-foreground text-center max-w-sm">
            Đơn vị này chưa có kỹ năng AI nào được gắn. Bấm{" "}
            <strong>Gắn kỹ năng</strong> để chọn kỹ năng từ danh mục.
          </p>
        </div>
      ) : (
        <ul
          className="flex flex-col gap-2"
          data-testid="dept-skills-list"
          role="list"
        >
          {skills.map((skill) => {
            const isBusy = busyId === skill.id;
            const isDeleting = skill.status === "deleting";
            return (
              <li
                key={skill.id}
                className="bg-card rounded-xl p-4 border border-border hover:border-primary/30 transition-colors flex items-center gap-3"
                data-testid="dept-skills-item"
                data-skill-id={skill.id}
              >
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined text-primary text-lg">
                    bolt
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p
                      className="text-sm font-medium text-foreground truncate"
                      title={skill.name}
                    >
                      {skill.name}
                    </p>
                    <Badge
                      variant="secondary"
                      className="text-[10px] px-1.5 py-0 font-bold"
                    >
                      v{skill.current_version}
                    </Badge>
                    {isDeleting && (
                      <Badge variant="destructive" className="text-[10px]">
                        Đang xoá
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Cập nhật {formatDate(skill.updated_at)}
                  </p>
                </div>
                {canManage && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => {
                      setActionError(null);
                      setConfirmDetach(skill);
                    }}
                    disabled={isBusy || isDeleting}
                    data-testid="dept-skills-detach-btn"
                    aria-label={`Gỡ kỹ năng ${skill.name}`}
                  >
                    <span className="material-symbols-outlined text-base">
                      link_off
                    </span>
                    Gỡ
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* Attach dialog (skill picker) */}
      <SkillSearchDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(skill) => {
          void handleAttach(skill);
        }}
      />

      {/* Detach confirm */}
      <Dialog
        open={confirmDetach !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmDetach(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Gỡ kỹ năng khỏi đơn vị?</DialogTitle>
            <DialogDescription>
              Kỹ năng &ldquo;{confirmDetach?.name}&rdquo; sẽ không còn gắn với
              đơn vị này. Bạn có thể gắn lại bất cứ lúc nào.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmDetach(null)}
              disabled={busyId === confirmDetach?.id}
            >
              Huỷ
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void handleConfirmDetach()}
              disabled={busyId === confirmDetach?.id}
              data-testid="dept-skills-detach-confirm"
            >
              {busyId === confirmDetach?.id ? "Đang gỡ…" : "Gỡ kỹ năng"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
