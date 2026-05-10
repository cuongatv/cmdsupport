# CMD Support — BIDV Brand System

## North Star: "Tin cậy chuyên nghiệp"
Chuyên nghiệp ngân hàng, tone teal đặc trưng BIDV, giao diện sạch sẽ, tập trung nội dung. Mọi yếu tố thiết kế đều hướng đến sự tin cậy và rõ ràng.

## Colors

| Token | Hex | Vai trò |
|---|---|---|
| **Primary** | `#2D8380` | CTA chính, focus ring, sidebar active |
| **Secondary** | `#005452` | Hover primary, sidebar active text, accent-foreground |
| **Tertiary** | `#13AE8E` | Accent, success, badge, chart-2 |
| **Neutral** | `#FDFFFF` | Background chung |
| Foreground | `#0F2A2A` | Text chính |
| Muted | `#5F7676` | Text phụ, placeholder |
| Border | `rgba(15,42,42,0.10)` | Viền card, input |
| Card | `#FFFFFF` | Nền card, popover |
| Primary Tint | `#E6F3F2` | Secondary background, tag nhẹ |
| Tertiary Tint | `#E0F4EC` | Accent background, badge nhẹ |
| Destructive | `#C0392B` | Lỗi, xoá |
| Warning | `#E0A23B` | Cảnh báo |
| Info | `#2A6FAE` | Thông tin bổ sung |

## Typography

- **Font:** Roboto — 6 weights (100/300/400/500/700/900), hỗ trợ italic. Subset: latin + vietnamese.
- **Headings:** weight 700, tight leading.
- **Body:** weight 400.
- **Labels/Button:** weight 500.
- Headings và body dùng chung Roboto, phân biệt qua weight.

## Elevation

- Shadow nhẹ: `0 1px 2px rgba(15,42,42,0.04), 0 8px 24px rgba(15,42,42,0.04)`.
- Ưu tiên nền tint thay vì shadow để phân tầng.
- Border subtle `rgba(15,42,42,0.10)`.

## Components

- **Button:** Primary = solid teal `#2D8380`, text trắng. Secondary = tint nhẹ `#E6F3F2`, text `#005452`. Ghost = transparent, hover nhẹ.
- **Card:** Nền `#FFFFFF`, border subtle, padding 24–32px. Border-radius `0.625rem`.
- **Input:** Nền trắng, border `rgba(15,42,42,0.10)`, focus ring teal `#2D8380`.
- **Tabs:** Indicator dùng tertiary `#13AE8E`.

## Sidebar & Header

- Nền neutral `#FDFFFF`.
- Item active: nền teal 10% `rgba(45,131,128,0.10)` + text `#005452`.
- Border: `rgba(15,42,42,0.08)`.

## Spacing

- Scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 px.
- Container max-width: 1440px.

## Responsive Breakpoints

- **< 768px** (mobile): drawer navigation + sticky CTA.
- **768–1279px** (tablet): icon sidebar 64px.
- **>= 1280px** (desktop): sidebar 240px mở rộng.

## Radius

- `--radius: 0.625rem` (10px) — áp dụng cho card, button, input.
- Các biến thể: `sm` (6px), `md` (8px), `lg` (10px), `xl` (14px).

## Iconography

- Material Symbols Outlined — variable font.
- Fill 0, weight 400, grade 0, optical size 24 (mặc định).
- Active state: fill 1.
