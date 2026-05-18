"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { ProjectList } from "@/components/projects/project-list";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { ProjectDetail } from "@/components/projects/project-detail";

// Project shape returned by `GET /api/projects`. Kept local to this view to
// preserve the verbatim behavior of the previous `/admin/page.tsx`.
export type Project = {
  id: string;
  name: string;
  description?: string;
  workspace_type: string;
  status: string;
  member_count: number;
  source_count: number;
  created_at: string;
};

// Classic dashboard — the entire legacy `/admin` experience (project list,
// create/edit dialog, detail drill-in, "?new=1" sidebar shortcut). The
// `/admin` route now mounts this inside a view toggle alongside the new
// Agile shell; behavior here must remain byte-for-byte identical to the
// pre-toggle implementation.
export function ClassicDashboardView() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("workspaces.create");

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [detailProject, setDetailProject] = useState<Project | null>(null);

  const searchParams = useSearchParams();
  const router = useRouter();

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Project[]>("/api/projects");
      setProjects(data);
    } catch {
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Auto-open create dialog from sidebar shortcut (?new=1). The toggle now
  // owns the `?view=` query param, so strip only `new` and preserve the
  // rest of the URL to avoid clobbering the active view.
  useEffect(() => {
    if (searchParams.get("new") === "1" && canManage) {
      setEditProject(null);
      setDialogOpen(true);
      const next = new URLSearchParams(searchParams.toString());
      next.delete("new");
      const query = next.toString();
      router.replace(query ? `/admin?${query}` : "/admin", { scroll: false });
    }
  }, [searchParams, canManage, router]);

  const handleCreate = () => {
    setEditProject(null);
    setDialogOpen(true);
  };

  const handleEdit = (project: Project) => {
    setEditProject(project);
    setDialogOpen(true);
  };

  if (detailProject) {
    return (
      <ProjectDetail
        project={detailProject}
        isAdmin={canManage}
        onBack={() => {
          setDetailProject(null);
          loadProjects();
        }}
      />
    );
  }

  return (
    <div data-testid="classic-dashboard-root">
      <PageHeader
        title="Tổng quan"
        description="Quản lý không gian nghiệp vụ và tương tác khách hàng — mỗi không gian có đội ngũ và tài liệu riêng."
        action={
          canManage ? (
            <Button
              onClick={handleCreate}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base mr-1">add</span>
              Tạo không gian
            </Button>
          ) : undefined
        }
      />

      <ProjectList
        projects={projects}
        loading={loading}
        isAdmin={canManage}
        onEdit={handleEdit}
        onOpen={setDetailProject}
        onRefresh={loadProjects}
      />

      {canManage && (
        <ProjectDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          project={editProject}
          onSaved={loadProjects}
        />
      )}
    </div>
  );
}
