PY=.\.venv\Scripts\python.exe
PYTEST=.\.venv\Scripts\python.exe -m pytest

.PHONY: seed up-bare down-bare drill-baseline drill-dr rto test clean

seed:
	$(PY) state/seed_vectors.py --region a --docs 200
	$(PY) state/seed_vectors.py --region b --docs 0 --weights-mb 0
	pwsh -Command "Set-Content -Path edge/active_region -Value 'a' -NoNewline"

up-bare:
	pwsh -File scripts/up_bare.ps1

down-bare:
	pwsh -File scripts/down_bare.ps1

# Buoc 2: baseline khong co DR
drill-baseline:
	pwsh -Command "Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList 'loadgen/traffic.py','--duration','40','--rps','2','--out','reports/drill-1-nodr.jsonl' -WorkingDirectory '.' -NoNewWindow -PassThru | Out-Null; Start-Sleep 8; .venv\Scripts\python.exe chaos/kill_region.py --region a --mode netblock --mock; Start-Sleep 40"

# Buoc 4: replay attack sau khi contain xong
# replicate.py phai chay TRUOC va co it nhat 1 chu ky xong, khong thi failover.py
# se chet o buoc 2_restore_snapshot vi chua tung co snapshot nao duoc put.
drill-dr:
	pwsh -Command "Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList 'state/ingest.py','--region','a','--rate','0.5','--duration','150' -WorkingDirectory '.' -NoNewWindow -PassThru | Out-Null"
	pwsh -Command "Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList 'state/replicate.py','--every','30','--duration','150','--backend','fs' -WorkingDirectory '.' -NoNewWindow -PassThru | Out-Null"
	pwsh -Command "Start-Sleep 5; Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList 'loadgen/traffic.py','--duration','100','--rps','2','--out','reports/drill-2-withdr.jsonl' -WorkingDirectory '.' -NoNewWindow -PassThru | Out-Null; Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList 'dr/health_checker.py','--interval','5','--threshold','3','--duration','100','--out','reports/health-events.jsonl' -WorkingDirectory '.' -NoNewWindow -PassThru | Out-Null; Start-Sleep 12; .venv\Scripts\python.exe chaos/kill_region.py --region a --mode netblock --mock"

rto:
	$(PY) tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300

test:
	$(PYTEST) tests/ -v

clean:
	pwsh -File scripts/down_bare.ps1
	Remove-Item -Recurse -Force state/region-a -ErrorAction SilentlyContinue
	Remove-Item -Recurse -Force state/region-b -ErrorAction SilentlyContinue
	Remove-Item -Recurse -Force state/_replica -ErrorAction SilentlyContinue
	Remove-Item -Recurse -Force run -ErrorAction SilentlyContinue
	Remove-Item -Force reports/*.jsonl -ErrorAction SilentlyContinue
	Remove-Item -Force reports/*.json -ErrorAction SilentlyContinue
	Remove-Item -Force chaos/chaos-events.jsonl -ErrorAction SilentlyContinue
