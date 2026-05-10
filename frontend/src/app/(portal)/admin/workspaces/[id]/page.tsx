"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ProjectDetail } from "@/components/projects/project-detail";

type Project = {
  id: string;
  name: string;
  description?: string;
  workspace_type: string;
  status: string;
  member_count: number;
  source_count: number;
  created_at: string;
};

export default function WorkspaceDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const projectId = params.id as string;
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      // Fetch all projects then find by id (matches existing API pattern)
      const projects = await api<Project[]>("/api/projects");
      const found = projects.find((p) => p.id === projectId);
      if (found) {
        setProject(found);
      } else {
        setError(true);
      }
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-3xl text-primary animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <span className="material-symbols-outlined text-4xl text-muted-foreground">
          folder_off
        </span>
        <p className="text-sm text-muted-foreground">Workspace not found</p>
        <button
          onClick={() => router.push("/")}
          className="text-sm text-primary hover:underline"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <ProjectDetail
      project={project}
      isAdmin={isAdmin}
      onBack={() => router.push("/")}
    />
  );
}
