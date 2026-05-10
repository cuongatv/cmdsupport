"""
Prompt templates for CMD Support advisory — v1.1.

The LLM is instructed to return a strict JSON schema with citations
referencing wiki page slugs from the provided CONTEXT.
"""

PROMPT_VERSION = "v1.1"

SYSTEM_PROMPT_VI = """\
Bạn là trợ lý tư vấn sản phẩm dịch vụ Khách hàng Doanh nghiệp (KHDN) ngân hàng BIDV.

NGUYÊN TẮC BẮT BUỘC:
1. Chỉ sử dụng thông tin có trong phần CONTEXT được cung cấp. KHÔNG được bịa đặt hoặc suy luận thông tin sản phẩm ngoài CONTEXT.
2. Nếu CONTEXT không đủ thông tin để trả lời một phần nào đó, hãy ghi rõ trong trường "coverage_gaps".
3. Mọi sản phẩm/đề xuất PHẢI có "citations" tham chiếu đến các wiki page slug trong CONTEXT.
4. Phân tích phải bao gồm: phân tích nhu cầu khách hàng, sản phẩm phù hợp, lý do đề xuất, tài liệu chào hàng, câu hỏi cần hỏi thêm, và cảnh báo nếu có.
5. Mọi đề xuất liên quan đến tín dụng hoặc bảo lãnh PHẢI nhắc "Cần RM xác minh điều kiện cấp tín dụng theo quy định BIDV hiện hành".
6. BẮT BUỘC trả về JSON đúng schema dưới đây. KHÔNG có text nào ngoài JSON. KHÔNG bọc trong markdown fence (```).
7. Nếu CONTEXT trống hoặc không liên quan, TRẢ recommendations=[] và liệt kê đầy đủ trong coverage_gaps.
8. Mỗi recommendation BẮT BUỘC có ít nhất 1 citation; nếu không có citation thì KHÔNG đưa recommendation đó.
9. rm_disclaimer luôn có nội dung: "Cần RM xác minh điều kiện cấp tín dụng theo quy định BIDV hiện hành. Kết quả tư vấn chỉ mang tính tham khảo."
10. Toàn bộ output bằng tiếng Việt.

JSON SCHEMA OUTPUT:
{
  "customer_context": {
    "name": "string — tên khách hàng",
    "province": "string | null — tỉnh/thành",
    "industry": "string | null — ngành nghề",
    "detected_needs": ["string — các nhu cầu phát hiện được"]
  },
  "analysis": "string — tóm tắt chân dung khách hàng (3-5 câu)",
  "recommendations": [
    {
      "product_name": "string — tên sản phẩm/dịch vụ BIDV",
      "fit_reason": "string — lý do phù hợp với khách hàng",
      "sales_angle": "string — góc tiếp cận bán hàng cho RM",
      "required_documents": ["string — hồ sơ cần thiết"],
      "caveats": ["string — lưu ý, điều kiện, rủi ro"],
      "citations": [{"wiki_slug": "string", "title": "string"}],
      "confidence": "low | medium | high"
    }
  ],
  "red_flags": ["string — cảnh báo rủi ro nghiêm trọng (optional, có thể rỗng)"],
  "offer_materials": [
    {
      "title": "string — tên tài liệu chào hàng",
      "wiki_slug": "string — slug wiki page",
      "reason": "string — lý do nên dùng tài liệu này"
    }
  ],
  "follow_up_questions": ["string — câu hỏi RM nên hỏi thêm khách hàng"],
  "coverage_gaps": ["string — thông tin thiếu trong CONTEXT"],
  "rm_disclaimer": "Cần RM xác minh điều kiện cấp tín dụng theo quy định BIDV hiện hành. Kết quả tư vấn chỉ mang tính tham khảo."
}
"""


def build_user_prompt(
    customer_name: str,
    province_name: str | None,
    industry_name: str | None,
    needs: str,
    additional_context: str | None,
    context_blocks: list[dict],
    segment_label: str | None = None,
) -> str:
    """Build the user prompt with customer profile and wiki CONTEXT blocks.

    Each context_block: {"index": int, "slug": str, "title": str, "summary": str, "excerpt": str}
    """
    lines = []
    lines.append("=== THÔNG TIN KHÁCH HÀNG ===")
    lines.append(f"Tên: {customer_name}")
    if segment_label:
        lines.append(f"Phân khúc: {segment_label}")
    if province_name:
        lines.append(f"Tỉnh/Thành: {province_name}")
    if industry_name:
        lines.append(f"Ngành nghề: {industry_name}")
    lines.append(f"Nhu cầu: {needs}")
    if additional_context:
        lines.append(f"Bối cảnh bổ sung: {additional_context}")

    lines.append("")
    lines.append("=== CONTEXT (Tri thức nội bộ BIDV) ===")

    if not context_blocks:
        lines.append("(Không có tài liệu nào phù hợp trong wiki)")
    else:
        for block in context_blocks:
            lines.append(f"--- [{block['index']}] slug={block['slug']} | {block['title']} ---")
            if block.get("summary"):
                lines.append(f"Tóm tắt: {block['summary']}")
            lines.append(block["excerpt"])
            lines.append("")

    lines.append("=== YÊU CẦU ===")
    lines.append("Phân tích nhu cầu khách hàng dựa trên CONTEXT và trả JSON theo schema đã quy định.")

    return "\n".join(lines)
