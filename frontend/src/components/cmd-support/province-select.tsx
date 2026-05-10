"use client";

import { useCmdOptions } from "./use-cmd-options";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";

type Props = {
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
};

export function ProvinceSelect({ value, onValueChange, disabled }: Props) {
  const { provinces, loadingProvinces } = useCmdOptions();
  const selected = provinces.find((p) => p.code === value);

  return (
    <Select
      value={value}
      onValueChange={(v) => onValueChange(v ?? "")}
      disabled={disabled || loadingProvinces}
    >
      <SelectTrigger className="w-full overflow-hidden bg-background text-base">
        {selected ? (
          <span className="block min-w-0 flex-1 text-left truncate text-foreground">
            {selected.short_name}
          </span>
        ) : (
          <span className="block min-w-0 flex-1 text-left truncate text-muted-foreground">
            {loadingProvinces ? "Đang tải…" : "Chọn tỉnh/thành phố"}
          </span>
        )}
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="">
          <span className="text-muted-foreground">— Không chọn —</span>
        </SelectItem>
        {provinces.map((p) => (
          <SelectItem key={p.code} value={p.code}>
            {p.short_name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
