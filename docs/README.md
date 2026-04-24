# Docs — Money Tracking

Tài liệu thiết kế cho hệ thống quản lý chi tiêu cá nhân local-first, LLM-powered.

## Mục lục

| # | File | Nội dung |
|---|---|---|
| 01 | [overview.md](./01-overview.md) | Mục tiêu, phạm vi, persona, non-goals |
| 02 | [architecture.md](./02-architecture.md) | Sơ đồ hệ thống, thành phần, luồng dữ liệu |
| 03 | [tech-stack.md](./03-tech-stack.md) | Lựa chọn công nghệ & lý do |
| 04 | [data-model.md](./04-data-model.md) | Schema DB, ERD, index chính |
| 05 | [features.md](./05-features.md) | 4 luồng nhập liệu + budget + insight |
| 06 | [llm-strategy.md](./06-llm-strategy.md) | Prompt, JSON schema, routing model |
| 07 | [gmail.md](./07-gmail.md) | OAuth, polling, parser, rule learning |
| 08 | [telegram.md](./08-telegram.md) | Bot, polling 5s, commands, flows |
| 09 | [api.md](./09-api.md) | REST endpoints & WebSocket |
| 10 | [security.md](./10-security.md) | Bảo mật, secrets, redaction |
| 11 | [deployment.md](./11-deployment.md) | Docker compose, cấu hình |
| 12 | [roadmap.md](./12-roadmap.md) | Milestone & thứ tự thực thi |
| 13 | [dashboard.md](./13-dashboard.md) | Layout tracking chi tiết của dashboard |
| 14 | [llm-tools.md](./14-llm-tools.md) | LangChain ReAct agent + Gmail readonly tool + Langfuse |

## Quy ước

- Tất cả đơn vị tiền tệ mặc định là **VND**.
- Timezone mặc định `Asia/Ho_Chi_Minh`.
- Tài liệu viết tiếng Việt; code/identifier/commit message tiếng Anh.
- Khi có thay đổi quyết định thiết kế, cập nhật file tương ứng và ghi chú trong [roadmap.md](./12-roadmap.md).
