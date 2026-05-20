"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  generateTelegramLinkCode,
  getMyTelegramIdentity,
  revokeMyTelegramIdentity,
} from "@/lib/telegram-api";
import type {
  LinkCodeResponse,
  TelegramIdentity,
} from "@/lib/telegram-types";

const LINK_INSTRUCTION =
  "Tìm CMDSupportBot trên Telegram (hoặc bot này trong nhóm Squad), chat riêng và nhập lệnh trên. Mã hết hạn sau 10 phút.";

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("vi-VN");
  } catch {
    return value;
  }
}

export function UserTelegramSection() {
  const [identity, setIdentity] = useState<TelegramIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [linkCode, setLinkCode] = useState<LinkCodeResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getMyTelegramIdentity();
      setIdentity(result);
      if (result && result.is_active) {
        // Linked: discard any stale pending code
        setLinkCode(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được thông tin Telegram");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      const data = await generateTelegramLinkCode();
      setLinkCode(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được mã liên kết");
    } finally {
      setGenerating(false);
    }
  };

  const handleRevoke = async () => {
    if (!confirm("Hủy liên kết tài khoản Telegram?")) return;
    setRevoking(true);
    setError("");
    try {
      await revokeMyTelegramIdentity();
      setLinkCode(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không hủy được liên kết");
    } finally {
      setRevoking(false);
    }
  };

  const handleCopy = (text: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isLinked = Boolean(identity && identity.is_active);
  const command = linkCode ? `/link ${linkCode.link_code}` : "";

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex items-center gap-3 mb-4">
        <span className="material-symbols-outlined text-primary">send</span>
        <div>
          <h3 className="text-lg font-semibold text-foreground">
            Liên kết Telegram
          </h3>
          <p className="text-xs text-muted-foreground">
            Kết nối tài khoản Telegram để dùng lệnh /task, /done… trong nhóm Squad.
          </p>
        </div>
      </div>

      {error && (
        <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg mb-4">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : isLinked && identity ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 px-4 py-3 rounded-lg border border-green-200">
            <span className="material-symbols-outlined text-base">check_circle</span>
            <span>Đã liên kết tài khoản Telegram.</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <div>
              <p className="text-xs text-muted-foreground">Tên hiển thị</p>
              <p className="text-sm font-medium mt-1">
                {identity.display_name ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Tên người dùng Telegram</p>
              <p className="text-sm font-medium mt-1">
                {identity.telegram_username ? `@${identity.telegram_username}` : "—"}
              </p>
            </div>
            <div className="sm:col-span-2">
              <p className="text-xs text-muted-foreground">Đã liên kết lúc</p>
              <p className="text-sm font-medium mt-1">
                {formatDateTime(identity.linked_at)}
              </p>
            </div>
          </div>

          <div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRevoke}
              disabled={revoking}
              className="text-destructive hover:text-destructive"
            >
              <span className="material-symbols-outlined text-sm mr-1">
                link_off
              </span>
              {revoking ? "Đang hủy…" : "Hủy liên kết"}
            </Button>
          </div>
        </div>
      ) : linkCode ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Mở Telegram, chat riêng với CMDSupportBot (hoặc nhắn trong nhóm Squad có bot này), và nhập đúng lệnh dưới đây:
          </p>
          <div className="bg-[#0F2A2A] rounded-lg p-3 font-mono text-sm text-[#FDFFFF] break-all">
            {command}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => handleCopy(command)}>
              <span className="material-symbols-outlined text-sm mr-1">
                {copied ? "check" : "content_copy"}
              </span>
              {copied ? "Đã sao chép!" : "Sao chép lệnh"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleGenerate}
              disabled={generating}
            >
              <span className="material-symbols-outlined text-sm mr-1">refresh</span>
              {generating ? "Đang tạo lại…" : "Tạo mã mới"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Mã hết hạn lúc {formatDateTime(linkCode.expires_at)}.
          </p>
          <p className="text-xs text-muted-foreground">{LINK_INSTRUCTION}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Chưa liên kết tài khoản Telegram.
          </p>
          <Button
            onClick={handleGenerate}
            disabled={generating}
            className="bg-primary text-primary-foreground hover:bg-primary/90 self-start"
          >
            {generating ? "Đang tạo…" : "Tạo mã liên kết"}
          </Button>
        </div>
      )}
    </div>
  );
}
