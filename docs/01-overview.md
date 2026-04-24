# 01 — Tổng quan

## Mục tiêu

Một ứng dụng quản lý chi tiêu cá nhân **chạy local** trên máy của chủ sở hữu, cho phép:

1. Ghi nhận giao dịch bằng nhiều kênh: nhập tay, chat tự nhiên, email ngân hàng, Telegram.
2. Dùng LLM để trích xuất & phân loại giao dịch mà không phải click form dài.
3. Theo dõi ngân sách theo tháng/category, cảnh báo qua Telegram khi bất thường.
4. Xem dashboard trực quan (biểu đồ, top merchant, xu hướng).
5. Tương tác hai chiều qua Telegram: báo cáo nhanh, truy vấn ngắn, xác nhận giao dịch.

## Phạm vi (MVP)

**Có:**
- 1 user (chủ sở hữu máy).
- Đa tài khoản (tiền mặt, các ngân hàng, ví điện tử).
- Đa loại tiền (ưu tiên VND, hỗ trợ USD để theo dõi thu quốc tế).
- Import Gmail read-only qua OAuth.
- Telegram bot với short polling 5s.
- LLM local (Ollama) + fallback cloud (DeepSeek).
- Dashboard tháng, so sánh tháng trước.

**Chưa làm (non-goals MVP):**
- Multi-user, chia sẻ ngân sách gia đình.
- Đồng bộ nhiều thiết bị (mobile app riêng).
- Kết nối API ngân hàng trực tiếp (open banking) — đa số ngân hàng VN chưa mở.
- Đầu tư / portfolio tracking chi tiết (chỉ track giao dịch, không định giá).
- Xuất báo cáo thuế.

## Persona

**Chủ sở hữu (single user)**
- Có 1 máy tính cá nhân luôn bật hoặc bật hàng ngày.
- Dùng 2–5 tài khoản ngân hàng / ví, có email thông báo giao dịch.
- Muốn kỷ luật chi tiêu nhưng ngại nhập tay.
- Quen Telegram, thường xuyên online.
- Không muốn dữ liệu tài chính nằm trên cloud SaaS.

## Nguyên tắc thiết kế

1. **Local-first**: DB, LLM chính, bot đều chạy trên máy user. Cloud chỉ là optional fallback.
2. **Low friction**: nhập 1 giao dịch không quá 3 giây (1 dòng chat hoặc 1 tap confirm).
3. **Progressive trust**: LLM đề xuất, user confirm lần đầu; lần sau học theo rule đã lưu.
4. **Privacy by default**: không gửi raw email/số tài khoản sang LLM cloud; redact trước.
5. **Graceful degradation**: mất mạng vẫn nhập tay & chat local được (nếu Ollama sẵn sàng).

## Định nghĩa "Done" cho MVP

- [ ] Ghi được 1 giao dịch bằng nhập tay trên web.
- [ ] Chat tiếng Việt "ăn phở 45k bằng momo" → lưu DB đúng.
- [ ] Email thông báo chuyển khoản từ 2 ngân hàng chính được parse tự động.
- [ ] Telegram bot nhận tin nhắn mới trong ≤ 5s và xử lý như chat web.
- [ ] Dashboard hiện chi tiêu tháng theo category (pie + bar).
- [ ] Cảnh báo Telegram khi category X vượt 80% ngân sách tháng.
- [ ] Chạy được bằng `docker compose up` sau khi điền `.env`.
