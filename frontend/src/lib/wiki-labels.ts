import { WikiPageType } from "@/types/wiki";

export const WIKI_PAGE_TYPE_LABEL_VI: Record<WikiPageType, string> = {
  entity: "Đối tượng nghiệp vụ",
  concept: "Khái niệm / Thuật ngữ",
  topic: "Chủ đề nghiệp vụ",
  source: "Nguồn tài liệu",
  index: "Mục lục / Chỉ mục",
  log: "Nhật ký",
};

export function getWikiPageTypeLabel(type: WikiPageType): string {
  return WIKI_PAGE_TYPE_LABEL_VI[type];
}

// ----------------------------------------------------------------------------
// BIDV KHDN taxonomy (17 slugs) — Vietnamese labels.
// SOURCE OF TRUTH: alembic/versions/037_seed_wiki_taxonomy.py
// Strings here MUST match the migration verbatim.
// ----------------------------------------------------------------------------

export type WikiTaxonomyGroup = "business_object" | "supporting_knowledge" | "unknown";

export const WIKI_TAXONOMY_LABEL_VI: Record<string, string> = {
  // business_object.* (12)
  "business_object.product_service": "Sản phẩm & dịch vụ",
  "business_object.target_customer": "Khách hàng mục tiêu / phân khúc",
  "business_object.non_credit_development_tool":
    "Công cụ phát triển khách hàng phi tín dụng",
  "business_object.credit_development_tool":
    "Công cụ phát triển khách hàng tín dụng",
  "business_object.campaign_program": "Chiến dịch / chương trình thúc đẩy",
  "business_object.policy_mechanism": "Cơ chế / chính sách",
  "business_object.eligibility_condition": "Điều kiện / tiêu chí áp dụng",
  "business_object.process_form": "Quy trình / hồ sơ / biểu mẫu",
  "business_object.risk_compliance": "Rủi ro / tuân thủ",
  "business_object.industry_segment": "Ngành nghề / lĩnh vực kinh doanh",
  "business_object.region_channel": "Địa bàn / kênh phân phối",
  "business_object.other": "Đối tượng nghiệp vụ khác",
  // supporting_knowledge.* (5)
  "supporting_knowledge.general_context": "Bối cảnh / thông tin nền",
  "supporting_knowledge.term_explanation": "Giải thích thuật ngữ",
  "supporting_knowledge.operational_guidance":
    "Hướng dẫn vận hành / hướng dẫn đọc tài liệu",
  "supporting_knowledge.source_background": "Thông tin nguồn / xuất xứ tài liệu",
  "supporting_knowledge.other": "Kiến thức bổ trợ khác",
};

export const WIKI_TAXONOMY_GROUP_LABEL_VI: Record<
  Exclude<WikiTaxonomyGroup, "unknown">,
  string
> = {
  business_object: "Đối tượng nghiệp vụ",
  supporting_knowledge: "Kiến thức bổ trợ / Khác",
};

export function getWikiTaxonomyLabel(slug: string): string {
  return WIKI_TAXONOMY_LABEL_VI[slug] ?? slug;
}

export function getWikiTaxonomyGroup(slug: string): WikiTaxonomyGroup {
  if (slug.startsWith("business_object.")) return "business_object";
  if (slug.startsWith("supporting_knowledge.")) return "supporting_knowledge";
  return "unknown";
}
