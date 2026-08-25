# Postmortem - DR Drill Lab 23

## 1. Timeline

| ISO time | Event | Evidence |
|---|---|---|
| 2026-08-25T05:46:05 | outage starts (kill region a) | `chaos/chaos-events.jsonl:2` |
| 2026-08-25T05:46:06 | first user sees error | `reports/drill-2-withdr.jsonl:81` |
| 2026-08-25T05:46:25 | health check detects UNHEALTHY | `reports/health-events.jsonl:1` |
| 2026-08-25T05:46:32 | DNS cutover to region b | `reports/failover-events.jsonl:8` |
| 2026-08-25T05:46:34 | resolved - first OK from region b | `reports/drill-2-withdr.jsonl:94` |

## 2. RTO/RPO vs Target

- Target RTO: 300s | Measured: 29.4s | Gap: 270.6s (PASS)
- Target RPO: 300s | Measured: 6.0s (3 docs lost) | Gap: 294.0s (PASS)
- **Slowest step:** health-check detection floor (15s = 51% of RTO)

## 3. Root Cause

The health-check detection floor (interval x threshold = 5s x 3 = 15s) accounts for 51% of total RTO.
This is by design - anti-flapping threshold prevents unnecessary failovers.

## 4. Action Items

| # | Action | Owner | Deadline | RTO Reduction |
|---|---|---|---|---|
| 1 | Reduce health-check interval from 5s to 2s | on-call | next drill | -6s |
| 2 | Pre-warm region B pool state | ops | next sprint | -0s (removes warm-up) |

## 5. Required Questions

1. **Tính `interval x threshold` và cho biết nó chiếm bao nhiêu % của RTO?**
   - Answer: `interval x threshold` = 5s × 3 = 15s, chiếm 51% của RTO (15s / 29.4s)

2. **Nếu giảm interval xuống 1s thì RTO giảm bao nhiêu? Có mạo hiểm không?**
   - Answer: RTO giảm khoảng 12s (từ 29.4s xuống ~17s). Có mạo hiểm vì giảm interval tăng risk false positive - health checker có thể flip state vì transient network issue thay vì thật sự outage.

3. **`docs_lost` có nghĩa là gì? Tại sao con số này quan trọng với khách hàng?**
   - Answer: `docs_lost = 3` nghĩa là 3 documents của khách hàng bị mất khi failover vì chưa được replicate từ region A sang region B. Quan trọng vì đây là data loss trực tiếp ảnh hưởng đến khách hàng - customer documents không thể truy xuất được sau disaster.
