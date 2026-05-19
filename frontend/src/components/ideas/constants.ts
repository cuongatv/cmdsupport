export const STATUS_LABELS: Record<string, string> = {
  new: "Mới",
  reviewing: "Đang xem xét",
  planned: "Đã lên kế hoạch",
  in_progress: "Đang triển khai",
  shipped: "Đã ra mắt",
  declined: "Từ chối",
};

// Inline hex tones because the project doesn't expose `info`/`warning`/`tertiary`
// as Tailwind tokens (see DESIGN.md vs globals.css). Using arbitrary values keeps
// the badge palette consistent with the brand without invading globals.css.
export const STATUS_TONES: Record<string, string> = {
  new: "bg-[#E8F0FA] text-[#2A6FAE] border border-[#2A6FAE]/20",
  reviewing: "bg-[#FBEFD7] text-[#A06A1B] border border-[#E0A23B]/30",
  planned: "bg-secondary text-secondary-foreground border border-primary/20",
  in_progress: "bg-primary/10 text-primary border border-primary/30",
  shipped: "bg-accent text-accent-foreground border border-[#13AE8E]/30",
  declined: "bg-muted text-muted-foreground border border-border",
};

export const CATEGORY_LABELS: Record<string, string> = {
  feature: "Tính năng mới",
  improvement: "Cải tiến",
  bug: "Lỗi",
  ux: "Trải nghiệm",
  other: "Khác",
};
