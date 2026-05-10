"use client";

import Image from "next/image";

type Size = "sm" | "md" | "lg";

const SIZE_MAP: Record<Size, number> = {
  sm: 32,
  md: 56,
  lg: 96,
};

type Props = {
  size?: Size;
  label?: string;
};

/**
 * Loading indicator dùng logo BIDV với hiệu ứng pulse.
 * Dùng cho các trạng thái loading toàn trang/màn hình.
 */
export function LoadingLogo({ size = "md", label = "Đang tải…" }: Props) {
  const px = SIZE_MAP[size];
  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <div
        className="animate-pulse"
        style={{ width: px, height: px }}
        aria-hidden="true"
      >
        <Image
          src="/bidv-logo.webp"
          alt="CMD Support"
          width={px}
          height={px}
          priority
          className="object-contain"
        />
      </div>
      {label ? (
        <span className="text-sm text-muted-foreground">{label}</span>
      ) : null}
    </div>
  );
}
