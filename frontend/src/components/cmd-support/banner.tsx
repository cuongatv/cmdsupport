"use client";

import Image from "next/image";

/**
 * Hero banner for CMD Support pages.
 * Mobile (<md): 2:1 ratio, Desktop (>=md): 1440/180 ratio.
 */
export function CmdSupportBanner() {
  return (
    <>
      {/* Mobile banner — 800x400, ratio 2:1 */}
      <div className="relative w-full overflow-hidden rounded-xl border border-border shadow-sm aspect-[2/1] md:hidden">
        <Image
          src="/banner-mobile.webp"
          alt="CMD Support — Tư vấn khách hàng doanh nghiệp BIDV"
          fill
          priority
          sizes="100vw"
          className="object-cover object-center"
        />
      </div>

      {/* Desktop banner — 1440x180, ratio 8:1 */}
      <div className="hidden md:block relative w-full overflow-hidden rounded-xl border border-border shadow-sm aspect-[1440/180]">
        <Image
          src="/banner-desktop.webp"
          alt="CMD Support — Tư vấn khách hàng doanh nghiệp BIDV"
          fill
          priority
          sizes="(max-width: 1024px) 100vw, 1280px"
          className="object-cover object-center"
        />
      </div>
    </>
  );
}
