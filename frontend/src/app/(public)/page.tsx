"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { CmdSupportBanner } from "@/components/cmd-support/banner";
import { AdvisoryResult, type AdviceDetail } from "@/components/cmd-support/advisory-result";
import { SegmentSelect } from "@/components/cmd-support/segment-select";
import { ProvinceSelect } from "@/components/cmd-support/province-select";
import { IndustrySelect } from "@/components/cmd-support/industry-select";

export default function PublicHomePage() {
  const { user } = useAuth();
  const [customerName, setCustomerName] = useState("");
  const [segment, setSegment] = useState("sme");
  const [provinceCode, setProvinceCode] = useState("");
  const [industryCode, setIndustryCode] = useState("");
  const [needs, setNeeds] = useState("");
  const [additionalContext, setAdditionalContext] = useState("");
  const [formErrors, setFormErrors] = useState<{ customer_name?: string; needs?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdviceDetail | null>(null);

  const validate = (): boolean => {
    const errs: { customer_name?: string; needs?: string } = {};
    if (!customerName.trim()) errs.customer_name = "Tên khách hàng là bắt buộc";
    if (!needs.trim() || needs.trim().length < 10) errs.needs = "Mô tả nhu cầu phải có ít nhất 10 ký tự";
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const data = await api<AdviceDetail>("/api/cmd-support/advice", {
        method: "POST",
        body: {
          customer_name: customerName.trim(),
          customer_segment: segment,
          province_code: provinceCode || undefined,
          industry_code: industryCode || undefined,
          needs: needs.trim(),
          additional_context: additionalContext.trim() || undefined,
        },
        timeoutMs: 120_000,
      });
      setResult(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setError(
          user
            ? 'Dịch vụ AI tạm thời chưa sẵn sàng. Chưa cấu hình AI provider. Vui lòng mở Cài đặt (/admin/settings) để cấu hình.'
            : "Dịch vụ AI tạm thời chưa sẵn sàng. Vui lòng quay lại sau."
        );
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Đã xảy ra lỗi không xác định.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const renderError = () => {
    if (!error) return null;
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
        <div className="flex items-start gap-2">
          <span className="material-symbols-outlined text-destructive text-lg mt-0.5">error</span>
          <div className="flex-1">
            <p className="text-sm text-destructive">{error}</p>
            {user && error.includes("Cài đặt") && (
              <Link href="/admin/settings" className="text-sm text-primary hover:underline mt-1 inline-block">
                Mở Cài đặt
              </Link>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-10 py-6 sm:py-8 flex flex-col gap-6 flex-1">
      <CmdSupportBanner />

      {/* Disclaimer banner */}
      <div className="rounded-lg border border-primary/20 bg-secondary px-4 py-3">
        <div className="flex items-start gap-2">
          <span className="material-symbols-outlined text-primary text-lg mt-0.5">gavel</span>
          <p className="text-sm text-foreground">
            Lưu ý: Kết quả tư vấn của AI mang tính tham khảo. RM phải xác minh điều kiện cấp tín dụng và tài liệu sản phẩm theo quy định BIDV hiện hành trước khi tư vấn cho khách hàng.
          </p>
        </div>
      </div>

      {/* Form + Result grid 420px / fluid */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-6">
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-card p-5 space-y-4">
            <div className="flex flex-col gap-1.5">
              <Label>
                Tên khách hàng <span className="text-destructive">*</span>
              </Label>
              <Input
                value={customerName}
                onChange={(e) => {
                  setCustomerName(e.target.value);
                  setFormErrors((p) => ({ ...p, customer_name: undefined }));
                }}
                placeholder="VD: Công ty TNHH ABC"
                className="bg-background text-base"
                aria-invalid={!!formErrors.customer_name}
                disabled={submitting}
              />
              {formErrors.customer_name && (
                <p className="text-xs text-destructive">{formErrors.customer_name}</p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Phân khúc khách hàng</Label>
              <SegmentSelect value={segment} onValueChange={setSegment} disabled={submitting} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Tỉnh/Thành phố</Label>
              <ProvinceSelect value={provinceCode} onValueChange={setProvinceCode} disabled={submitting} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Ngành nghề</Label>
              <IndustrySelect value={industryCode} onValueChange={setIndustryCode} disabled={submitting} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>
                Mô tả nhu cầu khách hàng <span className="text-destructive">*</span>
              </Label>
              <Textarea
                rows={6}
                value={needs}
                onChange={(e) => {
                  setNeeds(e.target.value);
                  setFormErrors((p) => ({ ...p, needs: undefined }));
                }}
                placeholder="VD: Khách hàng cần vay vốn lưu động 50 tỷ, có nhu cầu mở L/C nhập khẩu nguyên liệu..."
                className="bg-background text-base"
                aria-invalid={!!formErrors.needs}
                disabled={submitting}
              />
              {formErrors.needs && (
                <p className="text-xs text-destructive">{formErrors.needs}</p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Ghi chú bổ sung (tuỳ chọn)</Label>
              <Textarea
                rows={3}
                value={additionalContext}
                onChange={(e) => setAdditionalContext(e.target.value)}
                placeholder="Thông tin bổ sung về khách hàng..."
                className="bg-background text-base"
                disabled={submitting}
              />
            </div>

            <Button
              className="w-full min-h-[44px] text-base hidden lg:flex"
              disabled={submitting}
              onClick={handleSubmit}
            >
              {submitting ? (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                  Đang phân tích…
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm">auto_awesome</span>
                  Phân tích bằng AI
                </span>
              )}
            </Button>

            {renderError()}
          </div>
        </div>

        <div className="min-h-0 lg:overflow-y-auto">
          <AdvisoryResult result={result} loading={submitting} error={null} />
        </div>
      </div>

      {/* Sticky CTA mobile */}
      <div className="lg:hidden fixed bottom-0 left-0 right-0 z-30 bg-background border-t border-border p-4">
        <Button
          className="w-full min-h-[44px] text-base"
          disabled={submitting}
          onClick={handleSubmit}
        >
          {submitting ? (
            <span className="flex items-center gap-2">
              <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
              Đang phân tích…
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <span className="material-symbols-outlined text-sm">auto_awesome</span>
              Phân tích bằng AI
            </span>
          )}
        </Button>
      </div>
    </div>
  );
}
