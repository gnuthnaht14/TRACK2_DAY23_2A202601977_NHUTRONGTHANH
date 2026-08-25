"""BƯỚC 3a — SINH VIÊN VIẾT. Health checker cho 2 region.

Yêu cầu (đọc §4 "Kiến Trúc Health-Check-Based Failover" + §2 "DNS Failover"):
  1. Poll /readyz của CẢ HAI region mỗi `interval` giây (mặc định 5s).
     Dùng /readyz, KHÔNG dùng /healthz. /healthz chỉ nói "process còn sống" —
     region có process sống nhưng vector DB rỗng thì vẫn không serve được.
  2. Chỉ đổi trạng thái sau `threshold` lần fail LIÊN TIẾP (mặc định 3).
     Một lần fail không phải outage. Đây là chống flapping (§4 Anti-Patterns).
  3. Ghi 1 dòng JSONL MỖI LẦN ĐỔI TRẠNG THÁI (không ghi mỗi lần poll — log sẽ ngập).
     Dòng bắt buộc có: ts, region, to (HEALTHY|UNHEALTHY), reason,
     interval_s, threshold. Thiếu interval_s/threshold thì tools/measure_rto.py
     không tính được detect floor -> mất điểm.

Chạy:  python dr/health_checker.py --interval 5 --threshold 3 --duration 300 \
              --out reports/health-events.jsonl
"""
import argparse
import json
import pathlib
import time

import httpx

URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


def probe(region: str, timeout: float) -> tuple[bool, str]:
    """Trả về (ready, reason). Timeout PHẢI có — netblock làm request treo mãi."""
    try:
        resp = httpx.get(f"{URL[region]}/readyz", timeout=timeout)
        if resp.status_code == 200:
            return True, "ready"
        else:
            data = resp.json()
            return False, "; ".join(data.get("reasons", []))
    except Exception as e:
        return False, str(type(e).__name__)


def run(interval: float, timeout: float, threshold: int, duration: float, out: pathlib.Path):
    """Vòng lặp poll + phát hiện transition + ghi JSONL."""
    # Track consecutive failures for each region
    failures = {"a": 0, "b": 0}
    current_state = {"a": "UNKNOWN", "b": "UNKNOWN"}

    out.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()
    while time.time() - start < duration:
        for region in ["a", "b"]:
            ready, reason = probe(region, timeout)

            if ready:
                failures[region] = 0
                new_state = "HEALTHY"
            else:
                failures[region] += 1
                # Only flip to UNHEALTHY after threshold consecutive failures
                if failures[region] >= threshold:
                    new_state = "UNHEALTHY"
                else:
                    new_state = current_state[region]  # Keep current state

            # Only log state changes
            if new_state != current_state[region] and current_state[region] != "UNKNOWN":
                record = {
                    "ts": time.time(),
                    "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    "event": "state_change",
                    "region": region,
                    "to": new_state,
                    "reason": reason,
                    "interval_s": interval,
                    "threshold": threshold,
                    "consecutive_fails": failures[region]
                }
                with out.open("a") as f:
                    f.write(json.dumps(record) + "\n")
                print(f"STATE_CHANGE: {region} -> {new_state}: {reason}")

            current_state[region] = new_state

        time.sleep(interval)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--timeout", type=float, default=2.0)
    p.add_argument("--threshold", type=int, default=3)
    p.add_argument("--duration", type=float, default=300)
    p.add_argument("--out", default="reports/health-events.jsonl")
    a = p.parse_args()
    run(a.interval, a.timeout, a.threshold, a.duration, pathlib.Path(a.out))
