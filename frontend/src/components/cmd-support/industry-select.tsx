"use client";

import { useState, useEffect } from "react";
import { useCmdOptions, type Industry } from "./use-cmd-options";
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

export function IndustrySelect({ value, onValueChange, disabled }: Props) {
  const { industriesL1, getIndustriesL2, loadingL1 } = useCmdOptions();
  const [l1Code, setL1Code] = useState("");
  const [l2Code, setL2Code] = useState("");
  const [l2List, setL2List] = useState<Industry[]>([]);
  const [loadingL2, setLoadingL2] = useState(false);

  const selectedL1 = industriesL1.find((i) => i.code === l1Code);
  const selectedL2 = l2List.find((i) => i.code === l2Code);

  // When l1Code changes, fetch l2
  useEffect(() => {
    if (!l1Code) {
      setL2List([]);
      setL2Code("");
      return;
    }
    setLoadingL2(true);
    setL2Code("");
    getIndustriesL2(l1Code)
      .then(setL2List)
      .catch(() => setL2List([]))
      .finally(() => setLoadingL2(false));
  }, [l1Code, getIndustriesL2]);

  // Propagate value up: prefer l2Code, else l1Code
  useEffect(() => {
    onValueChange(l2Code || l1Code);
  }, [l1Code, l2Code, onValueChange]);

  return (
    <div className="flex flex-col gap-2">
      {/* Level 1 */}
      <Select
        value={l1Code}
        onValueChange={(v) => setL1Code(v ?? "")}
        disabled={disabled || loadingL1}
      >
        <SelectTrigger className="w-full overflow-hidden bg-background text-base">
          {selectedL1 ? (
            <span className="block min-w-0 flex-1 text-left truncate text-foreground">
              {selectedL1.code} — {selectedL1.name}
            </span>
          ) : (
            <span className="block min-w-0 flex-1 text-left truncate text-muted-foreground">
              {loadingL1 ? "Đang tải…" : "Chọn ngành cấp 1"}
            </span>
          )}
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="">
            <span className="text-muted-foreground">— Không chọn —</span>
          </SelectItem>
          {industriesL1.map((i) => (
            <SelectItem key={i.code} value={i.code}>
              {i.code} — {i.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Level 2 — only show when l1 selected and l2 available */}
      {l1Code && (
        <div className="flex items-center gap-2">
          <Select
            value={l2Code}
            onValueChange={(v) => setL2Code(v ?? "")}
            disabled={disabled || loadingL2}
          >
            <SelectTrigger className="w-full overflow-hidden bg-background text-base">
              {selectedL2 ? (
                <span className="block min-w-0 flex-1 text-left truncate text-foreground">
                  {selectedL2.code} — {selectedL2.name}
                </span>
              ) : (
                <span className="block min-w-0 flex-1 text-left truncate text-muted-foreground">
                  {loadingL2 ? "Đang tải…" : "Chọn ngành cấp 2 (tuỳ chọn)"}
                </span>
              )}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">
                <span className="text-muted-foreground">— Bỏ cấp 2 —</span>
              </SelectItem>
              {l2List.map((i) => (
                <SelectItem key={i.code} value={i.code}>
                  {i.code} — {i.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {l2Code && (
            <button
              type="button"
              onClick={() => setL2Code("")}
              className="shrink-0 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Bỏ cấp 2"
            >
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
