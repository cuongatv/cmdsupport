export type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
};

export type Department = {
  id: string;
  name: string;
};

export type Source = {
  id: string;
  title: string;
  file_name?: string;
  source_type?: string;
  status: string;
  progress?: number;
  progress_message?: string;
  page_count?: number;
  wiki_page_count?: number;
  knowledge_type_id?: string;
  knowledge_type_name?: string;
  knowledge_type_color?: string;
  department_ids?: string[];
  department_names?: string[];
  contributed_by_name?: string;
  scope_type?: string;
  scope_id?: string;
  ingestion_pipeline?: "legacy" | "mrp";
  pipeline_strategy?: string | null;
  pipeline_phase?: string | null;
  created_at: string;
  updated_at?: string;
};
