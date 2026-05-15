"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ProductSourceSelect, type ProductSourceValue } from "./product-source-select";
import { RulesTable } from "./rules-table";
import type { AiAssistResponse, ProductRule } from "./types";

const EMPTY_SOURCE: ProductSourceValue = { wikiPageId: null, customName: null };

export function ProductRulesTab() {
  const [rules, setRules] = useState<ProductRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [source, setSource] = useState<ProductSourceValue>(EMPTY_SOURCE);
  const [productNameForAi, setProductNameForAi] = useState("");
  const [basicInfo, setBasicInfo] = useState("");
  const [persona, setPersona] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await api<ProductRule[]>("/api/cmd-support/rules/products");
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
    setSource(EMPTY_SOURCE);
    setProductNameForAi("");
    setBasicInfo("");
    setPersona("");
    setErr(null);
  };

  const startEdit = (rule: ProductRule) => {
    setEditingId(rule.id);
    setSource({
      wikiPageId: rule.wiki_page_id,
      customName: rule.product_name_custom,
    });
    setProductNameForAi(rule.wiki_page_title || rule.product_name_custom || "");
    setBasicInfo(rule.basic_info ?? "");
    setPersona(rule.customer_persona);
    setErr(null);
  };

  const handleAi = async () => {
    if (!basicInfo.trim()) {
      setErr("Cần nhập 'Thông tin cơ bản' trước khi dùng AI hỗ trợ");
      return;
    }
    const productName = source.customName ?? productNameForAi ?? "";
    if (!productName.trim()) {
      setErr("Cần chọn hoặc nhập tên sản phẩm trước khi dùng AI hỗ trợ");
      return;
    }
    setAiBusy(true);
    setErr(null);
    try {
      const res = await api<AiAssistResponse>(
        "/api/cmd-support/rules/products/ai-assist",
        {
          method: "POST",
          body: { product_name: productName, basic_info: basicInfo },
          timeoutMs: 180_000,
        },
      );
      setPersona(res.generated_text);
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Lỗi AI",
      );
    } finally {
      setAiBusy(false);
    }
  };

  const handleSave = async () => {
    if (!source.wikiPageId && !source.customName) {
      setErr("Chọn sản phẩm từ dropdown hoặc nhập sản phẩm mới");
      return;
    }
    if (!persona.trim()) {
      setErr("Chân dung KH tiềm năng không được trống");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const body = {
        wiki_page_id: source.wikiPageId ?? undefined,
        product_name_custom: source.customName ?? undefined,
        basic_info: basicInfo || undefined,
        customer_persona: persona,
      };
      if (editingId) {
        await api(`/api/cmd-support/rules/products/${editingId}`, {
          method: "PUT",
          body,
        });
      } else {
        await api("/api/cmd-support/rules/products", { method: "POST", body });
      }
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
      await api(`/api/cmd-support/rules/products/${id}`, { method: "DELETE" });
      await refresh();
      if (editingId === id) resetForm();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lỗi xoá");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[480px_1fr] gap-6">
      {/* Form */}
      <div className="rounded-xl border border-border bg-card p-5 space-y-4 h-fit">
        <h2 className="text-base font-semibold">
          {editingId ? "Sửa quy tắc sản phẩm" : "Tạo quy tắc sản phẩm"}
        </h2>

        <div className="flex flex-col gap-1.5">
          <Label>Sản phẩm/Chính sách</Label>
          <ProductSourceSelect
            value={source}
            onChange={(next) => {
              setSource(next);
              if (next.customName) setProductNameForAi(next.customName);
            }}
            disabled={saving || aiBusy}
          />
          {source.wikiPageId && (
            <p className="text-[11px] text-muted-foreground">
              Liên kết tới wiki page (đã được AI phân loại từ tab Tri thức).
            </p>
          )}
          {source.customName && (
            <p className="text-[11px] text-muted-foreground">
              Sản phẩm tự nhập — chưa có trong wiki.
            </p>
          )}
        </div>

        {/* Optional product name override for AI assist when picked from wiki */}
        {source.wikiPageId && (
          <div className="flex flex-col gap-1.5">
            <Label>Tên sản phẩm dùng cho AI gợi ý</Label>
            <Input
              value={productNameForAi}
              onChange={(e) => setProductNameForAi(e.target.value)}
              placeholder="Tên ngắn để AI hiểu"
              disabled={aiBusy || saving}
            />
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label>Thông tin cơ bản (đầu vào cho AI)</Label>
          <Textarea
            rows={4}
            value={basicInfo}
            onChange={(e) => setBasicInfo(e.target.value)}
            placeholder="VD: Sản phẩm cho vay vốn lưu động, hạn mức tối đa 100 tỷ, thế chấp BĐS, lãi suất ưu đãi cho ngành sản xuất…"
            disabled={aiBusy || saving}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label>Chân dung khách hàng tiềm năng</Label>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={handleAi}
              disabled={aiBusy || saving || !basicInfo.trim()}
            >
              {aiBusy ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-sm mr-1">
                    progress_activity
                  </span>
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
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            placeholder="Mô tả chân dung khách hàng phù hợp với sản phẩm này. Có thể nhập tay hoặc dùng nút Hỗ trợ AI để gợi ý từ thông tin cơ bản."
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
            {saving ? "Đang lưu…" : editingId ? "Cập nhật" : "Tạo quy tắc"}
          </Button>
          {editingId && (
            <Button variant="outline" onClick={resetForm} disabled={saving}>
              Huỷ
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <RulesTable
        loading={loading}
        empty="Chưa có quy tắc sản phẩm nào."
        columns={[
          { header: "Sản phẩm", className: "w-[28%]" },
          { header: "Thông tin cơ bản" },
          { header: "Chân dung KH" },
          { header: "Cập nhật bởi", className: "w-[140px]" },
          { header: "", className: "w-[80px]" },
        ]}
        rows={rules.map((r) => ({
          key: r.id,
          cells: [
            r.wiki_page_title || r.product_name_custom || "—",
            <span key="basic" className="line-clamp-3 text-xs text-muted-foreground">
              {r.basic_info || "—"}
            </span>,
            <span key="persona" className="line-clamp-3 text-xs">{r.customer_persona || "—"}</span>,
            <span key="upd" className="text-xs text-muted-foreground">
              {r.updated_by?.name ?? "—"}
            </span>,
            <div key="act" className="flex gap-1 justify-end">
              <Button size="sm" variant="ghost" onClick={() => startEdit(r)}>
                <span className="material-symbols-outlined text-base">edit</span>
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleDelete(r.id)}
                className="text-destructive"
              >
                <span className="material-symbols-outlined text-base">delete</span>
              </Button>
            </div>,
          ],
        }))}
      />
    </div>
  );
}
