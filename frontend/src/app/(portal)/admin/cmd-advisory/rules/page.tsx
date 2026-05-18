"use client";

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProductRulesTab } from "@/components/cmd-support/rules/product-rules-tab";
import { SegmentRulesTab } from "@/components/cmd-support/rules/segment-rules-tab";
import { ProvinceRulesTab } from "@/components/cmd-support/rules/province-rules-tab";

type TabKey = "product" | "segment" | "province";

export default function ConsultingRulesPage() {
  const [tab, setTab] = useState<TabKey>("product");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold font-heading text-foreground">
          Quy tắc tư vấn
        </h1>
        <p className="text-sm text-muted-foreground">
          Cài đặt các quy tắc bổ sung cho prompt tư vấn KHDN. Quy tắc được tự
          động kết hợp với tri thức từ tab Tri thức khi RM tạo phiên tư vấn.
        </p>
      </header>

      <Tabs
        value={tab}
        onValueChange={(value) => {
          if (value === "product" || value === "segment" || value === "province") {
            setTab(value);
          }
        }}
      >
        <TabsList variant="line" className="border-b border-border w-full justify-start gap-4 px-0">
          <TabsTrigger value="product">Theo sản phẩm/chính sách</TabsTrigger>
          <TabsTrigger value="segment">Theo phân khúc khách hàng</TabsTrigger>
          <TabsTrigger value="province">Theo địa bàn</TabsTrigger>
        </TabsList>

        <TabsContent value="product" className="pt-6">
          <ProductRulesTab />
        </TabsContent>
        <TabsContent value="segment" className="pt-6">
          <SegmentRulesTab />
        </TabsContent>
        <TabsContent value="province" className="pt-6">
          <ProvinceRulesTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
