"use client";

import { Badge } from "@/components/ui/badge";
import { CitationList } from "./citation-list";

type Recommendation = {
  product_name: string;
  fit_reason: string;
  sales_angle: string;
  required_documents: string[];
  caveats: string[];
  citations: { wiki_slug: string; title: string; source_ids: string[] }[];
  confidence: "low" | "medium" | "high";
};

const confidenceMap: Record<string, { label: string; variant: "secondary" | "outline" | "default" }> = {
  low: { label: "Tin cậy thấp", variant: "secondary" },
  medium: { label: "Tin cậy trung bình", variant: "outline" },
  high: { label: "Tin cậy cao", variant: "default" },
};

type Props = {
  recommendation: Recommendation;
};

export function RecommendationCard({ recommendation: r }: Props) {
  const conf = confidenceMap[r.confidence] ?? confidenceMap.medium;

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-heading text-base font-medium text-foreground">{r.product_name}</h3>
        <Badge variant={conf.variant} className="shrink-0">{conf.label}</Badge>
      </div>

      {/* Fit reason */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1">Lý do phù hợp</p>
        <p className="text-sm text-foreground">{r.fit_reason}</p>
      </div>

      {/* Sales angle */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1">Góc tiếp cận bán hàng</p>
        <p className="text-sm text-foreground">{r.sales_angle}</p>
      </div>

      {/* Required documents */}
      {r.required_documents && r.required_documents.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Hồ sơ yêu cầu</p>
          <ul className="space-y-1">
            {r.required_documents.map((doc, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                <span className="material-symbols-outlined text-sm text-primary mt-0.5">check_circle</span>
                {doc}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Caveats */}
      {r.caveats && r.caveats.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {r.caveats.map((c, i) => (
            <Badge key={i} variant="destructive" className="text-xs">{c}</Badge>
          ))}
        </div>
      )}

      {/* Citations */}
      <CitationList citations={r.citations} />
    </div>
  );
}
