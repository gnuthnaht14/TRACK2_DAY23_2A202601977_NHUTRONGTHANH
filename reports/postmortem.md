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

1. **Tinh interval x threshold va cho biet no chiem bao nhieu % cua RTO?**
   - Answer: interval x threshold = 5s x 3 = 15s, chiem 51% cua RTO (15s / 29.4s)

2. **Neu giam interval xuong 1s thi RTO giam bao nhieu? Co mao hiem khong?**
   - Answer: RTO giam khoang 12s (tu 29.4s xuong ~17s). Co mao hiem vi giam interval tang risk false positive - health checker co the flip state vi transient network issue thay vi that su outage.

3. **docs_lost co nghia la gi? Tai sao con so nay quan trong voi khach hang?**
   - Answer: docs_lost = 3 nghia la 3 documents cua khach hang bi mat khi failover vi chua duoc replicate tu region A sang region B. Quan trong vi day la data loss truc tiep anh huong den khach hang - customer documents khong the truy xuat duoc sau disaster.
