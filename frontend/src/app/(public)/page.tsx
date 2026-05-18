"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { LoadingLogo } from "@/components/shared/loading-logo";

// Root `/` is an auth-aware redirect:
//   - not authenticated  → /login
//   - authenticated admin → /admin
//   - authenticated other → /me
// The public advisory form lives at /cmd-advisory.
export default function RootRedirectPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    router.replace(user.role === "admin" ? "/admin" : "/me");
  }, [user, loading, router]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <LoadingLogo size="md" label="Đang chuyển hướng…" />
    </div>
  );
}
