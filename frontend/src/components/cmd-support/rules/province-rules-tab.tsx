"use client";

import { useEffect, useMemo, useState } from "react";
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
import { RulesTable } from "./rules-table";
import type { AiAssistResponse, ProvinceRule } from "./types";

type ProvinceOption = { id: string; code: string; name: string; short_name: string };

export function ProvinceRulesTab() {
  const [rules, setRules] = useState<ProvinceRule[]>([]);
  const [provinces, setProvinces] = useState<ProvinceOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [provinceId, setProvinceId] = useState<string>("");
  const [basicInfo, setBasicInfo] = useState("");
  const [specifics, setSpecifics] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const [r, p] = await Promise.all([
        api<ProvinceRule[]>("/api/cmd-support/rules/provinces"),
        api<ProvinceOption[]>("/api/cmd-support/rules/sources/provinces"),
      ]);
      setRules(r);
      setProvinces(p);
      if (!provinceId && p.length > 0) setProvinceId(p[0].id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lỗi tải dữ liệu");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const provinceLabel = useMemo(() => {
    const found = provinces.find((p) => p.id === provinceId);
    return found ? found.short_name : "Chọn tỉnh/thành";
  }, [provinces, provinceId]);

  const resetForm = () => {
    setEditingId(null);
    setBasicInfo("");
    setSpecifics("");
    if (provinces.length > 0) setProvinceId(provinces[0].id);
    setErr(null);
  };

  const startEdit = (rule: ProvinceRule) => {
    setEditingId(rule.id);
    setProvinceId(rule.province_id);
    setBasicInfo(rule.basic_info ?? "");
    setSpecifics(rule.province_specifics);
    setErr(null);
  };

  const handleAi = async () => {
    if (!basicInfo.trim()) {
      setErr("Cần nhập 'Thông tin cơ bản' trước khi dùng AI hỗ trợ");
      return;
    }
    if (!provinceId) {
      setErr("Chọn tỉnh/thành trước khi dùng AI hỗ trợ");
      return;
    }
    setAiBusy(true);
    setErr(null);
    try {
      const res = await api<AiAssistResponse>(
        "/api/cmd-support/rules/provinces/ai-assist",
        {
          method: "POST",
          body: { province_id: provinceId, basic_info: basicInfo },
          timeoutMs: 180_000,
        },
      );
      setSpecifics(res.generated_text);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Lỗi AI");
    } finally {
      setAiBusy(false);
    }
  };

  const handleSave = async () => {
    if (!provinceId) {
      setErr("Chọn tỉnh/thành");
      return;
    }
    if (!specifics.trim()) {
      setErr("Đặc thù địa bàn không được trống");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api("/api/cmd-support/rules/provinces", {
        method: "POST",
        body: {
          province_id: provinceId,
          basic_info: basicInfo || undefined,
          province_specifics: specifics,
        },
      });
      await refresh();
      resetForm();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Lỗi lưu");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Xoá quy tắc này?")) return;
    try {
      await api(`/api/cmd-support/rules/provinces/${id}`, { method: "DELETE" });
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
          {editingId ? "Sửa quy tắc địa bàn" : "Tạo/cập nhật quy tắc địa bàn"}
        </h2>

        <div className="flex flex-col gap-1.5">
          <Label>Tỉnh/Thành phố</Label>
          <Select value={provinceId} onValueChange={(v) => v && setProvinceId(v)} disabled={saving || aiBusy}>
            <SelectTrigger className="w-full">{provinceLabel}</SelectTrigger>
            <SelectContent>
              {provinces.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.short_name}
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
            placeholder="VD: Hà Nội — kinh tế đa dạng, nhiều DN xuất nhập khẩu, dịch vụ tài chính phát triển…"
            disabled={aiBusy || saving}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label>Đặc thù tư vấn theo địa bàn</Label>
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
            placeholder="Mô tả đặc thù địa bàn (ngành chủ đạo, sản phẩm BIDV ưu tiên, lưu ý văn hoá)."
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
        empty="Chưa có quy tắc địa bàn nào."
        columns={[
          { header: "Tỉnh/Thành", className: "w-[180px]" },
          { header: "Thông tin cơ bản" },
          { header: "Đặc thù" },
          { header: "Cập nhật bởi", className: "w-[140px]" },
          { header: "", className: "w-[80px]" },
        ]}
        rows={rules.map((r) => ({
          key: r.id,
          cells: [
            <span className="font-medium">{r.province_name ?? "—"}</span>,
            <span className="line-clamp-3 text-xs text-muted-foreground">{r.basic_info || "—"}</span>,
            <span className="line-clamp-3 text-xs">{r.province_specifics || "—"}</span>,
            <span className="text-xs text-muted-foreground">{r.updated_by?.name ?? "—"}</span>,
            <div className="flex gap-1 justify-end">
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
