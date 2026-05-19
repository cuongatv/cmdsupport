"use client";

import { useState } from "react";
import Image from "next/image";
import { api, ApiError, apiUpload } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  CategoryPicker,
  type IdeaCategory,
} from "@/components/ideas/category-picker";
import { ImageUpload, type StagedImage } from "@/components/ideas/image-upload";

const ZALO_PHONE = "0983736500";
// Zalo deep link — opens chat directly with the admin's phone number.
const ZALO_CHAT_URL = `https://zalo.me/${ZALO_PHONE}`;

type SubmitResponse = { id: string; created_at: string };

type FormErrors = {
  contributor_name?: string;
  description?: string;
  contributor_email?: string;
};

export default function PublicIdeasPage() {
  const [contributorName, setContributorName] = useState("");
  const [contributorPhone, setContributorPhone] = useState("");
  const [contributorEmail, setContributorEmail] = useState("");
  const [contributorDepartment, setContributorDepartment] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [currentPain, setCurrentPain] = useState("");
  const [expectedBenefit, setExpectedBenefit] = useState("");
  const [referenceSystem, setReferenceSystem] = useState("");
  const [category, setCategory] = useState<IdeaCategory>("feature");
  const [images, setImages] = useState<StagedImage[]>([]);

  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [topError, setTopError] = useState<string | null>(null);
  const [submittedId, setSubmittedId] = useState<string | null>(null);

  const validate = (): boolean => {
    const errs: FormErrors = {};
    if (!contributorName.trim()) {
      errs.contributor_name = "Vui lòng nhập tên của Anh/Chị.";
    }
    if (!description.trim() || description.trim().length < 10) {
      errs.description = "Mô tả ý tưởng cần ít nhất 10 ký tự.";
    }
    if (contributorEmail.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contributorEmail.trim())) {
      errs.contributor_email = "Email không hợp lệ.";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    setTopError(null);

    try {
      const created = await api<SubmitResponse>("/api/public/ideas", {
        method: "POST",
        body: {
          contributor_name: contributorName.trim(),
          contributor_phone: contributorPhone.trim() || undefined,
          contributor_email: contributorEmail.trim() || undefined,
          contributor_department: contributorDepartment.trim() || undefined,
          title: title.trim() || undefined,
          description: description.trim(),
          current_pain: currentPain.trim() || undefined,
          expected_benefit: expectedBenefit.trim() || undefined,
          reference_system: referenceSystem.trim() || undefined,
          category,
        },
      });

      // Upload images sequentially — keep it simple, friendlier error reporting.
      for (const img of images) {
        const fd = new FormData();
        fd.append("file", img.file, img.file.name);
        try {
          await apiUpload(`/api/public/ideas/${created.id}/images`, fd);
        } catch (uploadErr) {
          // Best-effort: surface the issue but don't lose the submission.
          const msg =
            uploadErr instanceof Error ? uploadErr.message : "Lỗi tải ảnh.";
          setTopError(
            `Góp ý đã được gửi, nhưng có ảnh tải lên thất bại: ${msg}`
          );
        }
      }

      setSubmittedId(created.id);
      // Cleanup preview URLs
      images.forEach((i) => URL.revokeObjectURL(i.previewUrl));
    } catch (err) {
      if (err instanceof ApiError) {
        setTopError(err.message);
      } else if (err instanceof Error) {
        setTopError(err.message);
      } else {
        setTopError("Không thể gửi góp ý. Vui lòng thử lại.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setContributorName("");
    setContributorPhone("");
    setContributorEmail("");
    setContributorDepartment("");
    setTitle("");
    setDescription("");
    setCurrentPain("");
    setExpectedBenefit("");
    setReferenceSystem("");
    setCategory("feature");
    setImages([]);
    setErrors({});
    setTopError(null);
    setSubmittedId(null);
  };

  if (submittedId) {
    return (
      <div className="w-full max-w-2xl mx-auto px-4 sm:px-6 py-12 sm:py-20 flex flex-col items-center text-center gap-6">
        <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
          <span
            className="material-symbols-outlined text-primary text-[44px]"
            style={{
              fontVariationSettings: "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 48",
            }}
          >
            check_circle
          </span>
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl font-bold font-heading">
            Cảm ơn Anh/Chị!
          </h1>
          <p className="text-muted-foreground max-w-md">
            Góp ý của Anh/Chị đã được ghi nhận. Đội phát triển CMD Support sẽ
            xem xét và phản hồi sớm nhất có thể.
          </p>
          <p className="text-xs text-muted-foreground/70">
            Mã góp ý:{" "}
            <span className="font-mono text-foreground/80">
              {submittedId.slice(0, 8)}
            </span>
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
          <Button onClick={resetForm} variant="outline" size="lg">
            <span className="material-symbols-outlined mr-1 text-[18px]">
              add
            </span>
            Gửi góp ý khác
          </Button>
          <a
            href={ZALO_CHAT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-lg bg-[#0068FF] text-white text-sm font-semibold hover:bg-[#0050C8] transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">chat</span>
            Trao đổi thêm qua Zalo
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-10 flex flex-col gap-8 pb-32 lg:pb-10">
      {/* ─── Hero ─── */}
      <section className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/10 via-primary/[0.04] to-tertiary/10 px-6 py-8 sm:px-10 sm:py-12">
        <div className="absolute -top-20 -right-20 w-72 h-72 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-16 w-72 h-72 rounded-full bg-tertiary/10 blur-3xl pointer-events-none" />
        <div className="relative flex flex-col sm:flex-row items-start gap-6">
          <div className="flex-1 space-y-3 min-w-0">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold uppercase tracking-wide">
              <span
                className="material-symbols-outlined text-[14px]"
                style={{
                  fontVariationSettings:
                    "'FILL' 1, 'wght' 600, 'GRAD' 0, 'opsz' 14",
                }}
              >
                campaign
              </span>
              Cộng đồng CMD Support
            </div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold font-heading leading-tight text-foreground">
              Cùng nâng cấp hệ thống{" "}
              <span className="text-primary">CMD Support</span>
            </h1>
            <p className="text-sm sm:text-base text-muted-foreground max-w-2xl leading-relaxed">
              Anh/Chị có ý tưởng cải tiến, tính năng mới, hay phản hồi về
              trải nghiệm sử dụng? Hãy chia sẻ ngay — mỗi góp ý đều là tư liệu
              quý giá giúp nhà phát triển hoàn thiện hệ thống.
            </p>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px] text-primary">
                  verified
                </span>
                Ẩn danh nếu muốn
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px] text-primary">
                  schedule
                </span>
                Phản hồi nhanh chóng
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px] text-primary">
                  forum
                </span>
                Trao đổi 1-1 qua Zalo
              </span>
            </div>
          </div>
          <a
            href={ZALO_CHAT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0068FF] text-white text-sm font-semibold shadow-lg shadow-[#0068FF]/20 hover:bg-[#0050C8] hover:shadow-xl hover:-translate-y-0.5 transition-all"
            title="Mở Zalo và chat ngay với admin"
          >
            <span
              className="material-symbols-outlined text-[20px]"
              style={{
                fontVariationSettings:
                  "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 20",
              }}
            >
              chat
            </span>
            Chat Zalo ngay
            <span className="text-[11px] opacity-90 font-normal hidden sm:inline">
              ({ZALO_PHONE})
            </span>
          </a>
        </div>
      </section>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {/* ─── Step 1: Category ─── */}
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
              1
            </div>
            <h2 className="text-base font-semibold font-heading">
              Loại góp ý
            </h2>
          </div>
          <CategoryPicker
            value={category}
            onChange={setCategory}
            disabled={submitting}
          />
        </section>

        {/* ─── Step 2: Idea ─── */}
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-6 space-y-5">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
              2
            </div>
            <h2 className="text-base font-semibold font-heading">
              Nội dung ý tưởng
            </h2>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-sm">
              Tiêu đề ngắn{" "}
              <span className="text-muted-foreground font-normal">
                (tuỳ chọn)
              </span>
            </Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VD: Cho phép tải file lên hàng loạt"
              className="bg-background"
              maxLength={300}
              disabled={submitting}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-sm">
              Mô tả ý tưởng <span className="text-destructive">*</span>
            </Label>
            <Textarea
              rows={5}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setErrors((p) => ({ ...p, description: undefined }));
              }}
              placeholder="Mô tả chi tiết tính năng/ý tưởng của Anh/Chị — càng cụ thể càng tốt..."
              className="bg-background"
              aria-invalid={!!errors.description}
              disabled={submitting}
            />
            {errors.description && (
              <p className="text-xs text-destructive">{errors.description}</p>
            )}
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label className="text-sm">
                Vấn đề hiện tại{" "}
                <span className="text-muted-foreground font-normal">
                  (tuỳ chọn)
                </span>
              </Label>
              <Textarea
                rows={3}
                value={currentPain}
                onChange={(e) => setCurrentPain(e.target.value)}
                placeholder="Anh/Chị đang gặp khó khăn gì với hệ thống hiện tại?"
                className="bg-background"
                disabled={submitting}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-sm">
                Lợi ích mong đợi{" "}
                <span className="text-muted-foreground font-normal">
                  (tuỳ chọn)
                </span>
              </Label>
              <Textarea
                rows={3}
                value={expectedBenefit}
                onChange={(e) => setExpectedBenefit(e.target.value)}
                placeholder="Nếu được triển khai, ý tưởng này sẽ giúp ích như thế nào?"
                className="bg-background"
                disabled={submitting}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-sm">
              Hệ thống tham khảo{" "}
              <span className="text-muted-foreground font-normal">
                (tuỳ chọn)
              </span>
            </Label>
            <Input
              value={referenceSystem}
              onChange={(e) => setReferenceSystem(e.target.value)}
              placeholder="VD: Slack, Notion, JIRA, link bài viết tham khảo..."
              className="bg-background"
              maxLength={500}
              disabled={submitting}
            />
            <p className="text-xs text-muted-foreground">
              Hệ thống/sản phẩm Anh/Chị thấy đã làm tốt việc này — giúp đội
              phát triển hình dung nhanh hơn.
            </p>
          </div>
        </section>

        {/* ─── Step 3: Images ─── */}
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-6 space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
              3
            </div>
            <h2 className="text-base font-semibold font-heading">
              Ảnh minh hoạ{" "}
              <span className="text-muted-foreground text-sm font-normal">
                (tuỳ chọn)
              </span>
            </h2>
          </div>
          <ImageUpload
            images={images}
            onChange={setImages}
            disabled={submitting}
          />
        </section>

        {/* ─── Step 4: Contact ─── */}
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-6 space-y-5">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
              4
            </div>
            <h2 className="text-base font-semibold font-heading">
              Thông tin liên hệ
            </h2>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label className="text-sm">
                Tên của Anh/Chị <span className="text-destructive">*</span>
              </Label>
              <Input
                value={contributorName}
                onChange={(e) => {
                  setContributorName(e.target.value);
                  setErrors((p) => ({ ...p, contributor_name: undefined }));
                }}
                placeholder="VD: Nguyễn Văn A"
                className="bg-background"
                aria-invalid={!!errors.contributor_name}
                maxLength={200}
                disabled={submitting}
              />
              {errors.contributor_name && (
                <p className="text-xs text-destructive">
                  {errors.contributor_name}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-sm">
                Số điện thoại{" "}
                <span className="text-muted-foreground font-normal">
                  (tuỳ chọn)
                </span>
              </Label>
              <Input
                type="tel"
                value={contributorPhone}
                onChange={(e) => setContributorPhone(e.target.value)}
                placeholder="VD: 0901234567"
                className="bg-background"
                maxLength={50}
                disabled={submitting}
                inputMode="tel"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-sm">
                Email{" "}
                <span className="text-muted-foreground font-normal">
                  (tuỳ chọn)
                </span>
              </Label>
              <Input
                type="email"
                value={contributorEmail}
                onChange={(e) => {
                  setContributorEmail(e.target.value);
                  setErrors((p) => ({ ...p, contributor_email: undefined }));
                }}
                placeholder="Để chúng tôi phản hồi khi cần"
                className="bg-background"
                aria-invalid={!!errors.contributor_email}
                maxLength={200}
                disabled={submitting}
              />
              {errors.contributor_email && (
                <p className="text-xs text-destructive">
                  {errors.contributor_email}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-sm">
                Đơn vị / Phòng ban{" "}
                <span className="text-muted-foreground font-normal">
                  (tuỳ chọn)
                </span>
              </Label>
              <Input
                value={contributorDepartment}
                onChange={(e) => setContributorDepartment(e.target.value)}
                placeholder="VD: Chi nhánh Hà Nội, Phòng KHDN..."
                className="bg-background"
                maxLength={200}
                disabled={submitting}
              />
            </div>
          </div>
        </section>

        {topError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 flex items-start gap-2">
            <span className="material-symbols-outlined text-destructive text-[20px] mt-0.5">
              error
            </span>
            <p className="text-sm text-destructive">{topError}</p>
          </div>
        )}

        {/* ─── Submit (desktop) ─── */}
        <div className="hidden lg:flex items-center justify-between gap-4">
          <p className="text-xs text-muted-foreground">
            Bằng việc gửi góp ý, Anh/Chị đồng ý cho phép đội ngũ CMD Support
            liên hệ lại để làm rõ chi tiết nếu cần.
          </p>
          <Button
            type="submit"
            size="lg"
            className="min-h-[44px] px-8 text-base font-semibold"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[18px]">
                  progress_activity
                </span>
                Đang gửi…
              </>
            ) : (
              <>
                <span
                  className="material-symbols-outlined text-[18px]"
                  style={{
                    fontVariationSettings:
                      "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 18",
                  }}
                >
                  send
                </span>
                Gửi góp ý
              </>
            )}
          </Button>
        </div>
      </form>

      {/* ─── Sticky CTA (mobile) ─── */}
      <div className="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-background/95 backdrop-blur border-t border-border px-4 py-3 flex gap-2 items-center">
        <a
          href={ZALO_CHAT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 w-11 h-11 rounded-lg bg-[#0068FF] text-white flex items-center justify-center"
          title="Chat Zalo"
        >
          <span className="material-symbols-outlined text-[20px]">chat</span>
        </a>
        <Button
          type="button"
          onClick={() => handleSubmit()}
          size="lg"
          className="flex-1 min-h-[44px] text-base font-semibold"
          disabled={submitting}
        >
          {submitting ? (
            <>
              <span className="material-symbols-outlined animate-spin text-[18px]">
                progress_activity
              </span>
              Đang gửi…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-[18px]">
                send
              </span>
              Gửi góp ý
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
