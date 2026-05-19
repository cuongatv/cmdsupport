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
  // `identifier` accepts either a username or an email — the backend
  // resolves both. Naming the state `identifier` (not `email`) avoids
  // leaking the previous assumption that email is the only login handle.
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const loggedInUser = await login(identifier, password);
      router.push(loggedInUser.role === "admin" ? "/admin" : "/me");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Scoped keyframes — React 19 hoists <style> to <head> automatically.
          All animations operate on transform / opacity / filter only (no layout thrash). */}
      <style>{`
        @keyframes login-drift-a {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50%      { transform: translate3d(40px, -30px, 0) scale(1.12); }
        }
        @keyframes login-drift-b {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50%      { transform: translate3d(-50px, 40px, 0) scale(0.92); }
        }
        @keyframes login-drift-c {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50%      { transform: translate3d(30px, 50px, 0) scale(1.08); }
        }
        @keyframes login-shimmer {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
        @keyframes login-logo-glow {
          0%, 100% { filter: drop-shadow(0 0 0 rgba(19, 174, 142, 0)); }
          50%      { filter: drop-shadow(0 0 22px rgba(19, 174, 142, 0.45)) drop-shadow(0 0 12px rgba(255, 198, 47, 0.30)); }
        }
        @keyframes login-drift-d {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50%      { transform: translate3d(-30px, -40px, 0) scale(1.10); }
        }
        .login-aurora-d   { animation: login-drift-d 26s ease-in-out infinite; }
        .login-aurora-a   { animation: login-drift-a 22s ease-in-out infinite; }
        .login-aurora-b   { animation: login-drift-b 28s ease-in-out infinite; }
        .login-aurora-c   { animation: login-drift-c 32s ease-in-out infinite; }
        .login-shimmer    { animation: login-shimmer 4s linear infinite; }
        .login-logo-glow  { animation: login-logo-glow 6s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .login-aurora-a,
          .login-aurora-b,
          .login-aurora-c,
          .login-aurora-d,
          .login-shimmer,
          .login-logo-glow { animation: none; }
        }
      `}</style>

      <div className="relative min-h-screen overflow-hidden bg-background">
        {/* Layer 1 — Soft mesh gradient base */}
        <div
          aria-hidden
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 15% 20%, rgba(0,107,104,0.20), transparent 60%), radial-gradient(ellipse 70% 60% at 85% 80%, rgba(19,174,142,0.18), transparent 60%), radial-gradient(ellipse 100% 80% at 50% 50%, rgba(230,243,242,0.55), transparent 70%)",
          }}
        />

        {/* Layer 2 — Drifting aurora blobs */}
        <div aria-hidden className="absolute inset-0 overflow-hidden">
          <div
            className="login-aurora-a absolute -top-32 -left-24 h-[40rem] w-[40rem] rounded-full opacity-60 max-lg:opacity-30 blur-3xl will-change-transform"
            style={{
              background:
                "radial-gradient(circle at 30% 30%, #13AE8E, transparent 70%)",
            }}
          />
          <div
            className="login-aurora-b absolute top-1/3 -right-32 h-[36rem] w-[36rem] rounded-full opacity-55 max-lg:opacity-30 blur-3xl will-change-transform"
            style={{
              background:
                "radial-gradient(circle at 70% 50%, #006B68, transparent 70%)",
            }}
          />
          <div
            className="login-aurora-c absolute -bottom-40 left-1/4 h-[34rem] w-[34rem] rounded-full opacity-45 blur-3xl will-change-transform max-lg:hidden"
            style={{
              background:
                "radial-gradient(circle at 50% 50%, #7BC9C0, transparent 70%)",
            }}
          />
          {/* Gold accent blob — supporting brand color #FFC62F */}
          <div
            className="login-aurora-d absolute top-10 right-1/4 h-[28rem] w-[28rem] rounded-full opacity-30 blur-3xl will-change-transform max-lg:hidden"
            style={{
              background:
                "radial-gradient(circle at 50% 50%, #FFC62F, transparent 70%)",
            }}
          />
        </div>

        {/* Layer 2.5 — Mobile-only soft vignette: floats the card in airy space */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 lg:hidden"
          style={{
            background:
              "linear-gradient(to bottom, rgba(253,255,255,0.92) 0%, rgba(253,255,255,0) 22%, rgba(253,255,255,0) 78%, rgba(253,255,255,0.92) 100%)",
          }}
        />

        {/* Layer 3 — SVG noise / grain for subtle texture */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.04] mix-blend-multiply"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
          }}
        />

        {/* Foreground content */}
        <div className="relative z-10 grid min-h-screen grid-cols-1 lg:grid-cols-[1.1fr_0.9fr]">
          {/* Brand showcase — desktop only */}
          <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden p-12 xl:p-16">
            {/* Decorative grid lines */}
            <div
              aria-hidden
              className="absolute inset-0 opacity-[0.07]"
              style={{
                backgroundImage:
                  "linear-gradient(to right, #006B68 1px, transparent 1px), linear-gradient(to bottom, #006B68 1px, transparent 1px)",
                backgroundSize: "48px 48px",
                maskImage:
                  "radial-gradient(ellipse 80% 60% at 30% 50%, black, transparent 70%)",
                WebkitMaskImage:
                  "radial-gradient(ellipse 80% 60% at 30% 50%, black, transparent 70%)",
              }}
            />

            {/* Top — logo + label */}
            <div className="relative z-10 animate-in fade-in slide-in-from-left-8 duration-700">
              <div className="flex items-center gap-3">
                <div className="login-logo-glow">
                  <Image
                    src="/bidv-logo.webp"
                    alt="CMD Support"
                    width={56}
                    height={56}
                    priority
                  />
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">
                    CMD Support
                  </p>
                </div>
              </div>
            </div>

            {/* Middle — headline + tagline */}
            <div className="relative z-10 animate-in fade-in slide-in-from-left-8 duration-700 delay-150">
              <h1 className="text-6xl xl:text-7xl font-bold tracking-tight leading-[1.05]">
                <span className="text-foreground">CMD</span>{" "}
                <span className="bg-gradient-to-br from-[#006B68] via-[#13AE8E] to-[#FFC62F] bg-clip-text text-transparent">
                  Support
                </span>
              </h1>
              <p className="mt-5 max-w-md text-lg leading-relaxed text-foreground/70">
                Nền tảng tối ưu quản lý công việc, ứng dụng AI và kết nối tri
                thức.
              </p>

              {/* Feature pills */}
              <div className="mt-8 flex flex-wrap gap-2">
                {[
                  "Tối ưu quản lý công việc",
                  "Trợ lý AI",
                  "Kết nối tri thức",
                ].map((tag, idx) => (
                  <span
                    key={tag}
                    className={
                      idx === 1
                        ? "rounded-full border border-[#FFC62F]/40 bg-[#FFC62F]/10 px-3.5 py-1.5 text-xs font-medium text-[#8a6a10] shadow-sm backdrop-blur-md"
                        : "rounded-full border border-primary/15 bg-white/60 px-3.5 py-1.5 text-xs font-medium text-primary shadow-sm backdrop-blur-md"
                    }
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            {/* Bottom — status pill */}
            <div className="relative z-10 animate-in fade-in slide-in-from-left-8 duration-700 delay-300">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="size-1.5 rounded-full bg-[#13AE8E] animate-pulse" />
                Hệ thống nội bộ · Truy cập có ghi log
              </div>
            </div>
          </aside>

          {/* Login form panel */}
          <main className="relative flex items-center justify-center px-6 py-14 sm:p-10 lg:p-12">
            <div className="w-full max-w-md max-lg:max-w-sm animate-in fade-in zoom-in-95 slide-in-from-bottom-4 duration-500">
              {/* Mobile brand (only <lg) */}
              <div className="mb-10 flex flex-col items-center text-center gap-3 lg:hidden">
                <div className="login-logo-glow">
                  <Image
                    src="/bidv-logo.webp"
                    alt="CMD Support"
                    width={48}
                    height={48}
                    priority
                  />
                </div>
                <h1 className="text-3xl font-semibold tracking-tight">
                  <span className="text-foreground">CMD</span>{" "}
                  <span className="bg-gradient-to-br from-[#006B68] via-[#13AE8E] to-[#FFC62F] bg-clip-text text-transparent">
                    Support
                  </span>
                </h1>
                <p className="text-[13px] tracking-wide text-muted-foreground/80">
                  Tối ưu quản lý công việc · Trợ lý AI · Kết nối tri thức
                </p>
              </div>

              {/* Glassmorphism card with gradient halo */}
              <div className="relative">
                <div
                  aria-hidden
                  className="absolute -inset-px rounded-2xl max-lg:rounded-3xl bg-gradient-to-br from-[#006B68]/40 via-[#13AE8E]/25 to-[#FFC62F]/35 opacity-60 max-lg:opacity-40 blur-md"
                />
                <div className="relative overflow-hidden rounded-2xl max-lg:rounded-3xl border border-white/60 max-lg:border-white/50 bg-white/70 p-8 shadow-[0_20px_60px_-15px_rgba(0,107,104,0.25)] max-lg:shadow-[0_8px_30px_-12px_rgba(0,107,104,0.18)] backdrop-blur-xl">
                  {/* Shimmer accent on top edge */}
                  <div
                    aria-hidden
                    className="pointer-events-none absolute inset-x-0 top-0 h-px overflow-hidden"
                  >
                    <div className="login-shimmer h-full w-1/3 bg-gradient-to-r from-transparent via-[#FFC62F] to-transparent" />
                  </div>

                  <div className="mb-6 max-lg:mb-7">
                    <h2 className="text-2xl font-bold text-foreground max-lg:text-xl max-lg:font-semibold">
                      Đăng nhập
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground max-lg:mt-1.5">
                      Vui lòng nhập thông tin tài khoản của bạn
                    </p>
                  </div>

                  <form onSubmit={handleSubmit} className="flex flex-col gap-5 max-lg:gap-6">
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="identifier" className="text-sm font-medium">
                        Tên đăng nhập hoặc Email
                      </Label>
                      <Input
                        id="identifier"
                        type="text"
                        placeholder="vd: admin hoặc admin@cmdsupport.com"
                        value={identifier}
                        onChange={(e) => setIdentifier(e.target.value)}
                        required
                        autoFocus
                        autoComplete="username"
                        className="h-11 bg-white/70 backdrop-blur-sm"
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
                        className="h-11 bg-white/70 backdrop-blur-sm"
                      />
                    </div>

                    {error && (
                      <p className="animate-in fade-in slide-in-from-top-1 duration-200 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                        {error}
                      </p>
                    )}

                    <Button
                      type="submit"
                      disabled={loading}
                      className="group/cta relative mt-2 h-11 w-full overflow-hidden bg-primary text-primary-foreground transition-all hover:-translate-y-px hover:shadow-lg hover:shadow-primary/30"
                    >
                      <span
                        aria-hidden
                        className="absolute inset-0 bg-gradient-to-r from-[#006B68] via-[#13AE8E] to-[#006B68] bg-[length:200%_100%] bg-left opacity-0 transition-all duration-500 group-hover/cta:bg-right group-hover/cta:opacity-100"
                      />
                      <span className="relative">
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
                      </span>
                    </Button>
                  </form>
                </div>
              </div>

              {/* Footer disclaimer */}
              <div className="mt-6 space-y-1 max-lg:mt-10 max-lg:space-y-2 text-center animate-in fade-in duration-700 delay-300">
                <p className="text-xs text-muted-foreground max-lg:text-[10px] max-lg:uppercase max-lg:tracking-[0.22em] max-lg:text-muted-foreground/70">
                  CMD Support — Phiên bản Pilot
                </p>
                <p className="text-[11px] text-muted-foreground/70 lg:hidden max-lg:tracking-wide">
                  Hệ thống nội bộ · Truy cập có ghi log
                </p>
              </div>
            </div>
          </main>
        </div>
      </div>
    </>
  );
}
