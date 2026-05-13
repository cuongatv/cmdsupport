"use client";

import * as React from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Source } from "./types";

type PlanPage = {
  action?: string;
  slug?: string;
  title?: string;
  page_type?: string;
  entity_names?: string[];
  related_kb_pages?: string[];
  priority?: number;
};

type PlanRevision = {
  id: string;
  feedback: string;
  status: string;
  base_version: number;
  requested_by: string | null;
  created_at: string | null;
  completed_at: string | null;
  error_message: string | null;
};

type PlanResponse = {
  source_id: string;
  plan_id: string;
  status: string;
  version: number;
  strategy: string | null;
  pipeline_phase: string | null;
  plan: {
    pages?: PlanPage[];
    source_page_slug?: string;
    estimated_page_count?: number;
    compilation_notes?: string;
  };
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string | null;
  revisions: PlanRevision[];
};

type Props = {
  source: Source;
  onClose: () => void;
  onReviewed: () => void;
};

const POLL_INTERVAL_MS = 4000;
// Cap polling so a stuck revising plan (worker chết, redis fail) không tạo
// tải vô hạn lên API. ~5 phút là quá đủ cho REDUCE rerun trên doc lớn.
const MAX_POLL_ATTEMPTS = 75;

export function PlanReviewDialog({ source, onClose, onReviewed }: Props) {
  const [plan, setPlan] = React.useState<PlanResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [submitting, setSubmitting] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [feedback, setFeedback] = React.useState("");
  const [info, setInfo] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const fetchPlan = React.useCallback(async () => {
    try {
      const data = await api<PlanResponse>(`/api/sources/${source.id}/plan`);
      setPlan(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được kế hoạch");
      return null;
    }
  }, [source.id]);

  React.useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const loadOnce = async () => {
      setLoading(true);
      const data = await fetchPlan();
      if (!active) return;
      setLoading(false);
      attempts += 1;
      if (data?.status === "revising") {
        if (attempts >= MAX_POLL_ATTEMPTS) {
          setError(
            "Kế hoạch vẫn đang được tạo lại quá lâu. Hãy đóng và mở lại hộp thoại để tiếp tục theo dõi.",
          );
          return;
        }
        timer = setTimeout(loadOnce, POLL_INTERVAL_MS);
      }
    };

    void loadOnce();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [fetchPlan]);

  const isRevising = plan?.status === "revising";

  const handleApprove = async () => {
    setSubmitting(true);
    setError(null);
    setInfo(null);
    try {
      await api(`/api/sources/${source.id}/plan/approve`, {
        method: "POST",
        body: { note: note || null },
      });
      onReviewed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Duyệt thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    setSubmitting(true);
    setError(null);
    setInfo(null);
    try {
      await api(`/api/sources/${source.id}/plan/reject`, {
        method: "POST",
        body: { note: note || null },
      });
      onReviewed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Từ chối thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevise = async () => {
    const trimmed = feedback.trim();
    if (!trimmed) {
      setError("Vui lòng nhập yêu cầu chỉnh sửa kế hoạch.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setInfo(null);
    try {
      await api(`/api/sources/${source.id}/plan/revise`, {
        method: "POST",
        body: { feedback: trimmed },
      });
      setInfo("Đã gửi yêu cầu chỉnh sửa. Đang tạo lại kế hoạch...");
      setFeedback("");
      await fetchPlan();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi yêu cầu chỉnh sửa thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  const pages = plan?.plan.pages ?? [];
  const creates = pages.filter((p) => (p.action ?? "CREATE").toUpperCase() === "CREATE");
  const updates = pages.filter((p) => (p.action ?? "CREATE").toUpperCase() === "UPDATE");

  return (
    <Dialog open onOpenChange={(value) => (!value ? onClose() : undefined)}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-heading">
            Duyệt kế hoạch MRP — {source.title || source.file_name || source.id}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground">Đang tải kế hoạch…</p>
        ) : !plan ? (
          <p className="text-sm text-muted-foreground">
            {error ?? "Không có dữ liệu kế hoạch."}
          </p>
        ) : (
          <div className="flex flex-col gap-4 mt-2">
            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <div>
                Trạng thái:{" "}
                <span className="text-foreground">
                  {plan.status}
                  {isRevising ? " (đang tạo lại…)" : ""}
                </span>
              </div>
              <div>
                Phiên bản plan:{" "}
                <span className="text-foreground">v{plan.version}</span>
              </div>
              <div>
                Chiến lược:{" "}
                <span className="text-foreground">{plan.strategy || "—"}</span>
              </div>
              <div>
                Pha hiện tại:{" "}
                <span className="text-foreground">{plan.pipeline_phase || "—"}</span>
              </div>
              <div>
                Số trang dự kiến:{" "}
                <span className="text-foreground">
                  {plan.plan.estimated_page_count ?? pages.length}
                </span>
              </div>
            </div>

            {plan.plan.compilation_notes && (
              <div className="text-sm bg-muted/50 px-3 py-2 rounded-lg">
                {plan.plan.compilation_notes}
              </div>
            )}

            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Tạo mới ({creates.length})</h3>
              <ul className="text-sm space-y-1 max-h-40 overflow-y-auto pr-2">
                {creates.length === 0 ? (
                  <li className="text-muted-foreground">Không có trang mới.</li>
                ) : (
                  creates.map((p) => (
                    <li key={`c-${p.slug}`} className="flex flex-col">
                      <span className="font-medium">{p.title || p.slug}</span>
                      <span className="text-xs text-muted-foreground">{p.slug}</span>
                    </li>
                  ))
                )}
              </ul>
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Cập nhật ({updates.length})</h3>
              <ul className="text-sm space-y-1 max-h-40 overflow-y-auto pr-2">
                {updates.length === 0 ? (
                  <li className="text-muted-foreground">Không có trang cần cập nhật.</li>
                ) : (
                  updates.map((p) => (
                    <li key={`u-${p.slug}`} className="flex flex-col">
                      <span className="font-medium">{p.title || p.slug}</span>
                      <span className="text-xs text-muted-foreground">{p.slug}</span>
                    </li>
                  ))
                )}
              </ul>
            </section>

            {plan.revisions.length > 0 && (
              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Lịch sử yêu cầu chỉnh sửa</h3>
                <ul className="text-xs space-y-2 max-h-40 overflow-y-auto pr-2">
                  {plan.revisions.map((rev) => (
                    <li
                      key={rev.id}
                      className="border rounded-md px-2 py-1.5 bg-background"
                    >
                      <div className="flex justify-between gap-2">
                        <span className="font-medium">
                          v{rev.base_version} → {rev.status}
                        </span>
                        <span className="text-muted-foreground">
                          {rev.created_at?.slice(0, 19).replace("T", " ")}
                        </span>
                      </div>
                      <p className="mt-0.5 whitespace-pre-wrap">{rev.feedback}</p>
                      {rev.error_message && (
                        <p className="mt-0.5 text-destructive">
                          Lỗi: {rev.error_message}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plan-revise">Yêu cầu chỉnh sửa kế hoạch</Label>
              <textarea
                id="plan-revise"
                className="min-h-[72px] rounded-md border bg-background px-3 py-2 text-sm"
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Ví dụ: gộp 3 trang khách hàng SME thành 1, đổi page_type sang topic, bỏ trang nhân sự không liên quan..."
                disabled={submitting || isRevising}
              />
              <p className="text-[11px] text-muted-foreground">
                Hệ thống sẽ chạy lại bước REDUCE (planning) dựa trên phản hồi này. MAP cache được giữ nguyên.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plan-note">Ghi chú duyệt / từ chối (tùy chọn)</Label>
              <textarea
                id="plan-note"
                className="min-h-[60px] rounded-md border bg-background px-3 py-2 text-sm"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Lý do duyệt hoặc từ chối"
                disabled={submitting || isRevising}
              />
            </div>

            {info && <p className="text-sm text-primary">{info}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="outline"
                onClick={onClose}
                disabled={submitting}
              >
                Đóng
              </Button>
              <Button
                variant="outline"
                onClick={handleRevise}
                disabled={submitting || isRevising || !feedback.trim()}
              >
                Yêu cầu chỉnh sửa
              </Button>
              <Button
                variant="destructive"
                onClick={handleReject}
                disabled={submitting || isRevising || plan.status === "rejected"}
              >
                Từ chối
              </Button>
              <Button
                onClick={handleApprove}
                disabled={submitting || isRevising || plan.status === "approved"}
                className="bg-primary text-primary-foreground hover:bg-primary/90"
              >
                Duyệt và biên dịch
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
