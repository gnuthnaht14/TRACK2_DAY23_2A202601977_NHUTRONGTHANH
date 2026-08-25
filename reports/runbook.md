# Runbook 1 trang — Region chính down

Runbook phải chạy được lúc 3h sáng bởi người KHÔNG viết nó. Mỗi bước: lệnh copy-paste
được + cách biết bước đó xong.

| # | Bước | Lệnh | Biết là xong khi | Ai làm |
|---|---|---|---|---|
| 1 | Xác nhận outage | `python chaos/kill_region.py status` | `a.alive=false` 3 lần liên tiếp | on-call |
| 2 | Mở incident + bấm giờ RTO | `python dr/runbook.py --primary a --target b --backend fs --auto` | ts ghi vào `reports/runbook-run.jsonl` | on-call |
| 3 | Restore state ở region phụ | Tự động trong bước 3 của runbook.py | Vector count > 0, weights=true trong `reports/failover-events.jsonl` | tự động |
| 4 | Scale pool warm→full | Tự động trong bước 3 của runbook.py | `/readyz` của b trả 200 | tự động |
| 5 | DNS/LB cutover | Tự động trong bước 3 của runbook.py | `curl localhost:8080/edge/state` cho `active_region=b` | tự động |
| 6 | Verify golden signals | Tự động trong bước 6 của runbook.py | p95 < 500ms, error rate < 5% trong `reports/runbook-run.jsonl` | tự động |
| 7 | Đo RTO + postmortem | `python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300` | `rto_verdict` = PASS hoặc NO_RECOVERY | on-call |

**Rollback (failover ngược):** Khi nào thì trả traffic về region A?

- **Điều kiện:** Region A đã restore và `/readyz` trả 200
- **Ai quyết định:** on-call engineer
- **Lệnh rollback:**
  ```bash
  echo a > edge/active_region
  ```
- **Lưu ý:** Không chạy full-auto failover mà không có circuit breaker - sẽ gây flap giữa 2 region liên tục (§4 Anti-Patterns).
