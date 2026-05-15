"""
Prompt templates for AI Assist trên trang Quy tắc tư vấn.

Mỗi prompt nhận `basic_info` (RM nhập) và một context (tên sản phẩm, label phân
khúc, hoặc tên tỉnh) rồi sinh ra nội dung gợi ý cho RM. RM có thể chỉnh trước
khi lưu — đây chỉ là hỗ trợ soạn thảo, không phải nguồn duy nhất.
"""

PROMPT_VERSION = "v1.0"

SYSTEM_PROMPT_VI = (
    "Bạn là chuyên gia phân tích Khách hàng Doanh nghiệp (KHDN) của ngân hàng "
    "BIDV. Hãy trả lời ngắn gọn, có cấu trúc bullet, bằng tiếng Việt. Không "
    "thêm lời mở đầu hoặc kết luận thừa. Không sử dụng markdown fence."
)


def build_product_persona_prompt(product_name: str, basic_info: str) -> str:
    return (
        f"Sản phẩm/chính sách: {product_name}\n\n"
        f"Thông tin cơ bản RM cung cấp:\n{basic_info}\n\n"
        "Hãy mô tả chân dung khách hàng doanh nghiệp tiềm năng phù hợp nhất với "
        "sản phẩm/chính sách trên, dưới dạng bullet, bao gồm:\n"
        "- Ngành nghề điển hình\n"
        "- Quy mô (doanh thu / số nhân sự / vốn)\n"
        "- Đặc điểm tài chính & dòng tiền\n"
        "- Nhu cầu/Pain point thường gặp\n"
        "- Tín hiệu mua hàng (mua lúc nào, ai quyết định)\n"
        "- Các rủi ro cần lưu ý khi tiếp cận\n"
        "Trả lời súc tích, mỗi bullet ngắn gọn 1-2 dòng."
    )


def build_segment_specifics_prompt(segment_label: str, basic_info: str) -> str:
    return (
        f"Phân khúc khách hàng: {segment_label}\n\n"
        f"Thông tin cơ bản RM cung cấp:\n{basic_info}\n\n"
        "Hãy nêu các đặc thù tư vấn riêng cho phân khúc này tại BIDV, dạng "
        "bullet:\n"
        "- Đặc điểm hành vi & ưu tiên của phân khúc\n"
        "- Sản phẩm/dịch vụ thường phù hợp\n"
        "- Lưu ý về điều kiện tín dụng / hồ sơ\n"
        "- Cách RM nên tiếp cận và tone trao đổi\n"
        "- Cảnh báo rủi ro đặc thù phân khúc\n"
        "Súc tích, mỗi bullet 1-2 dòng."
    )


def build_province_specifics_prompt(province_name: str, basic_info: str) -> str:
    return (
        f"Địa bàn: {province_name}\n\n"
        f"Thông tin cơ bản RM cung cấp:\n{basic_info}\n\n"
        "Hãy nêu các đặc thù tư vấn KHDN tại địa bàn này, dạng bullet:\n"
        "- Đặc điểm kinh tế - ngành nghề chủ đạo của địa bàn\n"
        "- Phân khúc KHDN phổ biến\n"
        "- Các sản phẩm BIDV nên ưu tiên giới thiệu\n"
        "- Đặc thù văn hoá / cách tiếp cận khách hàng\n"
        "- Rủi ro/lưu ý đặc thù địa bàn\n"
        "Súc tích, mỗi bullet 1-2 dòng."
    )
