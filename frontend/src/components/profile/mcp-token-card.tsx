"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function McpTokenCard() {
  const [token, setToken] = useState<string | null>(null);
  const [hasToken, setHasToken] = useState(false);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Check if user already has a token on mount
  useEffect(() => {
    api<{ has_token: boolean }>("/api/my/mcp-token/status")
      .then((data) => setHasToken(data.has_token))
      .catch(() => {});
  }, []);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const data = await api<{ token: string }>("/api/my/mcp-token", {
        method: "POST",
      });
      setToken(data.token);
      setHasToken(true);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async () => {
    if (!confirm("Thu hồi MCP token? Claude Desktop sẽ ngắt kết nối.")) return;
    try {
      await api("/api/my/mcp-token", { method: "DELETE" });
      setToken(null);
      setHasToken(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed");
    }
  };

  const handleCopy = () => {
    if (!token) return;
    navigator.clipboard.writeText(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-surface-variant rounded-xl p-6 border border-border">
      <div className="flex items-center gap-3 mb-3">
        <span className="material-symbols-outlined text-primary">vpn_key</span>
        <div>
          <h3 className="text-lg font-semibold text-foreground">
            MCP Token
          </h3>
          <p className="text-xs text-muted-foreground">
            Kết nối Claude Desktop với CMD Support
          </p>
        </div>
      </div>

      {token ? (
        /* Token was just generated — show it */
        <div className="flex flex-col gap-3">
          <div className="bg-[#0F2A2A] rounded-lg p-3 font-mono text-xs text-[#FDFFFF] break-all">
            {token}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleCopy}>
              <span className="material-symbols-outlined text-sm mr-1">
                {copied ? "check" : "content_copy"}
              </span>
              {copied ? "Đã sao chép!" : "Sao chép Token"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRevoke}
              className="text-destructive hover:text-destructive"
            >
              <span className="material-symbols-outlined text-sm mr-1">
                vpn_key_off
              </span>
              Thu hồi
            </Button>
          </div>
        </div>
      ) : hasToken ? (
        /* User has a token but we don't show the value (security) */
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 px-4 py-3 rounded-lg border border-green-200">
            <span className="material-symbols-outlined text-base">check_circle</span>
            <span>MCP Token đang hoạt động. Token đã được hiển thị khi tạo — không thể lấy lại vì lý do bảo mật.</span>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleGenerate}
              disabled={loading}
              variant="outline"
              size="sm"
            >
              <span className="material-symbols-outlined text-sm mr-1">refresh</span>
              {loading ? "Đang tạo lại…" : "Tạo lại Token"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRevoke}
              className="text-destructive hover:text-destructive"
            >
              <span className="material-symbols-outlined text-sm mr-1">
                vpn_key_off
              </span>
              Thu hồi
            </Button>
          </div>
        </div>
      ) : (
        /* No token at all */
        <Button
          onClick={handleGenerate}
          disabled={loading}
          className="bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {loading ? "Đang tạo…" : "Tạo MCP Token"}
        </Button>
      )}
    </div>
  );
}
