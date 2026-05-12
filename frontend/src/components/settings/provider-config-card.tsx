"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const BASE_PROVIDERS = [
  { value: "google", label: "Google (Gemini)" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "wtboss", label: "WTBoss AI Gateway" },
];

type Capability = "embedding" | "llm" | "advisor-llm" | "vision";

type TestResult = { success: boolean; message: string };

type Props = {
  title: string;
  description: string;
  icon: string;
  capability?: Capability;
  provider: string;
  model: string;
  apiKey: string;
  onProviderChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onApiKeyChange: (value: string) => void;
};

export function ProviderConfigCard({
  title,
  description,
  icon,
  capability = "embedding",
  provider,
  model,
  apiKey,
  onProviderChange,
  onModelChange,
  onApiKeyChange,
}: Props) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // If the key is the masked placeholder from the server, omit it so the
      // backend falls back to the saved API key. Otherwise send the user's
      // current input (works for both freshly typed keys and unsaved edits).
      const body: Record<string, string> = {};
      if (provider) body.provider = provider;
      if (model) body.model_id = model;
      if (apiKey && !apiKey.includes("•")) body.api_key = apiKey;

      const res = await api<TestResult>(`/api/settings/test-${capability}`, {
        method: "POST",
        body,
      });
      setTestResult(res);
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : "Kiểm tra thất bại",
      });
    } finally {
      setTesting(false);
    }
  };
  // Anthropic không cung cấp embedding API → ẩn ở card embedding.
  const providerOptions =
    capability === "embedding"
      ? BASE_PROVIDERS.filter((p) => p.value !== "anthropic")
      : BASE_PROVIDERS;

  const modelPlaceholder =
    provider === "openrouter"
      ? "VD: openai/gpt-4o-mini"
      : provider === "wtboss"
      ? "VD: warp/claude-opus-4-7"
      : capability === "embedding"
      ? "VD: text-embedding-004"
      : capability === "vision"
      ? "VD: gpt-4o-mini"
      : "VD: gpt-4o-mini";

  const keyPlaceholder =
    provider === "openrouter"
      ? "sk-or-..."
      : provider === "wtboss"
      ? "wtboss-api-key..."
      : "sk-...";

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">
            {icon}
          </span>
        </div>
        <div>
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Nhà cung cấp</Label>
          <Select value={provider} onValueChange={(v) => v && onProviderChange(v)}>
            <SelectTrigger className="bg-background">
              <SelectValue placeholder="Chọn nhà cung cấp" />
            </SelectTrigger>
            <SelectContent>
              {providerOptions.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Model ID</Label>
          <Input
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            placeholder={modelPlaceholder}
            className="bg-background"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">API Key</Label>
          <Input
            type={apiKey.includes("•") ? "text" : "password"}
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            onFocus={() => {
              if (apiKey.includes("•")) onApiKeyChange("");
            }}
            placeholder={keyPlaceholder}
            className="bg-background"
          />
        </div>
      </div>

      {provider === "openrouter" && (
        <p className="mt-3 text-xs text-muted-foreground">
          OpenRouter dùng định dạng model{" "}
          <code className="px-1 py-0.5 rounded bg-muted text-foreground">
            nhà_cung_cấp/tên_model
          </code>
          . Xem danh sách model tại{" "}
          <a
            href="https://openrouter.ai/models"
            target="_blank"
            rel="noopener noreferrer"
            className="underline text-primary"
          >
            openrouter.ai/models
          </a>
          .
        </p>
      )}

      {provider === "wtboss" && (
        <p className="mt-3 text-xs text-muted-foreground">
          WTBoss AI Gateway: endpoint{" "}
          <code className="px-1 py-0.5 rounded bg-muted text-foreground">
            https://xai.wtboss.com/v1
          </code>
          . Định dạng model{" "}
          <code className="px-1 py-0.5 rounded bg-muted text-foreground">
            warp/&lt;tên&gt;
          </code>{" "}
          hoặc{" "}
          <code className="px-1 py-0.5 rounded bg-muted text-foreground">
            boss/&lt;tên&gt;
          </code>
          . Hỗ trợ Claude Opus/Sonnet, GPT 5.x, OPS Max.
        </p>
      )}

      <div className="mt-4 flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing || !provider || !model}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span
              className={`material-symbols-outlined text-base ${
                testing ? "animate-spin" : ""
              }`}
            >
              {testing ? "progress_activity" : "wifi_tethering"}
            </span>
            {testing ? "Đang kiểm tra…" : "Kiểm tra API"}
          </button>
          {!provider || !model ? (
            <span className="text-xs text-muted-foreground">
              Chọn nhà cung cấp và Model ID để kiểm tra.
            </span>
          ) : null}
        </div>
        {testResult && (
          <p
            className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
              testResult.success
                ? "bg-green-500/10 text-green-700 dark:text-green-400"
                : "bg-destructive/10 text-destructive"
            }`}
          >
            <span className="material-symbols-outlined text-sm">
              {testResult.success ? "check_circle" : "error"}
            </span>
            <span className="break-all">{testResult.message}</span>
          </p>
        )}
      </div>
    </div>
  );
}
