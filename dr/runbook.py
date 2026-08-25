"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time
import statistics

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


def step(n, name, **kw):
    """Ghi 1 dòng {ts, iso, step, name, ...} vào LOG."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "step": n,
        "name": name,
        **kw
    }
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"RUNBOOK: step {n} - {name}")
    for k, v in kw.items():
        print(f"  {k}: {v}")
    return rec


def confirm(auto: bool, msg: str) -> bool:
    """auto=True -> True; ngược lại hỏi y/N."""
    if auto:
        return True
    print(f"{msg} [y/N]: ", end="")
    response = input().strip().lower()
    return response == "y"


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    """7 bước ở trên."""
    result = {}
    start_time = time.time()

    # Step 1: xac_nhan_outage - Confirm outage by probing both regions
    step(1, "xac_nhan_outage")
    # Probe multiple times to confirm
    primary_alive = False
    target_alive = False
    for _ in range(3):
        try:
            r = httpx.get(f"{URL[primary]}/healthz", timeout=2)
            if r.status_code == 200:
                primary_alive = True
        except:
            pass
        try:
            r = httpx.get(f"{URL[target]}/healthz", timeout=2)
            if r.status_code == 200:
                target_alive = True
        except:
            pass
        time.sleep(1)

    step(1, "xac_nhan_outage",
         primary_alive=primary_alive,
         target_alive=target_alive,
         confirmed=not primary_alive)
    result["outage_confirmed"] = not primary_alive

    if not confirm(auto, f"Confirm failover from {primary} to {target}?"):
        step(1, "xac_nhan_outage", status="cancelled")
        return result

    # Step 2: thong_bao_incident - Announce incident
    step(2, "thong_bao_incident")
    step(2, "thong_bao_incident",
         operator_notified_at=time.time(),
         note="Incident announced - failover initiated")
    result["incident_announced"] = True

    # Step 3: scale_gpu_pool - Call failover.failover() exactly once
    step(3, "scale_gpu_pool")
    fo_result = fo.failover(target, backend, wait=60)
    step(3, "scale_gpu_pool",
         failover_result=fo_result.get("ok", False),
         rpo_seconds=fo_result.get("rpo_seconds"),
         docs_lost=fo_result.get("docs_lost"))
    result["failover_result"] = fo_result
    result["rpo_seconds"] = fo_result.get("rpo_seconds")
    result["docs_lost"] = fo_result.get("docs_lost")

    # Step 4: verify_state_replica - Read results from step 3
    step(4, "verify_state_replica")
    try:
        resp = httpx.get(f"{URL[target]}/v1/state", timeout=5)
        target_state = resp.json()
        step(4, "verify_state_replica",
             vector_count=target_state.get("count", 0),
             weights_ok=target_state.get("weights", False),
             pool_state=target_state.get("pool_state"))
        result["target_state"] = target_state
    except Exception as e:
        step(4, "verify_state_replica", error=str(e))

    # Step 5: dns_cutover - Check cutover result
    step(5, "dns_cutover")
    active_region = pathlib.Path("edge/active_region").read_text().strip()
    step(5, "dns_cutover",
         active_region=active_region,
         cutover_ok=(active_region == target))
    result["cutover_ok"] = (active_region == target)

    # Step 6: verify_golden_signals - 10 real requests
    step(6, "verify_golden_signals")
    latencies = []
    errors = 0
    for i in range(10):
        try:
            t0 = time.time()
            r = httpx.get(f"{URL[target]}/v1/infer", timeout=10)
            lat = (time.time() - t0) * 1000
            latencies.append(lat)
            if r.status_code != 200:
                errors += 1
        except Exception:
            errors += 1

    if latencies:
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        step(6, "verify_golden_signals",
             requests=10,
             errors=errors,
             p95_latency_ms=round(p95, 2),
             error_rate=errors/10)
        result["golden_signals"] = {"p95_latency_ms": p95, "error_rate": errors/10}

    # Step 7: post_incident - Summary
    elapsed = time.time() - start_time
    step(7, "post_incident",
         total_elapsed_s=round(elapsed, 2),
         rto_measure_command="python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300")
    result["total_elapsed_s"] = elapsed

    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
