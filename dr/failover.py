"""BƯỚC 3b — SINH VIÊN VIẾT. Cutover sang region phụ.

5 bước, THỨ TỰ QUAN TRỌNG (§2 Kiến Trúc Tham Chiếu: DNS/LB, compute, state là 3 lớp riêng):
  1_verify_target    — /v1/state của region phụ: weights? vector count? pool_state?
  2_restore_snapshot — gọi state/snapshot.py get + state/snapshot.py rpo()
                       Log BẮT BUỘC: rpo_seconds, docs_lost, embed_model_version.
                       (§3: "backup index nhưng quên backup embedding model version
                        -> index không tương thích khi restore")
  3_scale_pool       — ghi "full" vào state/region-<t>/pool_state (warm -> full)
  4_wait_ready       — POLL /readyz tới khi 200. Region phụ có WARMUP_SECONDS —
                       đây là GPU pool warm-up của §4, nó nằm trong RTO của bạn.
  5_dns_cutover      — ghi region đích vào edge/active_region

BẪY: nếu bạn đổi edge/active_region TRƯỚC bước 4, user sẽ nhận 503 từ CẢ HAI region
và RTO của bạn dài hơn, không ngắn hơn. Nếu bước 4 timeout -> ABORT, KHÔNG cutover.

Mỗi bước ghi 1 dòng vào reports/failover-events.jsonl với ts + step.
Không có dòng 5_dns_cutover = tools/measure_rto.py không tìm được t_cutover = mất điểm.

Chạy:  python dr/failover.py --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time
import shutil

import httpx

sys.path.insert(0, ".")
from state import snapshot  # noqa: E402

URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}
LOG = pathlib.Path("reports/failover-events.jsonl")


def emit(step: str, **kw):
    """Append 1 dòng JSONL có ts + iso vào LOG, và print ra stdout."""
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "step": step,
        **kw
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"FAILOVER: {step}")
    for k, v in kw.items():
        print(f"  {k}: {v}")
    return rec


def failover(target: str, backend: str, wait: float) -> dict:
    """5 bước ở trên, đúng thứ tự."""
    result = {"ok": False}

    # Step 1: 1_verify_target - Check current state of the target region
    emit("1_verify_target")
    try:
        resp = httpx.get(f"{URL[target]}/v1/state", timeout=5)
        target_state = resp.json()
        emit("1_verify_target", target_state=target_state)
        result["target_state"] = target_state
    except Exception as e:
        emit("1_verify_target", error=str(e), status="unreachable")
        # Continue anyway - may be network issue but snapshot might work

    # Step 2: 2_restore_snapshot - Restore via state/snapshot.py
    try:
        # Get snapshot from replica
        snap_meta = snapshot.get(target, backend)
        # Calculate RPO
        primary_db = pathlib.Path(f"state/region-a/vectors.sqlite")
        restored_db = pathlib.Path(f"state/region-{target}/vectors.sqlite")
        rpo_info = snapshot.rpo(primary_db, restored_db)

        emit("2_restore_snapshot",
             rpo_seconds=rpo_info.get("rpo_seconds"),
             docs_lost=rpo_info.get("docs_lost"),
             embed_model_version=snap_meta.get("embed_model_version"))
        result["rpo_seconds"] = rpo_info.get("rpo_seconds")
        result["docs_lost"] = rpo_info.get("docs_lost")
        result["embed_model_version"] = snap_meta.get("embed_model_version")
    except Exception as e:
        emit("2_restore_snapshot", error=str(e))
        raise SystemExit(f"Cannot restore snapshot: {e}")

    # Step 3: 3_scale_pool - Flip target's pool state to "full"
    emit("3_scale_pool")
    pool_state_file = pathlib.Path(f"state/region-{target}/pool_state")
    pool_state_file.write_text("full")
    emit("3_scale_pool", pool_state="full")
    result["pool_state"] = "full"

    # Step 4: 4_wait_ready - Poll /readyz until it returns 200
    emit("4_wait_ready")
    start_wait = time.time()
    ready = False
    while time.time() - start_wait < wait:
        try:
            resp = httpx.get(f"{URL[target]}/readyz", timeout=5)
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        emit("4_wait_ready", status="TIMEOUT")
        result["fail_reason"] = "timeout_waiting_for_ready"
        return result

    emit("4_wait_ready", status="READY", wait_time_s=round(time.time() - start_wait, 2))
    result["ready"] = True
    result["ready_wait_s"] = time.time() - start_wait

    # Step 5: 5_dns_cutover - Write target region into edge/active_region
    emit("5_dns_cutover")
    active_file = pathlib.Path("edge/active_region")
    active_file.write_text(target)
    emit("5_dns_cutover", active_region=target)
    result["active_region"] = target
    result["ok"] = True

    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="b", choices=["a", "b"])
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--wait", type=float, default=60)
    a = p.parse_args()
    print(json.dumps(failover(a.target, a.backend, a.wait), indent=2))
