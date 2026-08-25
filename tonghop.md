Tổng quan dự án

Đây là Lab 23 — Region Failover trong chuỗi đào tạo VinAI về Disaster Recovery & High Availability cho hạ tầng AI. Mục tiêu: mô phỏng hai region AI inference, tấn công (kill) Region A khi đang phục vụ, rồi tự động phục hồi sang Region B — tất cả đo bằng timestamp thực từ log, không phải ước lượng.

Kiến trúc mô phỏng

┌────────────────────────────────┬────────────────────────────────────────────┐
│        Thành phần thực         │              Stand-in cục bộ               │
├────────────────────────────────┼────────────────────────────────────────────┤
│ AWS us-east-1 / us-west-2      │ 2 FastAPI process trên port 8001/8002      │
├────────────────────────────────┼────────────────────────────────────────────┤
│ Vector DB (Pinecone, Qdrant…)  │ SQLite file                                │
├────────────────────────────────┼────────────────────────────────────────────┤
│ S3 Cross-Region Replication    │ Snapshot trên filesystem (state/_replica/) │
├────────────────────────────────┼────────────────────────────────────────────┤
│ Route53 health-check failover  │ Proxy đọc file edge/active_region          │
├────────────────────────────────┼────────────────────────────────────────────┤
│ Network partition / AZ failure │ chaos/kill_region.py (SIGSTOP/SIGKILL)     │
└────────────────────────────────┴────────────────────────────────────────────┘

4 bước chính (2 tiếng)

1. Setup (10 phút) — cài deps, seed Region A (200 docs + model weights), Region B để trống (intentional gap)
2. Baseline (15 phút) — trace request path, inspect Region B, trả lời 3 câu hỏi về RTO/RPO
3. Red Team (25 phút) — kill Region A giữa chừng, chứng minh hệ thống không tự phục hồi
4. Containment (50 phút) — đây là phần chính cần code: 3 file skeleton trong dr/
5. Prove & Collect Evidence (20 phút) — re-attack, đo RTO/RPO, viết báo cáo

Phần cần code (dr/)

dr/health_checker.py  — poll /readyz mỗi N giây, threshold chống flapping
dr/failover.py        — 5 bước: verify → restore snapshot → scale pool → wait ready → DNS cutover
dr/runbook.py         — 7 bước semi-automated, hỏi xác nhận y/N, ghi events ra JSONL

Điều kiện đạt điểm

- RTO ≤ 300s (đo từ measure_rto.py)
- RPO đo được (seconds + docs lost)
- 3 report: rto-evidence.md, postmortem.md, runbook.md — mỗi số phải trace về file thực + dòng cụ thể
- Test suite phải pass hoàn toàn: pytest tests/ -v

Hard-fail conditions

- measure_rto.py trả "valid": false → fail ngay
- RTO trong báo cáo lệch quá 1s so với measure_rto.py → fail ngay
- Cutover xảy ra trước khi health checker phát hiện outage (t_cutover < t_detect) → fail ngay