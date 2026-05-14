"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const loggedInUser = await login(email, password);
      router.push(loggedInUser.role === "admin" ? "/admin" : "/me");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md px-8">
        {/* Brand */}
        <div className="flex flex-col items-center text-center mb-10">
          <Image
            src="/bidv-logo.webp"
            alt="CMD Support"
            width={72}
            height={72}
            priority
            className="mb-4"
          />
          <h1 className="text-5xl tracking-tight text-foreground mb-2">
            CMD Support
          </h1>
          <p className="text-muted-foreground text-sm">
            Trợ lý tư vấn khách hàng doanh nghiệp BIDV
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-card rounded-xl border border-border shadow-sahara p-8">
          <h2 className="text-2xl text-foreground mb-6">Đăng nhập</h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email" className="text-sm font-medium">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="admin@cmdsupport.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="bg-background"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="password" className="text-sm font-medium">
                Mật khẩu
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="Nhập mật khẩu"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="bg-background"
              />
            </div>

            {error && (
              <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">
                {error}
              </p>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full bg-primary hover:bg-primary/90 text-primary-foreground mt-2"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined animate-spin text-base">
                    progress_activity
                  </span>
                    Đang đăng nhập…
                </span>
              ) : (
                "Đăng nhập"
              )}
            </Button>
          </form>
        </div>

        <div className="text-center mt-6 space-y-1">
          <p className="text-xs text-muted-foreground">
            CMD Support — Phiên bản Pilot
          </p>
          <p className="text-[11px] text-muted-foreground/70">
            Hệ thống nội bộ BIDV. Truy cập có ghi log.
          </p>
        </div>
      </div>
    </div>
  );
}
