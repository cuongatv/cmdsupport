"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import {
  CUSTOMER_SEGMENTS,
  SEGMENT_SHORT_LABEL,
} from "@/components/cmd-support/segment-select";
import { RulesTable } from "./rules-table";
import type { AiAssistResponse, SegmentRule } from "./types";

export function SegmentRulesTab() {
  const [rules, setRules] = useState<SegmentRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [segment, setSegment] = useState<string>("sme");
  const [basicInfo, setBasicInfo] = useState("");
  const [specifics, setSpecifics] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await api<SegmentRule[]>("/api/cmd-support/rules/segments");
      setRules(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lỗi tải dữ liệu");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    refresh();
  }, []);

  const resetForm = () => {
    setEditingId(null);
    setSegment("sme");
    setBasicInfo("");
    setSpecifics("");
    setErr(null);
  };

  const startEdit = (rule: SegmentRule) => {
    setEditingId(rule.id);
    setSegment(rule.segment);
    setBasicInfo(rule.basic_info ?? "");
    setSpecifics(rule.segment_specifics);
    setErr(null);
  };

  const handleAi = async () => {
    if (!basicInfo.trim()) {
      setErr("Cần nhập 'Thông tin cơ bản' trước khi dùng AI hỗ trợ");
      return;
    }
    setAiBusy(true);
    setErr(null);
    try {
      const res = await api<AiAssistResponse>(
        "/api/cmd-support/rules/segments/ai-assist",
        {
          method: "POST",
          body: { segment, basic_info: basicInfo },
          timeoutMs: 180_000,
        },
      );
      setSpecifics(res.generated_text);
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Lỗi AI",
      );
    } finally {
      setAiBusy(false);
    }
  };

  const handleSave = async () => {
    if (!specifics.trim()) {
      setErr("Đặc thù phân khúc không được trống");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api("/api/cmd-support/rules/segments", {
        method: "POST",
        body: {
          segment,
          basic_info: basicInfo || undefined,
          segment_specifics: specifics,
        },
      });
      await refresh();
      resetForm();
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Lỗi lưu",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Xoá quy tắc này?")) return;
    try {
      await api(`/api/cmd-support/rules/segments/${id}`, { method: "DELETE" });
      await refresh();
      if (editingId === id) resetForm();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lỗi xoá");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[480px_1fr] gap-6">
      <div className="rounded-xl border border-border bg-card p-5 space-y-4 h-fit">
        <h2 className="text-base font-semibold">
          {editingId ? "Sửa quy tắc phân khúc" : "Tạo/cập nhật quy tắc phân khúc"}
        </h2>

        <div className="flex flex-col gap-1.5">
          <Label>Phân khúc khách hàng</Label>
          <Select value={segment} onValueChange={(v) => v && setSegment(v)} disabled={saving || aiBusy}>
            <SelectTrigger className="w-full">{SEGMENT_SHORT_LABEL[segment] ?? segment}</SelectTrigger>
            <SelectContent>
              {CUSTOMER_SEGMENTS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Thông tin cơ bản (đầu vào cho AI)</Label>
          <Textarea
            rows={4}
            value={basicInfo}
            onChange={(e) => setBasicInfo(e.target.value)}
            placeholder="VD: SME thường có doanh thu 20-200 tỷ, hồ sơ tài chính chưa chuẩn, cần linh hoạt hạn mức…"
            disabled={aiBusy || saving}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label>Đặc thù tư vấn cho phân khúc</Label>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={handleAi}
              disabled={aiBusy || saving || !basicInfo.trim()}
            >
              {aiBusy ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-sm mr-1">progress_activity</span>
                  Đang gợi ý…
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-sm mr-1">auto_awesome</span>
                  Hỗ trợ AI
                </>
              )}
            </Button>
          </div>
          <Textarea
            rows={10}
            value={specifics}
            onChange={(e) => setSpecifics(e.target.value)}
            placeholder="Mô tả đặc thù tư vấn cho phân khúc này (hành vi, sản phẩm phù hợp, lưu ý)."
            disabled={aiBusy || saving}
          />
        </div>

        {err && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
            {err}
          </div>
        )}

        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={saving} className="flex-1">
            {saving ? "Đang lưu…" : "Lưu"}
          </Button>
          {editingId && (
            <Button variant="outline" onClick={resetForm} disabled={saving}>
              Huỷ
            </Button>
          )}
        </div>
      </div>

      <RulesTable
        loading={loading}
        empty="Chưa có quy tắc phân khúc nào."
        columns={[
          { header: "Phân khúc", className: "w-[180px]" },
          { header: "Thông tin cơ bản" },
          { header: "Đặc thù" },
          { header: "Cập nhật bởi", className: "w-[140px]" },
          { header: "", className: "w-[80px]" },
        ]}
        rows={rules.map((r) => ({
          key: r.id,
          cells: [
            <span key="seg" className="font-medium">{SEGMENT_SHORT_LABEL[r.segment] ?? r.segment}</span>,
            <span key="basic" className="line-clamp-3 text-xs text-muted-foreground">{r.basic_info || "—"}</span>,
            <span key="spec" className="line-clamp-3 text-xs">{r.segment_specifics || "—"}</span>,
            <span key="upd" className="text-xs text-muted-foreground">{r.updated_by?.name ?? "—"}</span>,
            <div key="act" className="flex gap-1 justify-end">
              <Button size="sm" variant="ghost" onClick={() => startEdit(r)}>
                <span className="material-symbols-outlined text-base">edit</span>
              </Button>
              <Button size="sm" variant="ghost" onClick={() => handleDelete(r.id)} className="text-destructive">
                <span className="material-symbols-outlined text-base">delete</span>
              </Button>
            </div>,
          ],
        }))}
      />
    </div>
  );
}
