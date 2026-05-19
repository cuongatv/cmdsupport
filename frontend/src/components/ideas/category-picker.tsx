"use client";

import { cn } from "@/lib/utils";

export type IdeaCategory = "feature" | "improvement" | "bug" | "ux" | "other";

const CATEGORIES: {
  value: IdeaCategory;
  label: string;
  description: string;
  icon: string;
}[] = [
  {
    value: "feature",
    label: "Tính năng mới",
    description: "Đề xuất chức năng chưa có trong hệ thống",
    icon: "auto_awesome",
  },
  {
    value: "improvement",
    label: "Cải tiến",
    description: "Nâng cấp, tối ưu phần đã có",
    icon: "trending_up",
  },
  {
    value: "ux",
    label: "Trải nghiệm",
    description: "Giao diện, thao tác, luồng sử dụng",
    icon: "design_services",
  },
  {
    value: "bug",
    label: "Lỗi / Vấn đề",
    description: "Báo cáo lỗi hoặc hành vi sai",
    icon: "bug_report",
  },
  {
    value: "other",
    label: "Khác",
    description: "Ý tưởng không thuộc các loại trên",
    icon: "lightbulb",
  },
];

export function CategoryPicker({
  value,
  onChange,
  disabled,
}: {
  value: IdeaCategory;
  onChange: (v: IdeaCategory) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      {CATEGORIES.map((cat) => {
        const active = value === cat.value;
        return (
          <button
            key={cat.value}
            type="button"
            onClick={() => onChange(cat.value)}
            disabled={disabled}
            className={cn(
              "group relative flex flex-col items-start text-left rounded-xl border p-3 transition-all duration-150",
              "hover:border-primary/60 hover:shadow-sm",
              active
                ? "border-primary bg-primary/[0.06] ring-1 ring-primary/40 shadow-sm"
                : "border-border bg-card",
              disabled && "opacity-50 cursor-not-allowed"
            )}
          >
            <div
              className={cn(
                "w-9 h-9 rounded-lg flex items-center justify-center mb-2",
                active
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground group-hover:bg-primary/15"
              )}
            >
              <span
                className="material-symbols-outlined text-[20px]"
                style={{
                  fontVariationSettings: active
                    ? "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 20"
                    : "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20",
                }}
              >
                {cat.icon}
              </span>
            </div>
            <span className="text-sm font-semibold leading-tight">
              {cat.label}
            </span>
            <span className="text-[11px] text-muted-foreground leading-snug mt-0.5">
              {cat.description}
            </span>
          </button>
        );
      })}
    </div>
  );
}
