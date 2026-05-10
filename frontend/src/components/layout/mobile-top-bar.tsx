"use client";

export function MobileTopBar({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <div className="lg:hidden sticky top-0 z-30 bg-background/95 backdrop-blur border-b border-sidebar-border h-14 flex items-center px-3">
      <button
        onClick={onMenuClick}
        className="w-10 h-10 flex items-center justify-center rounded-lg hover:bg-black/[0.04] transition-colors"
        aria-label="Mở menu"
      >
        <span
          className="material-symbols-outlined text-[22px] text-foreground"
          style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 22" }}
        >
          menu
        </span>
      </button>
      <span className="flex-1 text-center text-[15px] font-semibold text-primary font-heading">
        CMD Support
      </span>
      {/* Spacer to balance hamburger */}
      <div className="w-10" />
    </div>
  );
}
