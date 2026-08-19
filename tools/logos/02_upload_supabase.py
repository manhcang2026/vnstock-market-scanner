from __future__ import annotations
import argparse, csv, os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

def read_csv(p):
    with open(p,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default="tools/logos/work/logo_manifest.csv")
    ap.add_argument("--bucket",default="stock-logos")
    ap.add_argument("--include-fallback",action="store_true",help="Upload cả logo fallback ticker")
    args=ap.parse_args()

    load_dotenv("tools/logos/.env")
    url=(os.getenv("SUPABASE_URL") or "").strip()
    key=(os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Thiếu SUPABASE_URL hoặc SUPABASE_SECRET_KEY trong tools/logos/.env")

    rows=read_csv(Path(args.manifest));supabase=create_client(url,key);ok=0;skip=0;err=0
    for i,r in enumerate(rows,1):
        symbol=(r.get("symbol") or "").upper();status=r.get("status") or "";p=Path(r.get("local_path") or "")
        if status=="FALLBACK" and not args.include_fallback:
            print(f"[{i}/{len(rows)}] {symbol} SKIP fallback");skip+=1;continue
        if not p.exists():
            print(f"[{i}/{len(rows)}] {symbol} ERROR missing file");err+=1;continue
        try:
            with open(p,"rb") as f:
                supabase.storage.from_(args.bucket).upload(
                    path=f"{symbol}.webp",
                    file=f,
                    file_options={"content-type":"image/webp","cache-control":"31536000","upsert":"true"},
                )
            ok+=1;print(f"[{i}/{len(rows)}] {symbol} OK")
        except Exception as e:
            err+=1;print(f"[{i}/{len(rows)}] {symbol} ERROR {e}")
    print(f"UPLOAD XONG: OK {ok} | SKIP {skip} | ERROR {err}")
    print(f"Public URL mẫu: {url}/storage/v1/object/public/{args.bucket}/ACB.webp")

if __name__=="__main__":main()
