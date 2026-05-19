export type AdminIdeaImage = {
  id: string;
  file_name: string | null;
  content_type: string | null;
  size_bytes: number | null;
  url: string | null;
};

export type AdminIdea = {
  id: string;
  contributor_name: string;
  contributor_phone: string | null;
  contributor_email: string | null;
  contributor_department: string | null;
  title: string | null;
  description: string;
  current_pain: string | null;
  expected_benefit: string | null;
  reference_system: string | null;
  category: string;
  status: string;
  admin_notes: string | null;
  created_at: string;
  updated_at: string;
  images: AdminIdeaImage[];
};

export type AdminIdeaList = {
  items: AdminIdea[];
  total: number;
  page: number;
  page_size: number;
};
