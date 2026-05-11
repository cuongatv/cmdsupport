"use client";

import Link from "next/link";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

type AdviceLanguage = "vi" | "en";

type ResultJson = {
  advice_language?: AdviceLanguage;
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

/* ═══════════════════════════════════════════════════════════
   W1-T3: v2 advisory memo schema (rendering wired up in W3-T11)
   ═══════════════════════════════════════════════════════════ */
export type CrossSellProduct = {
  product_name: string;
  fit_reason: string;
  citations: { wiki_slug: string; title: string }[];
  /** Optional — populated by v2 prompt for primary_products (mirrors v1 recommendations.confidence). */
  confidence?: "low" | "medium" | "high";
};

export type PolicyIncentive = {
  title: string;
  description: string;
  citations: { wiki_slug: string; title: string }[];
};

export type ResultJsonV2 = ResultJson & {
  schema_version?: string;
  executive_thesis?: string;
  primary_products?: CrossSellProduct[];
  cross_sell_products?: CrossSellProduct[];
  upsell_products?: CrossSellProduct[];
  operations_products?: CrossSellProduct[];
  digital_channels?: CrossSellProduct[];
  policies_incentives?: PolicyIncentive[];
  bundle_advantages?: string;
};

/** Legacy fallback detection — true only when backend stamped schema_version="v2.0". */
export const isV2 = (r: ResultJson | ResultJsonV2): r is ResultJsonV2 =>
  (r as ResultJsonV2).schema_version === "v2.0";

// v2 data-testids (implemented in W3-T11):
// data-testid="advisory-memo-cover"
// data-testid="advisory-thesis"
// data-testid="advisory-primary-products"
// data-testid="advisory-cross-sell"
// data-testid="advisory-operations"
// data-testid="advisory-digital"
// data-testid="advisory-policies"
// data-testid="advisory-bundle"
// data-testid="advisory-citations"
// data-testid="advisory-gaps"
// data-testid="advisory-disclaimer"
// data-testid="advisory-reuse-badge"

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
  result_json: ResultJson | ResultJsonV2 | null;
  prompt_version: string;
  model_provider: string;
  model_id: string;
  duration_ms: number;
  retrieved_wiki_page_slugs: string[] | null;
  created_at: string;
  created_by_name: string;
  schema_version?: string;
  reuse_status?: string;
};

type Props = {
  result: AdviceDetail | null;
  loading: boolean;
  error: string | null;
};

function confidenceLabel(value: string, language: "vi" | "en" = "vi"): string {
  if (language === "en") {
    switch (value) {
      case "low":
        return "Low confidence";
      case "medium":
        return "Medium confidence";
      case "high":
        return "High confidence";
      default:
        return value;
    }
  }

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

const RESULT_LABELS = {
  vi: {
    error: "Lỗi",
    failed: "Phân tích thất bại",
    noData: "Không có dữ liệu kết quả.",
    overview: "Tổng quan",
    products: "Sản phẩm đề xuất",
    materials: "Tài liệu chào hàng",
    questions: "Câu hỏi tiếp theo",
    gaps: "Khoảng trống",
    analysis: "Phân tích",
    detectedNeeds: "Nhu cầu phát hiện",
    salesAngle: "Góc bán hàng",
    requiredDocuments: "Hồ sơ cần thiết",
    caveats: "Lưu ý",
    sources: "Nguồn",
    noProducts: "Chưa có sản phẩm nào được đề xuất.",
    noMaterials: "Không có tài liệu chào hàng.",
    noQuestions: "Không có câu hỏi tiếp theo.",
    gapsHint: "Các khoảng trống thông tin dưới đây cần được bổ sung để tư vấn chính xác hơn.",
    noGaps: "Không có khoảng trống thông tin.",
    prompt: "Prompt",
    model: "Model",
    duration: "Thời gian",
    // v2 memo sections (W3-T14)
    customerCover: "Tư vấn KHDN",
    executiveSummary: "Luận điểm tư vấn",
    primaryProducts: "Sản phẩm trọng tâm",
    crossSell: "Bán chéo",
    upsell: "Nâng cấp",
    operations: "Vận hành",
    digitalChannels: "Kênh số",
    policiesIncentives: "Chính sách & Ưu đãi",
    bundleAdvantages: "Lợi ích đóng gói",
    fitReason: "Lý do phù hợp",
    // reuse status badges
    reuseStatusCached: "Kết quả đã lưu",
    reuseStatusRefreshed: "Nguồn mới, kết quả mới",
    reuseStatusNew: "Mới",
  },
  en: {
    error: "Error",
    failed: "Analysis failed",
    noData: "No advisory result data is available.",
    overview: "Overview",
    products: "Recommended products",
    materials: "Sales materials",
    questions: "Follow-up questions",
    gaps: "Coverage gaps",
    analysis: "Analysis",
    detectedNeeds: "Detected needs",
    salesAngle: "Sales angle",
    requiredDocuments: "Required documents",
    caveats: "Caveats",
    sources: "Sources",
    noProducts: "No products were recommended.",
    noMaterials: "No sales materials.",
    noQuestions: "No follow-up questions.",
    gapsHint: "The information gaps below should be addressed to improve advisory accuracy.",
    noGaps: "No coverage gaps.",
    prompt: "Prompt",
    model: "Model",
    duration: "Duration",
    // v2 memo sections (W3-T14)
    customerCover: "Advisory Memo",
    executiveSummary: "Advisory Thesis",
    primaryProducts: "Primary Products",
    crossSell: "Cross-sell",
    upsell: "Upsell",
    operations: "Operations",
    digitalChannels: "Digital Channels",
    policiesIncentives: "Policies & Incentives",
    bundleAdvantages: "Bundle Advantages",
    fitReason: "Why it fits",
    // reuse status badges
    reuseStatusCached: "Cached result",
    reuseStatusRefreshed: "Refreshed",
    reuseStatusNew: "New",
  },
} as const;

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
   v2 memo helpers (W3-T11)
   ═══════════════════════════════════════════════════════════ */

function CitationChips({
  citations,
  label,
}: {
  citations: { wiki_slug: string; title: string }[];
  label: string;
}) {
  if (!citations || citations.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground mt-2">{label}</p>
      <div className="flex flex-wrap gap-1.5 mt-1">
        {citations.map((c, j) => (
          <a
            key={j}
            href={`/admin/wiki/${c.wiki_slug}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs text-secondary-foreground hover:underline"
          >
            <span className="material-symbols-outlined text-xs">link</span>
            {c.title || c.wiki_slug}
          </a>
        ))}
      </div>
    </div>
  );
}

function CompactProductCard({
  product,
  fitReasonLabel,
  sourcesLabel,
  language,
}: {
  product: CrossSellProduct;
  fitReasonLabel: string;
  sourcesLabel: string;
  language: AdviceLanguage;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-heading text-sm font-medium">{product.product_name}</h4>
        {product.confidence && (
          <Badge variant="secondary">{confidenceLabel(product.confidence, language)}</Badge>
        )}
      </div>
      {product.fit_reason && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">{fitReasonLabel}</p>
          <p className="text-sm text-foreground">{product.fit_reason}</p>
        </div>
      )}
      <CitationChips citations={product.citations || []} label={sourcesLabel} />
    </div>
  );
}

function ReuseBadge({
  status,
  labels,
}: {
  status: string | undefined;
  labels: (typeof RESULT_LABELS)[AdviceLanguage];
}) {
  if (!status) return null;
  const config: Record<string, { className: string; icon: string; text: string }> = {
    reused: {
      className: "bg-emerald-100 text-emerald-800",
      icon: "cached",
      text: labels.reuseStatusCached,
    },
    refreshed: {
      className: "bg-amber-100 text-amber-800",
      icon: "autorenew",
      text: labels.reuseStatusRefreshed,
    },
    new: {
      className: "bg-white/15 text-white",
      icon: "fiber_new",
      text: labels.reuseStatusNew,
    },
  };
  const cfg = config[status];
  if (!cfg) return null;
  return (
    <span
      data-testid="advisory-reuse-badge"
      className={`inline-flex items-center gap-1 rounded-full text-xs font-medium px-2.5 py-1 ${cfg.className}`}
    >
      <span className="material-symbols-outlined text-sm">{cfg.icon}</span>
      {cfg.text}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════
   Main component
   ═══════════════════════════════════════════════════════════ */
export function AdvisoryResult({ result, loading, error }: Props) {
  const language = result?.result_json?.advice_language === "en" ? "en" : "vi";
  const labels = RESULT_LABELS[language];

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
            <p className="text-sm font-medium text-destructive">{labels.error}</p>
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
              <p className="text-sm font-medium text-destructive">{labels.failed}</p>
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
        <ResultFooter result={result} labels={labels} />
      </div>
    );
  }

  const r = result.result_json;
  if (!r) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <p className="text-sm text-muted-foreground">{labels.noData}</p>
      </div>
    );
  }

  /* v2 memo renderer (W3-T11) — only when backend stamps schema_version="v2.0". */
  if (isV2(r)) {
    const formattedDate = new Date(result.created_at).toLocaleDateString(
      language === "en" ? "en-US" : "vi-VN",
      { day: "numeric", month: "long", year: "numeric" },
    );

    return (
      <div className="space-y-4">
        {/* Cover band — BIDV teal. Inline style required: Tailwind purges arbitrary hex
            values when the project relies on CSS-driven theme tokens. */}
        <div
          data-testid="advisory-memo-cover"
          className="rounded-xl p-6 text-white shadow-sm"
          style={{ backgroundColor: "#2D8380" }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1 min-w-0">
              <p className="text-[11px] uppercase tracking-[0.18em] font-medium text-white/70">
                {labels.customerCover}
              </p>
              <h2 className="font-heading text-2xl font-bold leading-tight">
                {result.customer_name}
              </h2>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-white/85">
                {result.customer_segment && (
                  <>
                    <span>{result.customer_segment}</span>
                    <span aria-hidden className="text-white/40">·</span>
                  </>
                )}
                <span>{formattedDate}</span>
              </div>
            </div>
            <ReuseBadge status={result.reuse_status} labels={labels} />
          </div>
        </div>

        {/* Executive thesis */}
        {r.executive_thesis && (
          <blockquote
            data-testid="advisory-thesis"
            className="rounded-xl border-l-4 border-primary bg-primary/10 p-5"
          >
            <p className="font-heading text-base italic leading-relaxed text-foreground">
              {r.executive_thesis}
            </p>
          </blockquote>
        )}

        {/* Primary products */}
        {r.primary_products && r.primary_products.length > 0 && (
          <section data-testid="advisory-primary-products" className="space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.primaryProducts}</h3>
            <div className="space-y-3">
              {r.primary_products.map((p, i) => (
                <CompactProductCard
                  key={i}
                  product={p}
                  fitReasonLabel={labels.fitReason}
                  sourcesLabel={labels.sources}
                  language={language}
                />
              ))}
            </div>
          </section>
        )}

        {/* Cross-sell */}
        {r.cross_sell_products && r.cross_sell_products.length > 0 && (
          <section data-testid="advisory-cross-sell" className="space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.crossSell}</h3>
            <div className="space-y-3">
              {r.cross_sell_products.map((p, i) => (
                <CompactProductCard
                  key={i}
                  product={p}
                  fitReasonLabel={labels.fitReason}
                  sourcesLabel={labels.sources}
                  language={language}
                />
              ))}
            </div>
          </section>
        )}

        {/* Upsell */}
        {r.upsell_products && r.upsell_products.length > 0 && (
          <section className="space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.upsell}</h3>
            <div className="space-y-3">
              {r.upsell_products.map((p, i) => (
                <CompactProductCard
                  key={i}
                  product={p}
                  fitReasonLabel={labels.fitReason}
                  sourcesLabel={labels.sources}
                  language={language}
                />
              ))}
            </div>
          </section>
        )}

        {/* Operations */}
        {r.operations_products && r.operations_products.length > 0 && (
          <section data-testid="advisory-operations" className="space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.operations}</h3>
            <div className="space-y-3">
              {r.operations_products.map((p, i) => (
                <CompactProductCard
                  key={i}
                  product={p}
                  fitReasonLabel={labels.fitReason}
                  sourcesLabel={labels.sources}
                  language={language}
                />
              ))}
            </div>
          </section>
        )}

        {/* Digital channels */}
        {r.digital_channels && r.digital_channels.length > 0 && (
          <section data-testid="advisory-digital" className="space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.digitalChannels}</h3>
            <div className="space-y-3">
              {r.digital_channels.map((p, i) => (
                <CompactProductCard
                  key={i}
                  product={p}
                  fitReasonLabel={labels.fitReason}
                  sourcesLabel={labels.sources}
                  language={language}
                />
              ))}
            </div>
          </section>
        )}

        {/* Policies & incentives */}
        {r.policies_incentives && r.policies_incentives.length > 0 && (
          <section data-testid="advisory-policies" className="space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.policiesIncentives}</h3>
            <div className="space-y-3">
              {r.policies_incentives.map((p, i) => (
                <div key={i} className="rounded-xl border border-border bg-card p-4 space-y-2">
                  <h4 className="font-heading text-sm font-medium">{p.title}</h4>
                  {p.description && (
                    <p className="text-sm text-foreground whitespace-pre-line">{p.description}</p>
                  )}
                  <CitationChips citations={p.citations || []} label={labels.sources} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Bundle advantages */}
        {r.bundle_advantages && (
          <section
            data-testid="advisory-bundle"
            className="rounded-xl border border-primary/20 bg-primary/5 p-5 flex items-start gap-3"
          >
            <span className="material-symbols-outlined text-primary text-xl mt-0.5">
              workspace_premium
            </span>
            <div className="space-y-1 min-w-0">
              <h3 className="font-heading text-sm font-medium text-foreground">
                {labels.bundleAdvantages}
              </h3>
              <p className="text-sm text-foreground whitespace-pre-line">{r.bundle_advantages}</p>
            </div>
          </section>
        )}

        {/* Coverage gaps */}
        {r.coverage_gaps && r.coverage_gaps.length > 0 && (
          <section data-testid="advisory-gaps" className="space-y-3">
            <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3 flex items-start gap-2">
              <span className="material-symbols-outlined text-blue-600 text-lg mt-0.5">info</span>
              <p className="text-xs text-blue-800">{labels.gapsHint}</p>
            </div>
            <ul className="space-y-2">
              {r.coverage_gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                  <span className="material-symbols-outlined text-sm text-amber-500 mt-0.5">
                    report_problem
                  </span>
                  {g}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* RM disclaimer */}
        {r.rm_disclaimer && (
          <div
            data-testid="advisory-disclaimer"
            className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 flex items-start gap-2"
          >
            <span className="material-symbols-outlined text-amber-600 text-lg mt-0.5">gavel</span>
            <p className="text-xs text-amber-800">{r.rm_disclaimer}</p>
          </div>
        )}

        <ResultFooter result={result} labels={labels} />
      </div>
    );
  }

  /* v1 / legacy fallback — original Tabs layout, untouched. */
  return (
    <div className="space-y-4">
      <Tabs defaultValue="overview">
        <TabsList variant="line" className="w-full overflow-x-auto flex-nowrap">
          <TabsTrigger value="overview">{labels.overview}</TabsTrigger>
          <TabsTrigger value="products">{labels.products}</TabsTrigger>
          <TabsTrigger value="materials">{labels.materials}</TabsTrigger>
          <TabsTrigger value="questions">{labels.questions}</TabsTrigger>
          <TabsTrigger value="gaps">{labels.gaps}</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <h3 className="font-heading text-base font-medium">{labels.analysis}</h3>
            <p className="text-sm text-foreground whitespace-pre-line">{r.analysis}</p>
          </div>
          {r.customer_context?.detected_needs && r.customer_context.detected_needs.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-4 space-y-2">
              <h3 className="font-heading text-sm font-medium text-muted-foreground">{labels.detectedNeeds}</h3>
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
                  <Badge variant="secondary">{confidenceLabel(rec.confidence, language)}</Badge>
                </div>
                <p className="text-sm text-foreground">{rec.fit_reason}</p>
                {rec.sales_angle && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">{labels.salesAngle}</p>
                    <p className="text-sm text-foreground">{rec.sales_angle}</p>
                  </div>
                )}
                {rec.required_documents && rec.required_documents.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">{labels.requiredDocuments}</p>
                    <ul className="list-disc list-inside text-sm text-foreground">
                      {rec.required_documents.map((d, j) => <li key={j}>{d}</li>)}
                    </ul>
                  </div>
                )}
                {rec.caveats && rec.caveats.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">{labels.caveats}</p>
                    <ul className="list-disc list-inside text-sm text-foreground">
                      {rec.caveats.map((c, j) => <li key={j}>{c}</li>)}
                    </ul>
                  </div>
                )}
                {rec.citations && rec.citations.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mt-2">{labels.sources}</p>
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
            <p className="text-sm text-muted-foreground">{labels.noProducts}</p>
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
            <p className="text-sm text-muted-foreground py-4">{labels.noMaterials}</p>
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
            <p className="text-sm text-muted-foreground py-4">{labels.noQuestions}</p>
          )}
        </TabsContent>

        {/* Coverage gaps */}
        <TabsContent value="gaps" className="mt-4 space-y-3">
          {r.coverage_gaps && r.coverage_gaps.length > 0 ? (
            <>
              <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3 flex items-start gap-2">
                <span className="material-symbols-outlined text-blue-600 text-lg mt-0.5">info</span>
                <p className="text-xs text-blue-800">{labels.gapsHint}</p>
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
            <p className="text-sm text-muted-foreground py-4">{labels.noGaps}</p>
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

      <ResultFooter result={result} labels={labels} />
    </div>
  );
}

function ResultFooter({
  result,
  labels,
}: {
  result: AdviceDetail;
  labels: (typeof RESULT_LABELS)[AdviceLanguage];
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground pt-2 border-t border-border">
      <span>{labels.prompt}: {result.prompt_version}</span>
      <span>{labels.model}: {result.model_provider}/{result.model_id}</span>
      <span>{labels.duration}: {(result.duration_ms / 1000).toFixed(1)}s</span>
    </div>
  );
}
