"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  getTelegramSettings,
  updateTelegramSettings,
} from "@/lib/telegram-api";
import type {
  TelegramIntegrationStatus,
  TelegramSettingsUpdate,
} from "@/lib/telegram-types";
import { PageHeader } from "@/components/shared/page-header";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

function defaultWebhookUrl(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/api/integrations/telegram/webhook`;
}

/**
 * Generate a 32-char url-safe secret using crypto.getRandomValues.
 * 24 random bytes base64url-encoded yield exactly 32 unpadded chars.
 */
function generateWebhookSecret(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) {
    bin += String.fromCharCode(bytes[i]);
  }
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function formatDateTime(value: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("vi-VN");
}

export default function TelegramSettingsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [status, setStatus] = useState<TelegramIntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  // Form state.
  const [isEnabled, setIsEnabled] = useState(false);
  const [botToken, setBotToken] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [botUsername, setBotUsername] = useState("");

  // Dirty tracking — only fields the user edited are sent on Save.
  const [enabledDirty, setEnabledDirty] = useState(false);
  const [tokenDirty, setTokenDirty] = useState(false);
  const [secretDirty, setSecretDirty] = useState(false);
  const [urlDirty, setUrlDirty] = useState(false);
  const [usernameDirty, setUsernameDirty] = useState(false);

  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Admin guard — mirrors /admin/settings/page.tsx.
  useEffect(() => {
    if (user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, router]);

  const applyStatus = useCallback((next: TelegramIntegrationStatus) => {
    setStatus(next);
    setIsEnabled(next.is_enabled);
    // Never echo raw secrets — always start the inputs empty.
    setBotToken("");
    setWebhookSecret("");
    setWebhookUrl(next.webhook_url ?? defaultWebhookUrl());
    setBotUsername(next.bot_username ?? "");
    setEnabledDirty(false);
    setTokenDirty(false);
    setSecretDirty(false);
    setUrlDirty(false);
    setUsernameDirty(false);
  }, []);

  useEffect(() => {
    if (user?.role !== "admin") return;
    let cancelled = false;
    async function load() {
      try {
        const data = await getTelegramSettings();
        if (cancelled) return;
        applyStatus(data);
        setLoadError("");
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof Error
            ? err.message
            : "Không thể tải cài đặt Telegram.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [user, applyStatus]);

  const handleGenerateSecret = () => {
    const next = generateWebhookSecret();
    setWebhookSecret(next);
    setSecretDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveOk(false);
    setSaveError("");
    try {
      const body: TelegramSettingsUpdate = {};
      if (enabledDirty) body.is_enabled = isEnabled;
      if (tokenDirty) {
        const trimmed = botToken.trim();
        body.bot_token = trimmed.length > 0 ? trimmed : null;
      }
      if (secretDirty) {
        const trimmed = webhookSecret.trim();
        body.webhook_secret = trimmed.length > 0 ? trimmed : null;
      }
      if (urlDirty) {
        const trimmed = webhookUrl.trim();
        body.webhook_url = trimmed.length > 0 ? trimmed : null;
      }
      if (usernameDirty) {
        const trimmed = botUsername.trim();
        body.bot_username = trimmed.length > 0 ? trimmed : null;
      }
      if (Object.keys(body).length > 0) {
        await updateTelegramSettings(body);
      }
      const refreshed = await getTelegramSettings();
      applyStatus(refreshed);
      setSaveOk(true);
      window.setTimeout(() => setSaveOk(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  const tokenConfigured = status?.bot_token_configured ?? false;
  const secretConfigured = status?.webhook_secret_configured ?? false;
  const lastSetAt = status?.webhook_last_set_at ?? null;

  return (
    <>
      <PageHeader
        title="Tích hợp Telegram"
        description="Cấu hình bot Telegram của CMD Support: bật/tắt tích hợp, lưu token bot, sinh secret webhook và xem trạng thái webhook."
      />

      {loadError && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2">
          <span className="material-symbols-outlined text-base">error</span>
          {loadError}
        </p>
      )}

      <div className="flex flex-col gap-6">
        {/* Enable / disable */}
        <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary text-base">
                toggle_on
              </span>
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-foreground">
                Trạng thái tích hợp
              </h3>
              <p className="text-xs text-muted-foreground">
                Khi bật, webhook và các lệnh <code className="px-1 rounded bg-muted text-foreground">/task</code>,{" "}
                <code className="px-1 rounded bg-muted text-foreground">/done</code>,{" "}
                <code className="px-1 rounded bg-muted text-foreground">/bind</code>,{" "}
                <code className="px-1 rounded bg-muted text-foreground">/link</code>{" "}
                sẽ được xử lý.
              </p>
            </div>
            <Switch
              checked={isEnabled}
              onCheckedChange={(checked) => {
                setIsEnabled(checked);
                setEnabledDirty(true);
              }}
            />
          </div>
        </div>

        {/* Bot token */}
        <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary text-base">
                key
              </span>
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">
                Bot token
              </h3>
              <p className="text-xs text-muted-foreground">
                Lấy từ @BotFather. Token chỉ được lưu một chiều và không bao giờ hiển thị lại.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-xs">Token mới</Label>
            <Input
              type="password"
              value={botToken}
              onChange={(e) => {
                setBotToken(e.target.value);
                setTokenDirty(true);
              }}
              placeholder="Paste token from BotFather"
              autoComplete="off"
              spellCheck={false}
              className="bg-background"
            />
            {tokenConfigured ? (
              <span className="text-xs text-green-700 dark:text-green-400 inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">
                  check_circle
                </span>
                ✓ Token configured
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">
                Chưa cấu hình token.
              </span>
            )}
            <p className="text-xs text-muted-foreground">
              Nhập token mới để thay thế giá trị đã lưu. Để trống và lưu sẽ giữ nguyên giá trị hiện tại.
            </p>
          </div>
        </div>

        {/* Webhook secret */}
        <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary text-base">
                lock
              </span>
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">
                Webhook secret
              </h3>
              <p className="text-xs text-muted-foreground">
                Telegram gửi giá trị này qua header{" "}
                <code className="px-1 rounded bg-muted text-foreground">
                  X-Telegram-Bot-Api-Secret-Token
                </code>
                .
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-xs">Secret mới</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                type="password"
                value={webhookSecret}
                onChange={(e) => {
                  setWebhookSecret(e.target.value);
                  setSecretDirty(true);
                }}
                placeholder="32 ký tự url-safe"
                autoComplete="off"
                spellCheck={false}
                className="bg-background flex-1"
              />
              <button
                type="button"
                onClick={handleGenerateSecret}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
              >
                <span className="material-symbols-outlined text-base">
                  autorenew
                </span>
                Generate
              </button>
            </div>
            {secretConfigured ? (
              <span className="text-xs text-green-700 dark:text-green-400 inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">
                  check_circle
                </span>
                ✓ Secret configured
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">
                Chưa cấu hình secret.
              </span>
            )}
          </div>
        </div>

        {/* Webhook URL */}
        <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary text-base">
                link
              </span>
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">
                Webhook URL
              </h3>
              <p className="text-xs text-muted-foreground">
                URL công khai mà Telegram gọi tới. Mặc định dùng cùng origin của portal.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-xs">URL</Label>
            <Input
              type="url"
              value={webhookUrl}
              onChange={(e) => {
                setWebhookUrl(e.target.value);
                setUrlDirty(true);
              }}
              placeholder="https://example.com/api/integrations/telegram/webhook"
              className="bg-background"
            />
            {lastSetAt ? (
              <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">
                  schedule
                </span>
                Webhook lần cuối đăng ký: {formatDateTime(lastSetAt)}
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">
                Webhook chưa được đăng ký với Telegram.
              </span>
            )}
          </div>
        </div>

        {/* Bot username */}
        <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary text-base">
                alternate_email
              </span>
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">
                Tên bot
              </h3>
              <p className="text-xs text-muted-foreground">
                Tuỳ chọn — dùng để phân tích lệnh dạng{" "}
                <code className="px-1 rounded bg-muted text-foreground">
                  /cmd@CMDSupportBot
                </code>
                .
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label className="text-xs">Bot username</Label>
            <Input
              value={botUsername}
              onChange={(e) => {
                setBotUsername(e.target.value);
                setUsernameDirty(true);
              }}
              placeholder="CMDSupportBot"
              autoComplete="off"
              spellCheck={false}
              className="bg-background"
            />
          </div>
        </div>

        {/* Save */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="bg-primary text-primary-foreground px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {saving ? "Đang lưu…" : "Lưu cài đặt"}
            </button>
            {saveOk && (
              <span className="text-sm text-green-600 flex items-center gap-1">
                <span className="material-symbols-outlined text-sm filled">
                  check_circle
                </span>
                Đã lưu thành công
              </span>
            )}
          </div>
          {saveError && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2">
              <span className="material-symbols-outlined text-base">error</span>
              {saveError}
            </p>
          )}
        </div>
      </div>
    </>
  );
}
