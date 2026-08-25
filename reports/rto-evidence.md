# RTO/RPO Evidence - Lab 23

## 1. Drill 1 - No DR (baseline)

| Metric | Value | How to Measure | Evidence |
|---|---|---|---|
| t_outage | 2026-08-25T05:14:56 | chaos kill | `chaos/chaos-events.jsonl:1` |
| First failed request | +0.9s | first ok:false after t_outage | `reports/drill-1-nodr.jsonl:17` |
| Recovery after | none | no ok:true after t_outage | - |
| RTO | NO_RECOVERY | measure_rto.py | `reports/drill-1-nodr.jsonl` |

## 2. Drill 2 - With DR

| Milestone | +seconds from t_outage | How to Measure | Evidence |
|---|---|---|---|
| t_outage (zero) | 0 | action:kill | `chaos/chaos-events.jsonl:2` |
| First error | 0.9 | first ok:false | `reports/drill-2-withdr.jsonl:81` |
| Health check detects | 20.1 | to:UNHEALTHY region:a | `reports/health-events.jsonl:1` |
| Snapshot restored | 26.7 | step:2_restore_snapshot | `reports/failover-events.jsonl:3` |
| Region B ready | 26.7 | step:4_wait_ready | `reports/failover-events.jsonl:7` |
| DNS cutover | 26.7 | step:5_dns_cutover | `reports/failover-events.jsonl:8` |
| **RTO** | **29.4** | first ok:true after outage | `reports/drill-2-withdr.jsonl:94` |

| Metric | Measured | Target | Verdict |
|---|---|---|---|
| RTO - Inference API | 29.4s | 300s (5 min) | PASS |
| RPO - Vector DB | 6.0s / 3 docs | 300s | PASS |

## 3. RTO Breakdown (required)

| Component | Seconds | Source | How to Reduce |
|---|---|---|---|
| Health-check detect floor | 15.0 | interval_s x threshold | reduce interval or threshold |
| Snapshot restore | ~0.1 | 2_restore to 3_scale | faster storage |
| GPU pool warm-up | 0.04 | waited_s at 4_wait_ready | pre-warm target |
| DNS/LB TTL cache | 1.8 | t_recovered - t_cutover | reduce TTL |
| **Total** | **27.3** | | |

Health check config: interval=5s, threshold=3, detect_floor=15s
