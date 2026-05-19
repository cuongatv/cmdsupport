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
