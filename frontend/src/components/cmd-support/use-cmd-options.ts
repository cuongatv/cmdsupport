"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

export type Province = {
  code: string;
  name: string;
  short_name: string;
  type: string;
  region: string;
  sort_order: number;
};

export type Industry = {
  code: string;
  name: string;
  level: number;
  parent_code: string | null;
  sort_order: number;
};

let cachedProvinces: Province[] | null = null;
let cachedIndustriesL1: Industry[] | null = null;
const cachedIndustriesL2: Record<string, Industry[]> = {};

export function useCmdOptions() {
  const [provinces, setProvinces] = useState<Province[]>(cachedProvinces ?? []);
  const [industriesL1, setIndustriesL1] = useState<Industry[]>(cachedIndustriesL1 ?? []);
  const [loadingProvinces, setLoadingProvinces] = useState(!cachedProvinces);
  const [loadingL1, setLoadingL1] = useState(!cachedIndustriesL1);

  useEffect(() => {
    if (!cachedProvinces) {
      api<Province[]>("/api/cmd-support/options/provinces")
        .then((data) => {
          cachedProvinces = data;
          setProvinces(data);
        })
        .catch(() => {})
        .finally(() => setLoadingProvinces(false));
    }
    if (!cachedIndustriesL1) {
      api<Industry[]>("/api/cmd-support/options/industries?level=1")
        .then((data) => {
          cachedIndustriesL1 = data;
          setIndustriesL1(data);
        })
        .catch(() => {})
        .finally(() => setLoadingL1(false));
    }
  }, []);

  const getIndustriesL2 = useCallback(async (parentCode: string): Promise<Industry[]> => {
    if (cachedIndustriesL2[parentCode]) return cachedIndustriesL2[parentCode];
    const data = await api<Industry[]>(`/api/cmd-support/options/industries?level=2&parent_code=${parentCode}`);
    cachedIndustriesL2[parentCode] = data;
    return data;
  }, []);

  return { provinces, industriesL1, getIndustriesL2, loadingProvinces, loadingL1 };
}
