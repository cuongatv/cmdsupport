"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import { FEATURE_AGILE_PHASE_4 } from "@/lib/feature-flags";
import {
  getProjectTemplate,
  updateProjectTemplate,
} from "@/lib/task-api";
import type { TaskProjectTemplate } from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// Phase 4 (FEATURE_AGILE_PHASE_4) — Vietnamese DoR/DoD template management
// panel for a single TaskProject. Hidden entirely when the flag is OFF so
// legacy deployments stay untouched. Strings are hardcoded Vietnamese per
// the project decision to avoid pulling in an i18n framework.
//
// The editor authors each side as a multi-line textarea (one criterion per
// line). The PUT endpoint replaces the entire array on save; we send both
// sides on every save so the wire format matches user expectations
// ("Lưu mẫu" = save both panels at once).

type ProjectTemplatePanelProps = {
  projectId: string;
  /** Optional callback fired after a successful save. */
  onTemplateChanged?: (template: TaskProjectTemplate) => void;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

function isFlagOn(): boolean {
  return FEATURE_AGILE_PHASE_4;
}

// Newline-separated textarea ↔ `string[]`. Blank lines are stripped so the
// template never persists empty checklist items.
function linesToList(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function listToLines(items: string[]): string {
  return items.join("\n");
}

// Normalise the backend `list[Any]` payload into the Vietnamese-string list
// the UI authors. Items may be plain strings or `{label, ...}` objects (the
// task `dor_checklist`/`dod_checklist` snapshot uses the object shape); we
// extract a printable string for both so the template editor stays
// forward-compatible if the wire format ever widens.
function normalizeTemplateList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => {
      if (typeof entry === "string") return entry;
      if (entry && typeof entry === "object") {
        const obj = entry as Record<string, unknown>;
        if (typeof obj.label === "string") return obj.label;
        if (typeof obj.text === "string") return obj.text;
      }
      return "";
    })
    .filter((line) => line.length > 0);
}

export function ProjectTemplatePanel({
  projectId,
  onTemplateChanged,
}: ProjectTemplatePanelProps) {
  const [dorText, setDorText] = React.useState<string>("");
  const [dodText, setDodText] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string>("");
  const [info, setInfo] = React.useState<string>("");

  const refresh = React.useCallback(async () => {
    if (!isFlagOn()) return;
    setLoading(true);
    setError("");
    try {
      const template = await getProjectTemplate(projectId);
      setDorText(listToLines(normalizeTemplateList(template.dor_template)));
      setDodText(listToLines(normalizeTemplateList(template.dod_template)));
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được mẫu tiêu chí dự án"));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  React.useEffect(() => {
    // Defer to a microtask so we don't trip the
    // `react-hooks/set-state-in-effect` rule the project downgrades to warn.
    const timerId = window.setTimeout(() => {
      refresh();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [refresh]);

  if (!isFlagOn()) {
    // Phase 4 OFF — render nothing. Caller can still mount this component
    // unconditionally; the flag check lives here so the gate is co-located
    // with the feature.
    return null;
  }

  const handleSave = async () => {
    setError("");
    setInfo("");
    setSaving(true);
    try {
      const updated = await updateProjectTemplate(
        projectId,
        linesToList(dorText),
        linesToList(dodText),
      );
      setDorText(listToLines(normalizeTemplateList(updated.dor_template)));
      setDodText(listToLines(normalizeTemplateList(updated.dod_template)));
      setInfo("Đã lưu mẫu tiêu chí dự án");
      onTemplateChanged?.(updated);
    } catch (err) {
      setError(getErrorMessage(err, "Lưu mẫu tiêu chí dự án thất bại"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4"
      data-testid="project-template-panel"
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            Mẫu tiêu chí dự án
          </h2>
          <p className="text-xs text-muted-foreground">
            Mẫu Tiêu chí sẵn sàng (DoR) và Tiêu chí hoàn thành (DoD) áp dụng
            cho công việc mới trong dự án. Mỗi dòng là một tiêu chí.
          </p>
        </div>
      </header>

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          data-testid="project-template-panel-error"
        >
          {error}
        </div>
      )}

      {info && (
        <div
          className="rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary"
          role="status"
          data-testid="project-template-panel-info"
        >
          {info}
        </div>
      )}

      {loading ? (
        <div
          className="text-sm text-muted-foreground"
          data-testid="project-template-panel-loading"
        >
          Đang tải mẫu tiêu chí…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="project-template-dor-input">
              Tiêu chí sẵn sàng (DoR)
            </Label>
            <Textarea
              id="project-template-dor-input"
              data-testid="project-template-dor-input"
              value={dorText}
              onChange={(event) => setDorText(event.target.value)}
              placeholder={
                "Ví dụ:\nMô tả nghiệp vụ rõ ràng\nĐã thống nhất tiêu chí chấp nhận\nĐã ước lượng story points"
              }
              rows={8}
              className="bg-background font-mono text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              Mỗi dòng là một tiêu chí sẵn sàng. Dòng trống sẽ bị bỏ qua khi
              lưu.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="project-template-dod-input">
              Tiêu chí hoàn thành (DoD)
            </Label>
            <Textarea
              id="project-template-dod-input"
              data-testid="project-template-dod-input"
              value={dodText}
              onChange={(event) => setDodText(event.target.value)}
              placeholder={
                "Ví dụ:\nĐã có unit test phủ logic chính\nĐã code review và merge\nĐã cập nhật tài liệu nghiệp vụ"
              }
              rows={8}
              className="bg-background font-mono text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              Mỗi dòng là một tiêu chí hoàn thành. Dòng trống sẽ bị bỏ qua khi
              lưu.
            </p>
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button
          data-testid="project-template-save-btn"
          disabled={saving || loading}
          onClick={handleSave}
          className="bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {saving ? "Đang lưu…" : "Lưu mẫu"}
        </Button>
      </div>
    </section>
  );
}
