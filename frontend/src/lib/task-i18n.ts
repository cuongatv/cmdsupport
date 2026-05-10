// Vietnamese translations for task state names. The mapping is keyed by the
// lowercased English state name so that case/whitespace variations from seed
// data and user-customised states fall back gracefully. When a state name is
// not recognised the original string is returned unchanged so custom states
// keep their author-defined wording.

const STATE_NAME_TRANSLATIONS: Record<string, string> = {
  backlog: "Chờ xử lý (Backlog)",
  todo: "Cần làm (To Do)",
  "to do": "Cần làm (To Do)",
  "in progress": "Đang thực hiện (In Progress)",
  "in review": "Đang xem xét (In Review)",
  review: "Đang xem xét (In Review)",
  done: "Đã hoàn thành (Done)",
  completed: "Đã hoàn thành (Done)",
  cancelled: "Đã hủy (Cancelled)",
  canceled: "Đã hủy (Cancelled)",
  blocked: "Bị chặn (Blocked)",
  "on hold": "Tạm hoãn (On Hold)",
};

export function translateStateName(name: string | null | undefined): string {
  if (!name) return "";
  const key = name.trim().toLowerCase();
  return STATE_NAME_TRANSLATIONS[key] ?? name;
}
