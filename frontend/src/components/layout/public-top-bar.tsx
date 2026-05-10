"use client";

import Link from "next/link";
import Image from "next/image";
import { useAuth } from "@/lib/auth";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useRouter } from "next/navigation";

export function PublicTopBar() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <header className="sticky top-0 z-40 bg-background/95 backdrop-blur border-b border-sidebar-border">
      <div className="h-14 flex items-center justify-between px-4 sm:px-6 lg:px-10 max-w-7xl mx-auto">
        {/* Left: Logo + brand */}
        <Link href="/" className="flex items-center gap-2">
          <Image
            src="/bidv-logo.webp"
            alt="CMD Support"
            width={32}
            height={32}
            priority
            className="shrink-0 rounded-[4px]"
          />
          <span className="text-[16px] font-semibold text-primary font-heading">
            CMD Support
          </span>
        </Link>

        {/* Right: Login or Avatar */}
        {!loading && (
          <>
            {!user ? (
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
                title="Đăng nhập"
              >
                <span
                  className="material-symbols-outlined text-[20px]"
                  style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
                >
                  login
                </span>
                <span className="hidden sm:inline">Đăng nhập</span>
              </Link>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-accent/50 transition-colors cursor-pointer">
                  <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-semibold">
                    {user.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="hidden sm:inline text-sm text-foreground font-medium">
                    {user.name}
                  </span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem onClick={() => router.push("/admin")}>
                    <span className="material-symbols-outlined mr-2 text-base">admin_panel_settings</span>
                    Vào trang quản trị
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleLogout} className="text-destructive">
                    <span className="material-symbols-outlined mr-2 text-base">logout</span>
                    Đăng xuất
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </>
        )}
      </div>
    </header>
  );
}
