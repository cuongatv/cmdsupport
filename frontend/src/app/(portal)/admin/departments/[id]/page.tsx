"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { archiveDepartment } from "@/lib/department-api";
import type { Department } from "@/lib/department-types";
import { UNIT_TYPE_LABEL } from "@/lib/department-types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MembersTab } from "@/components/departments/hub/members-tab";
import { KnowledgeTab } from "@/components/departments/hub/knowledge-tab";
import { SkillsTab } from "@/components/departments/hub/skills-tab";
import { WorkTab } from "@/components/departments/hub/work-tab";
import { SquadCapacityPanel } from "@/components/tasks/squad-capacity-panel";
import { FEATURE_AGILE_PHASE_3 } from "@/lib/feature-flags";

type HubTab = "members" | "knowledge" | "skills" | "work" | "agile";

const BASE_TABS: ReadonlyArray<HubTab> = [
  "members",
  "knowledge",
  "skills",
  "work",
];
const VALID_TABS: ReadonlyArray<HubTab> = FEATURE_AGILE_PHASE_3
  ? [...BASE_TABS, "agile"]
  : BASE_TABS;
const DEFAULT_TAB: HubTab = "members";

function parseTab(value: string | null): HubTab {
  if (!value) return DEFAULT_TAB;
  return (VALID_TABS as ReadonlyArray<string>).includes(value)
    ? (value as HubTab)
    : DEFAULT_TAB;
}

type TabConfigItem = { key: HubTab; label: string; icon: string };

const BASE_TAB_CONFIG: ReadonlyArray<TabConfigItem> = [
  { key: "members", label: "Thành viên", icon: "group" },
  { key: "knowledge", label: "Tri thức", icon: "auto_stories" },
  { key: "skills", label: "Kỹ năng", icon: "psychology" },
  { key: "work", label: "Công việc", icon: "task_alt" },
];
const TAB_CONFIG: ReadonlyArray<TabConfigItem> = FEATURE_AGILE_PHASE_3
  ? [
      ...BASE_TAB_CONFIG,
      { key: "agile", label: "Tổng quan Agile", icon: "monitoring" },
    ]
  : BASE_TAB_CONFIG;

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function DepartmentHubPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const departmentId = params.id as string;
  const currentTab = parseTab(searchParams.get("tab"));

  const [department, setDepartment] = useState<Department | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveDialogOpen, setArchiveDialogOpen] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const loadDepartment = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The list endpoint already returns unit_type / is_archived / member_count
      // per the T9 contract, so reuse it instead of relying on a single-record
      // GET that may not exist yet.
      const departments = await api<Department[]>("/api/departments");
      const found = departments.find((d) => d.id === departmentId) ?? null;
      if (!found) {
        setError("Không tìm thấy đơn vị");
        setDepartment(null);
      } else {
        setDepartment(found);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được thông tin đơn vị"));
      setDepartment(null);
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  useEffect(() => {
    // Defer to next tick so the React 19 compiler doesn't flag the
    // setState-in-effect chain inside loadDepartment (matches the pattern
    // used in admin/tasks/page.tsx).
    const timerId = window.setTimeout(() => {
      void loadDepartment();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadDepartment]);

  const handleSelectTab = (tab: HubTab) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set("tab", tab);
    router.replace(`/admin/departments/${departmentId}?${next.toString()}`);
  };

  const handleEdit = () => {
    router.push(`/admin/departments?edit=${departmentId}`);
  };

  const handleConfirmArchive = async () => {
    if (!department) return;
    setArchiving(true);
    setArchiveError(null);
    try {
      await archiveDepartment(department.id);
      setArchiveDialogOpen(false);
      await loadDepartment();
    } catch (err) {
      setArchiveError(getErrorMessage(err, "Lưu trữ đơn vị thất bại"));
    } finally {
      setArchiving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col gap-4" data-testid="dept-hub-loading">
        <div className="h-4 w-48 bg-muted/60 animate-pulse rounded" />
        <div className="h-10 w-72 bg-muted/60 animate-pulse rounded" />
        <div className="h-10 w-full bg-muted/40 animate-pulse rounded" />
        <div className="h-48 w-full bg-muted/40 animate-pulse rounded-xl" />
      </div>
    );
  }

  if (error || !department) {
    return (
      <div
        className="flex flex-col items-center justify-center py-16 gap-3"
        data-testid="dept-hub-error"
      >
        <span className="material-symbols-outlined text-4xl text-muted-foreground">
          domain_disabled
        </span>
        <p className="text-sm text-muted-foreground">
          {error ?? "Không tìm thấy đơn vị"}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/admin/departments")}
        >
          <span className="material-symbols-outlined text-base">
            arrow_back
          </span>
          Quay lại danh sách đơn vị
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5" data-testid="dept-hub-root">
      {/* Breadcrumb */}
      <nav
        className="flex items-center gap-1.5 text-xs text-muted-foreground"
        aria-label="Breadcrumb"
        data-testid="dept-hub-breadcrumb"
      >
        <button
          type="button"
          onClick={() => router.push("/admin")}
          className="hover:text-foreground transition-colors"
        >
          Admin
        </button>
        <span className="material-symbols-outlined text-sm">chevron_right</span>
        <button
          type="button"
          onClick={() => router.push("/admin/departments")}
          className="hover:text-foreground transition-colors"
        >
          Đơn vị
        </button>
        <span className="material-symbols-outlined text-sm">chevron_right</span>
        <span className="text-foreground truncate max-w-[260px]">
          {department.name}
        </span>
      </nav>

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-primary">
              {department.unit_type === "squad_team"
                ? "rocket_launch"
                : "business"}
            </span>
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2
                className="text-2xl lg:text-3xl tracking-tight text-foreground truncate"
                data-testid="dept-hub-title"
              >
                {department.name}
              </h2>
              <Badge
                variant="outline"
                className="text-xs"
                data-testid="dept-hub-unit-type"
              >
                {UNIT_TYPE_LABEL[department.unit_type]}
              </Badge>
              {department.is_archived && (
                <Badge
                  variant="secondary"
                  className="text-xs"
                  data-testid="dept-hub-archived-badge"
                >
                  Đã lưu trữ
                </Badge>
              )}
            </div>
            {department.description && (
              <p className="text-sm text-muted-foreground max-w-xl line-clamp-2">
                {department.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={handleEdit}
            data-testid="dept-hub-edit-btn"
          >
            <span className="material-symbols-outlined text-base">edit</span>
            Sửa
          </Button>
          {!department.is_archived && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setArchiveError(null);
                setArchiveDialogOpen(true);
              }}
              data-testid="dept-hub-archive-btn"
            >
              <span className="material-symbols-outlined text-base">
                inventory_2
              </span>
              Lưu trữ
            </Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="Mục đơn vị"
        className="flex items-end gap-1 border-b border-border overflow-x-auto"
      >
        {TAB_CONFIG.map((t) => {
          const selected = currentTab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              data-testid={`dept-tab-${t.key}`}
              aria-selected={selected}
              aria-controls={`dept-tab-panel-${t.key}`}
              onClick={() => handleSelectTab(t.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap ${
                selected
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="material-symbols-outlined text-base">
                {t.icon}
              </span>
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div
        role="tabpanel"
        id={`dept-tab-panel-${currentTab}`}
        aria-labelledby={`dept-tab-${currentTab}`}
        className="flex-1"
      >
        {currentTab === "members" && (
          <MembersTab
            departmentId={department.id}
            unitType={department.unit_type}
          />
        )}
        {currentTab === "knowledge" && (
          <KnowledgeTab
            departmentId={department.id}
            unitType={department.unit_type}
          />
        )}
        {currentTab === "skills" && (
          <SkillsTab
            departmentId={department.id}
            unitType={department.unit_type}
          />
        )}
        {currentTab === "work" && (
          <WorkTab
            departmentId={department.id}
            unitType={department.unit_type}
            departmentName={department.name}
          />
        )}
        {FEATURE_AGILE_PHASE_3 && currentTab === "agile" && (
          <SquadCapacityPanel departmentId={department.id} />
        )}
      </div>

      {/* Archive confirm dialog */}
      <Dialog open={archiveDialogOpen} onOpenChange={setArchiveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Lưu trữ đơn vị?</DialogTitle>
            <DialogDescription>
              Đơn vị &ldquo;{department.name}&rdquo; sẽ được đánh dấu đã lưu
              trữ. Mọi thành viên thuộc đơn vị sẽ bị huỷ kích hoạt và không thể
              tạo công việc mới.
            </DialogDescription>
          </DialogHeader>

          {archiveError && (
            <p
              className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
              role="alert"
            >
              {archiveError}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setArchiveDialogOpen(false)}
              disabled={archiving}
            >
              Huỷ
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleConfirmArchive}
              disabled={archiving}
              data-testid="dept-hub-archive-confirm"
            >
              {archiving ? "Đang lưu trữ…" : "Lưu trữ"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
