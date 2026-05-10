"use client";

import Link from "next/link";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

type ResultJson = {
  customer_context: {
    name: string;
    province: string;
    industry: string;
    detected_needs: string[];
  };
  analysis: string;
  recommendations: {
    product_name: string;
    fit_reason: string;
    sales_angle: string;
    required_documents: string[];
    caveats: string[];
    citations: { wiki_slug: string; title: string; source_ids: string[] }[];
    confidence: "low" | "medium" | "high";
  }[];
  offer_materials: { title: string; wiki_slug: string; reason: string }[];
  follow_up_questions: string[];
  coverage_gaps: string[];
  rm_disclaimer: string;
};

export type AdviceDetail = {
  id: string;
  customer_name: string;
  province_name: string | null;
  industry_name: string | null;
  customer_segment: string | null;
  needs: string;
  additional_context: string | null;
  status: string;
  error_message: string | null;
  result_json: ResultJson | null;
  prompt_version: string;
  model_provider: string;
  model_id: string;
  duration_ms: number;
  retrieved_wiki_page_slugs: string[] | null;
  created_at: string;
  created_by_name: string;
};

type Props = {
  result: AdviceDetail | null;
  loading: boolean;
  error: string | null;
};

function confidenceLabel(value: string): string {
  switch (value) {
    case "low":
      return "Tin cậy thấp";
    case "medium":
      return "Tin cậy TB";
    case "high":
      return "Tin cậy cao";
    default:
      return value;
  }
}

function SkeletonCard() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-6 bg-muted rounded w-2/3" />
      <div className="h-4 bg-muted rounded w-full" />
      <div className="h-4 bg-muted rounded w-5/6" />
      <div className="h-32 bg-muted rounded w-full" />
      <div className="h-4 bg-muted rounded w-3/4" />
      <div className="h-4 bg-muted rounded w-1/2" />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Main component
   ═══════════════════════════════════════════════════════════ */
export function AdvisoryResult({ result, loading, error }: Props) {
  /* Loading → skeleton */
  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <SkeletonCard />
      </div>
    );
  }

  /* Error state */
  if (error) {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
        <div className="flex items-start gap-2">
          <span className="material-symbols-outlined text-destructive text-lg mt-0.5">error</span>
          <div>
            <p className="text-sm font-medium text-destructive">Lỗi</p>
            <p className="text-sm text-destructive/80 mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  /* Empty state */
  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
        <span className="material-symbols-outlined text-5xl text-muted-foreground/30 mb-4">smart_toy</span>
        <p className="text-sm text-muted-foreground max-w-xs">
          Hãy điền thông tin KHDN bên trái rồi bấm &ldquo;Phân tích bằng AI&rdquo; để nhận kết quả tư vấn.
        </p>
      </div>
    );
  }

  /* Failed status */
  if (result.status === "failed") {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-destructive text-lg mt-0.5">warning</span>
            <div>
              <p className="text-sm font-medium text-destructive">Phân tích thất bại</p>
              {result.error_message && (
                <p className="text-sm text-destructive/80 mt-1">{result.error_message}</p>
              )}
            </div>
          </div>
        </div>
        {result.result_json && (
          <pre className="rounded-lg bg-muted p-4 text-xs overflow-x-auto">
            {JSON.stringify(result.result_json, null, 2)}
          </pre>
        )}
        <ResultFooter result={result} />
      </div>
    );
  }

  const r = result.result_json;
  if (!r) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <p className="text-sm text-muted-foreground">Không có dữ liệu kết quả.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Tabs defaultValue="overview">
        <TabsList variant="line" className="w-full overflow-x-auto flex-nowrap">
          <TabsTrigger value="overview">Tổng quan</TabsTrigger>
          <TabsTrigger value="products">Sản phẩm đề xuất</TabsTrigger>
          <TabsTrigger value="materials">Tài liệu chào hàng</TabsTrigger>
          <TabsTrigger value="questions">Câu hỏi tiếp theo</TabsTrigger>
          <TabsTrigger value="gaps">Khoảng trống</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <h3 className="font-heading text-base font-medium">Phân tích</h3>
            <p className="text-sm text-foreground whitespace-pre-line">{r.analysis}</p>
          </div>
          {r.customer_context?.detected_needs && r.customer_context.detected_needs.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-4 space-y-2">
              <h3 className="font-heading text-sm font-medium text-muted-foreground">Nhu cầu phát hiện</h3>
              <div className="flex flex-wrap gap-1.5">
                {r.customer_context.detected_needs.map((need, i) => (
                  <Badge key={i} variant="secondary">{need}</Badge>
                ))}
              </div>
            </div>
          )}
        </TabsContent>

        {/* Products — list style */}
        <TabsContent value="products" className="mt-4 space-y-3">
          {r.recommendations && r.recommendations.length > 0 ? (
            r.recommendations.map((rec, i) => (
              <div key={i} className="rounded-xl border border-border bg-card p-4 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h4 className="font-heading text-base font-medium">{rec.product_name}</h4>
                  <Badge variant="secondary">{confidenceLabel(rec.confidence)}</Badge>
                </div>
                <p className="text-sm text-foreground">{rec.fit_reason}</p>
                {rec.sales_angle && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">Góc bán hàng</p>
                    <p className="text-sm text-foreground">{rec.sales_angle}</p>
                  </div>
                )}
                {rec.required_documents && rec.required_documents.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">Hồ sơ cần thiết</p>
                    <ul className="list-disc list-inside text-sm text-foreground">
                      {rec.required_documents.map((d, j) => <li key={j}>{d}</li>)}
                    </ul>
                  </div>
                )}
                {rec.caveats && rec.caveats.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">Lưu ý</p>
                    <ul className="list-disc list-inside text-sm text-foreground">
                      {rec.caveats.map((c, j) => <li key={j}>{c}</li>)}
                    </ul>
                  </div>
                )}
                {rec.citations && rec.citations.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">Nguồn</p>
                    <div className="flex flex-wrap gap-1.5">
                      {rec.citations.map((c, j) => (
                        <a key={j} href={`/admin/wiki/${c.wiki_slug}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs text-secondary-foreground hover:underline">
                          <span className="material-symbols-outlined text-xs">link</span>
                          {c.title || c.wiki_slug}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">Chưa có sản phẩm nào được đề xuất.</p>
          )}
        </TabsContent>

        {/* Materials */}
        <TabsContent value="materials" className="mt-4 space-y-3">
          {r.offer_materials && r.offer_materials.length > 0 ? (
            r.offer_materials.map((m, i) => (
              <div key={i} className="rounded-xl border border-border bg-card p-4 space-y-2">
                <div className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-primary text-lg">description</span>
                  <div className="min-w-0">
                    <Link
                      href={`/admin/wiki/${m.wiki_slug}`}
                      className="font-heading text-sm font-medium text-primary hover:underline"
                    >
                      {m.title}
                    </Link>
                    <p className="text-xs text-muted-foreground mt-1">{m.reason}</p>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground py-4">Không có tài liệu chào hàng.</p>
          )}
        </TabsContent>

        {/* Follow-up questions */}
        <TabsContent value="questions" className="mt-4">
          {r.follow_up_questions && r.follow_up_questions.length > 0 ? (
            <ul className="space-y-2">
              {r.follow_up_questions.map((q, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                  <span className="material-symbols-outlined text-sm text-muted-foreground mt-0.5">help_outline</span>
                  {q}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground py-4">Không có câu hỏi tiếp theo.</p>
          )}
        </TabsContent>

        {/* Coverage gaps */}
        <TabsContent value="gaps" className="mt-4 space-y-3">
          {r.coverage_gaps && r.coverage_gaps.length > 0 ? (
            <>
              <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3 flex items-start gap-2">
                <span className="material-symbols-outlined text-blue-600 text-lg mt-0.5">info</span>
                <p className="text-xs text-blue-800">Các khoảng trống thông tin dưới đây cần được bổ sung để tư vấn chính xác hơn.</p>
              </div>
              <ul className="space-y-2">
                {r.coverage_gaps.map((g, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                    <span className="material-symbols-outlined text-sm text-amber-500 mt-0.5">report_problem</span>
                    {g}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-muted-foreground py-4">Không có khoảng trống thông tin.</p>
          )}
        </TabsContent>
      </Tabs>

      {/* RM Disclaimer */}
      {r.rm_disclaimer && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 flex items-start gap-2">
          <span className="material-symbols-outlined text-amber-600 text-lg mt-0.5">gavel</span>
          <p className="text-xs text-amber-800">{r.rm_disclaimer}</p>
        </div>
      )}

      <ResultFooter result={result} />
    </div>
  );
}

function ResultFooter({ result }: { result: AdviceDetail }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground pt-2 border-t border-border">
      <span>Prompt: {result.prompt_version}</span>
      <span>Model: {result.model_provider}/{result.model_id}</span>
      <span>Thời gian: {(result.duration_ms / 1000).toFixed(1)}s</span>
    </div>
  );
}
