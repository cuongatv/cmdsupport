"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { ProjectList } from "@/components/projects/project-list";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { ProjectDetail } from "@/components/projects/project-detail";

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

export default function WorkspacesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [detailProject, setDetailProject] = useState<Project | null>(null);

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
        isAdmin={isAdmin}
        onBack={() => { setDetailProject(null); loadProjects(); }}
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Không gian nghiệp vụ"
        description="Quản lý không gian nghiệp vụ và tương tác khách hàng — mỗi không gian có đội ngũ và tài liệu riêng."
        action={
          isAdmin ? (
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
        isAdmin={isAdmin}
        onEdit={handleEdit}
        onOpen={setDetailProject}
        onRefresh={loadProjects}
      />

      {isAdmin && (
        <ProjectDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          project={editProject}
          onSaved={loadProjects}
        />
      )}
    </>
  );
}
