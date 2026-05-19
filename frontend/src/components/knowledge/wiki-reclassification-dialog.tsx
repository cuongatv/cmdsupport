"use client";

/**
 * T14 — Reclassification preview/apply UI.
 *
 * Thin HTTP layer around T11 routes:
 *   - POST /api/wiki/reclassify/preview  (dry-run, SELECT-only)
 *   - POST /api/wiki/reclassify/apply    (taxonomy-only writes via wiki_service)
 *
 * The dialog is intentionally read-then-confirm: "Áp dụng" is disabled until a
 * preview has been computed, and the rule-linked tier-change warning is
 * rendered above the table whenever any preview row carries that impact flag.
 */

import * as React from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { WikiTaxonomyBadge, WikiTypeBadge } from "@/components/wiki/wiki-type-badge";

// ---------------------------------------------------------------------------
// Response shapes — match app/routers/wiki_reclassify.py + service output.
// ---------------------------------------------------------------------------

type ReclassifyImpactFlag =
  | "low_confidence"
  | "to_other"
  | "business_to_supporting"
  | "rule_linked_tier_change"
  | string;

type PreviewPage = {
  wiki_page_id: string;
  slug: string;
  title: string;
  page_type: string;
  old_slugs: string[];
  new_slugs: string[];
  confidence: number;
  rationale: string;
  needs_review: boolean;
  classifier_version: string;
  rule_link_count: number;
  impact_flags: ReclassifyImpactFlag[];
};

type PreviewResponse = {
  preview_id: string;
  page_count: number;
  flagged_count: number;
  pages: PreviewPage[];
};

type ApplyResponse = {
  preview_id: string;
  applied_count: number;
  skipped_count: number;
  flagged_count: number;
  unchanged_count: number;
  applied_page_ids: string[];
  skipped_reasons: Record<string, string[]>;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

// Friendly Vietnamese label for impact_flags chips. Unknown flags fall back to
// the raw key so future server-side additions don't crash the UI.
const IMPACT_FLAG_LABELS: Record<string, string> = {
  low_confidence: "Độ tin cậy thấp",
  to_other: "Chuyển sang 'Khác'",
  business_to_supporting: "Hạ tầng nghiệp vụ → hỗ trợ",
  rule_linked_tier_change: "Đổi tầng — đang gắn quy tắc",
};

function flagLabel(flag: string): string {
  return IMPACT_FLAG_LABELS[flag] ?? flag;
}

export function WikiReclassificationDialog({ open, onOpenChange }: Props) {
  const [previewResult, setPreviewResult] = React.useState<PreviewResponse | null>(null);
  const [applyResult, setApplyResult] = React.useState<ApplyResponse | null>(null);
  const [loadingPreview, setLoadingPreview] = React.useState(false);
  const [loadingApply, setLoadingApply] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [forceRuleLinked, setForceRuleLinked] = React.useState(false);

  const handleRunPreview = async () => {
    setLoadingPreview(true);
    setError(null);
    setApplyResult(null);
    try {
      const data = await api<PreviewResponse>("/api/wiki/reclassify/preview", {
        method: "POST",
        body: { limit: 25 },
      });
      setPreviewResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không chạy được preview");
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleApply = async () => {
    if (!previewResult) return;
    setLoadingApply(true);
    setError(null);
    try {
      const data = await api<ApplyResponse>("/api/wiki/reclassify/apply", {
        method: "POST",
        body: {
          preview_id: previewResult.preview_id,
          force_rule_linked_tier_change: forceRuleLinked,
        },
      });
      setApplyResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Áp dụng thất bại");
    } finally {
      setLoadingApply(false);
    }
  };

  const hasRuleLinkedTierChange = React.useMemo(() => {
    if (!previewResult) return false;
    return previewResult.pages.some((page) =>
      page.impact_flags.includes("rule_linked_tier_change"),
    );
  }, [previewResult]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-heading">
            Phân loại lại Wiki
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          <p className="text-sm text-muted-foreground">
            Chạy dry-run để xem các trang Wiki sẽ được phân loại lại theo phân
            loại BIDV KHDN. Áp dụng chỉ thay đổi nhãn phân loại — nội dung trang
            không bị dịch hay viết lại.
          </p>

          {/* Action bar */}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              data-testid="run-reclassify-preview"
              onClick={handleRunPreview}
              disabled={loadingPreview || loadingApply}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span
                className={`material-symbols-outlined mr-1 ${loadingPreview ? "animate-spin" : ""}`}
                style={{ fontSize: 16 }}
              >
                {loadingPreview ? "progress_activity" : "preview"}
              </span>
              {loadingPreview ? "Đang chạy preview…" : "Chạy Preview"}
            </Button>

            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input
                data-testid="force-rule-linked-tier-change"
                type="checkbox"
                checked={forceRuleLinked}
                onChange={(e) => setForceRuleLinked(e.target.checked)}
                disabled={loadingApply}
                className="h-4 w-4 rounded border-border accent-primary"
              />
              Cho phép đổi tầng dù đang gắn quy tắc tư vấn
            </label>

            <Button
              data-testid="run-reclassify-apply"
              onClick={handleApply}
              disabled={!previewResult || loadingApply || loadingPreview}
              variant="outline"
            >
              <span
                className={`material-symbols-outlined mr-1 ${loadingApply ? "animate-spin" : ""}`}
                style={{ fontSize: 16 }}
              >
                {loadingApply ? "progress_activity" : "check"}
              </span>
              {loadingApply ? "Đang áp dụng…" : "Áp dụng"}
            </Button>
          </div>

          {/* Preview summary */}
          {previewResult && (
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-md border border-border bg-card px-3 py-2">
                <p className="text-muted-foreground">Tổng số trang</p>
                <p className="text-sm font-medium tabular-nums text-foreground">
                  {previewResult.page_count}
                </p>
              </div>
              <div className="rounded-md border border-border bg-card px-3 py-2">
                <p className="text-muted-foreground">Có cảnh báo</p>
                <p className="text-sm font-medium tabular-nums text-foreground">
                  {previewResult.flagged_count}
                </p>
              </div>
              <div className="rounded-md border border-border bg-card px-3 py-2">
                <p className="text-muted-foreground">Mã preview</p>
                <p className="font-mono text-[11px] text-foreground truncate">
                  {previewResult.preview_id}
                </p>
              </div>
            </div>
          )}

          {/* Rule-linked tier change warning */}
          {hasRuleLinkedTierChange && (
            <div
              data-testid="rule-linked-tier-change-warning"
              className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            >
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined text-lg mt-0.5">
                  warning
                </span>
                <div className="flex flex-col gap-1">
                  <p className="font-medium">
                    Cảnh báo: một số trang đang gắn quy tắc tư vấn sẽ đổi tầng
                    phân loại.
                  </p>
                  <p className="text-xs text-destructive/80">
                    Các thay đổi tầng (business → supporting hoặc → other) trên
                    trang có rule link sẽ bị bỏ qua khi áp dụng, trừ khi bạn
                    bật &ldquo;Cho phép đổi tầng dù đang gắn quy tắc tư vấn&rdquo;.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Apply result summary */}
          {applyResult && (
            <div className="rounded-lg border border-primary/40 bg-primary/5 px-4 py-3 text-sm">
              <p className="font-medium text-foreground">
                Đã áp dụng {applyResult.applied_count} | Bỏ qua{" "}
                {applyResult.skipped_count} | Cần review{" "}
                {applyResult.flagged_count}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Không thay đổi: {applyResult.unchanged_count}. Áp dụng cho{" "}
                {applyResult.applied_page_ids.length} ID trang.
              </p>
            </div>
          )}

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md flex items-center gap-2">
              <span className="material-symbols-outlined text-base">error</span>
              {error}
            </div>
          )}

          {/* Preview rows */}
          {previewResult && previewResult.pages.length === 0 && (
            <p className="text-sm text-muted-foreground italic">
              Không có trang nào trong phạm vi preview.
            </p>
          )}

          {previewResult && previewResult.pages.length > 0 && (
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left font-semibold px-3 py-2">Trang</th>
                    <th className="text-left font-semibold px-3 py-2">Loại</th>
                    <th className="text-left font-semibold px-3 py-2">
                      Phân loại cũ
                    </th>
                    <th className="text-left font-semibold px-3 py-2">
                      Phân loại mới
                    </th>
                    <th className="text-left font-semibold px-3 py-2">
                      Độ tin cậy
                    </th>
                    <th className="text-left font-semibold px-3 py-2">Lý do</th>
                    <th className="text-left font-semibold px-3 py-2">Cờ</th>
                  </tr>
                </thead>
                <tbody>
                  {previewResult.pages.map((page) => (
                    <tr
                      key={page.wiki_page_id}
                      data-testid={`reclassify-preview-row-${page.slug}`}
                      className="border-t border-border align-top"
                    >
                      <td className="px-3 py-2">
                        <div className="flex flex-col">
                          <span className="font-medium text-foreground">
                            {page.title}
                          </span>
                          <span className="text-[11px] text-muted-foreground font-mono">
                            {page.slug}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <WikiTypeBadge type={page.page_type} />
                      </td>
                      <td className="px-3 py-2">
                        {page.old_slugs.length === 0 ? (
                          <span className="text-xs text-muted-foreground/60">
                            —
                          </span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {page.old_slugs.map((slug) => (
                              <WikiTaxonomyBadge
                                key={`old-${page.wiki_page_id}-${slug}`}
                                slug={slug}
                              />
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {page.new_slugs.length === 0 ? (
                          <span className="text-xs text-muted-foreground/60">
                            —
                          </span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {page.new_slugs.map((slug) => (
                              <WikiTaxonomyBadge
                                key={`new-${page.wiki_page_id}-${slug}`}
                                slug={slug}
                              />
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs tabular-nums text-foreground">
                          {(page.confidence * 100).toFixed(0)}%
                        </span>
                        {page.needs_review && (
                          <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/15 text-amber-700 dark:text-amber-300">
                            Cần review
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 max-w-[260px]">
                        <p className="text-xs text-muted-foreground line-clamp-3 whitespace-pre-wrap">
                          {page.rationale || "—"}
                        </p>
                        {page.rule_link_count > 0 && (
                          <p className="text-[10px] text-muted-foreground/80 mt-1">
                            Rule link: {page.rule_link_count}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {page.impact_flags.length === 0 ? (
                          <span className="text-xs text-muted-foreground/60">
                            —
                          </span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {page.impact_flags.map((flag) => (
                              <span
                                key={`${page.wiki_page_id}-${flag}`}
                                className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                                  flag === "rule_linked_tier_change"
                                    ? "bg-destructive/10 text-destructive border-destructive/40"
                                    : "bg-secondary text-secondary-foreground border-border"
                                }`}
                              >
                                {flagLabel(flag)}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex justify-end">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loadingApply || loadingPreview}
            >
              Đóng
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
