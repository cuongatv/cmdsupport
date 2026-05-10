"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";

export const CUSTOMER_SEGMENTS = [
  { value: "sme", label: "SME (Doanh nghiệp nhỏ và vừa)" },
  { value: "midcom", label: "Midcom (Doanh nghiệp trung lớn)" },
  { value: "public_admin", label: "Hành chính sự nghiệp" },
] as const;

export type CustomerSegmentValue = (typeof CUSTOMER_SEGMENTS)[number]["value"];

export const SEGMENT_SHORT_LABEL: Record<string, string> = {
  sme: "SME",
  midcom: "Midcom",
  public_admin: "Hành chính sự nghiệp",
};

type Props = {
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
};

export function SegmentSelect({ value, onValueChange, disabled }: Props) {
  const current = value || "sme";
  const selected = CUSTOMER_SEGMENTS.find((s) => s.value === current);

  return (
    <Select
      value={current}
      onValueChange={(v) => v && onValueChange(v)}
      disabled={disabled}
    >
      <SelectTrigger className="w-full overflow-hidden bg-background text-base">
        {selected ? (
          <span className="block min-w-0 flex-1 text-left truncate text-foreground">
            {selected.label}
          </span>
        ) : (
          <span className="block min-w-0 flex-1 text-left truncate text-muted-foreground">
            Chọn phân khúc khách hàng
          </span>
        )}
      </SelectTrigger>
      <SelectContent>
        {CUSTOMER_SEGMENTS.map((s) => (
          <SelectItem key={s.value} value={s.value}>
            {s.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
