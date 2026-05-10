"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type HealthStatus = "healthy" | "error" | "loading";

type Health = {
  api: HealthStatus;
  database: HealthStatus;
  worker: HealthStatus;
};

export function SystemHealthCard() {
  const [health, setHealth] = useState<Health>({
    api: "loading",
    database: "loading",
    worker: "loading",
  });

  useEffect(() => {
    api<{ api: string; database: string; worker: string }>("/api/health")
      .then((data) => {
        setHealth({
          api: data.api === "healthy" ? "healthy" : "error",
          database: data.database === "healthy" ? "healthy" : "error",
          worker: data.worker === "healthy" ? "healthy" : "error",
        });
      })
      .catch(() => {
        setHealth({ api: "error", database: "error", worker: "error" });
      });
  }, []);

  const allHealthy = health.api === "healthy" && health.database === "healthy" && health.worker === "healthy";

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex justify-between items-center border-b border-border pb-3 mb-4">
        <h3 className="text-xl tracking-tight text-foreground">Tình trạng hệ thống</h3>
        <span className={`text-xs font-medium flex items-center gap-1 ${allHealthy ? "text-primary" : "text-destructive"}`}>
          <span className="material-symbols-outlined text-sm">
            {allHealthy ? "check_circle" : "warning"}
          </span>
          {allHealthy ? "MCP Server trực tuyến" : "Có sự cố"}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <HealthItem label="API" status={health.api} />
        <HealthItem label="Cơ sở dữ liệu" status={health.database} />
        <HealthItem label="Worker" status={health.worker} />
      </div>
    </div>
  );
}

function HealthItem({ label, status }: { label: string; status: HealthStatus }) {
  const colors = {
    healthy: "text-green-600 bg-green-50",
    error: "text-destructive bg-destructive/10",
    loading: "text-muted-foreground bg-secondary",
  };

  const icon = {
    healthy: "check_circle",
    error: "error",
    loading: "progress_activity",
  };

  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${colors[status]}`}>
      <span className={`material-symbols-outlined text-sm ${status === "loading" ? "animate-spin" : "filled"}`}>
        {icon[status]}
      </span>
      <span className="text-xs font-medium">{label}</span>
    </div>
  );
}
