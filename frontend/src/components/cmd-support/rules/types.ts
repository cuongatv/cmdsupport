export type RuleUserBrief = { id: string; name: string };

export type ProductRule = {
  id: string;
  wiki_page_id: string | null;
  wiki_page_title: string | null;
  wiki_page_slug: string | null;
  product_name_custom: string | null;
  basic_info: string | null;
  customer_persona: string;
  created_by: RuleUserBrief | null;
  updated_by: RuleUserBrief | null;
  created_at: string;
  updated_at: string;
};

export type SegmentRule = {
  id: string;
  segment: string;
  basic_info: string | null;
  segment_specifics: string;
  created_by: RuleUserBrief | null;
  updated_by: RuleUserBrief | null;
  created_at: string;
  updated_at: string;
};

export type ProvinceRule = {
  id: string;
  province_id: string;
  province_name: string | null;
  province_code: string | null;
  basic_info: string | null;
  province_specifics: string;
  created_by: RuleUserBrief | null;
  updated_by: RuleUserBrief | null;
  created_at: string;
  updated_at: string;
};

export type WikiSourceItem = {
  id: string;
  slug: string;
  title: string;
  knowledge_type_slugs: string[];
};

export type KnowledgeTypeOption = {
  slug: string;
  name: string;
  color: string | null;
};

export type AiAssistResponse = { generated_text: string };
