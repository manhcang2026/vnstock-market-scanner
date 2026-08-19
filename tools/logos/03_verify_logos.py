from __future__ import annotations
import argparse,csv
from pathlib import Path

def read_csv(p):
    with open(p,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--manifest",default="tools/logos/work/logo_manifest.csv");args=ap.parse_args()
    rows=read_csv(Path(args.manifest));real=[r for r in rows if r.get("status")=="REAL_CANDIDATE"];fallback=[r for r in rows if r.get("status")=="FALLBACK"]
    print(f"TOTAL {len(rows)} | REAL_CANDIDATE {len(real)} | FALLBACK {len(fallback)}")
    if fallback:
        print("FALLBACK:",", ".join(r.get("symbol","") for r in fallback))
        print("Có thể thêm URL thật vào tools/logos/config/logo_overrides.csv rồi chạy lại --force cho các mã này.")
if __name__=="__main__":main()
