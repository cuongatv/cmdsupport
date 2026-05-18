"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { AdvisoryResult, type AdviceDetail } from "@/components/cmd-support/advisory-result";
import { SEGMENT_SHORT_LABEL } from "@/components/cmd-support/segment-select";

export default function CmdAdvisoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [detail, setDetail] = useState<AdviceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api<AdviceDetail>(`/api/cmd-support/advice/${id}`)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Không thể tải phiên tư vấn"))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <>
      <PageHeader
        title={detail?.customer_name ?? "Chi tiết tư vấn"}
        description={detail ? `Tạo bởi ${detail.created_by_name} · ${new Date(detail.created_at).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}` : undefined}
        action={
          <Button variant="outline" onClick={() => router.push("/admin/cmd-advisory/history")}>
            <span className="material-symbols-outlined text-sm mr-1">arrow_back</span>
            Quay lại
          </Button>
        }
      />

      <div className="rounded-lg border border-primary/20 bg-secondary px-4 py-3 mb-4">
        <div className="flex items-start gap-2">
          <span className="material-symbols-outlined text-primary text-lg mt-0.5">info</span>
          <p className="text-sm text-foreground">
            Lưu ý: Kết quả tư vấn của AI mang tính tham khảo. RM phải xác minh điều kiện cấp tín dụng và tài liệu sản phẩm theo quy định BIDV hiện hành trước khi tư vấn cho khách hàng.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-destructive text-lg mt-0.5">error</span>
            <p className="text-sm text-destructive">{error}</p>
          </div>
        </div>
      ) : detail ? (
        <div className="space-y-6">
          {/* Input summary */}
          <div className="rounded-xl border border-border bg-card p-4 space-y-2">
            <h3 className="font-heading text-sm font-medium text-muted-foreground">Thông tin đầu vào</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-muted-foreground">Phân khúc:</span>{" "}
                <span className="text-foreground">
                  {detail.customer_segment
                    ? SEGMENT_SHORT_LABEL[detail.customer_segment] ?? detail.customer_segment
                    : "—"}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Tỉnh/TP:</span>{" "}
                <span className="text-foreground">{detail.province_name || "—"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Ngành nghề:</span>{" "}
                <span className="text-foreground">{detail.industry_name || "—"}</span>
              </div>
              <div className="sm:col-span-2">
                <span className="text-muted-foreground">Nhu cầu:</span>{" "}
                <span className="text-foreground">{detail.needs}</span>
              </div>
              {detail.additional_context && (
                <div className="sm:col-span-2">
                  <span className="text-muted-foreground">Ghi chú:</span>{" "}
                  <span className="text-foreground">{detail.additional_context}</span>
                </div>
              )}
            </div>
          </div>

          {/* Result */}
          <AdvisoryResult result={detail} loading={false} error={null} />
        </div>
      ) : null}
    </>
  );
}
