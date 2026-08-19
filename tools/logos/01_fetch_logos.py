from __future__ import annotations
import argparse, csv, json, re, time
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageDraw, ImageFont

VIETSTOCK="https://finance.vietstock.vn"
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36","Accept-Language":"vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"}
TIMEOUT=25
DELAY=.35
SIZE=256

def read_csv(p):
    with open(p,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def write_csv(p,rows,fields):
    p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

def load_overrides(path):
    if not path.exists():return {}
    return {(r.get("symbol") or "").strip().upper():(r.get("logo_url") or "").strip() for r in read_csv(path) if (r.get("symbol") or "").strip() and (r.get("logo_url") or "").strip()}

def get(session,url):
    r=session.get(url,headers=HEADERS,timeout=TIMEOUT,allow_redirects=True);r.raise_for_status();return r

def extract_website(html,base_url):
    soup=BeautifulSoup(html,"html.parser")
    # Ưu tiên link ngay cạnh chữ Website.
    for node in soup.find_all(string=re.compile(r"^\s*Website\s*$",re.I)):
        parent=node.parent
        for scope in [parent,parent.parent if parent else None,parent.parent.parent if parent and parent.parent else None]:
            if not scope:continue
            a=scope.find("a",href=True)
            if a and a["href"].startswith(("http://","https://")):
                h=a["href"]
                if "vietstock" not in urlparse(h).netloc.lower(): return h
    # Fallback: domain bên ngoài Vietstock có text giống website.
    for a in soup.find_all("a",href=True):
        h=a["href"].strip(); txt=a.get_text(" ",strip=True)
        if h.startswith(("http://","https://")) and "vietstock" not in urlparse(h).netloc.lower():
            if txt.startswith("www.") or re.match(r"^[\w.-]+\.[a-z]{2,}$",txt,re.I):return h
    return ""

def img_score(img,symbol,index):
    attrs=" ".join([
        str(img.get("src") or ""),str(img.get("data-src") or ""),str(img.get("alt") or ""),
        " ".join(img.get("class") or []),str(img.get("id") or ""),str(img.get("title") or "")
    ]).lower()
    score=0
    if "logo" in attrs:score+=12
    if symbol.lower() in attrs:score+=8
    if index<40:score+=2
    bad=["icon","arrow","avatar","person","leader","member","user","vietstock","banner","chart","loading","sprite","flag","menu"]
    if any(x in attrs for x in bad):score-=12
    src=(img.get("src") or img.get("data-src") or "").lower()
    if src.endswith(".svg"):score-=5
    return score

def extract_img_candidates(html,base_url,symbol):
    soup=BeautifulSoup(html,"html.parser");out=[]
    # JSON-LD Organization.logo
    for s in soup.find_all("script",type="application/ld+json"):
        try:
            obj=json.loads(s.string or "null")
            objs=obj if isinstance(obj,list) else [obj]
            for o in objs:
                if isinstance(o,dict):
                    logo=o.get("logo")
                    if isinstance(logo,dict):logo=logo.get("url")
                    if isinstance(logo,str):out.append((30,urljoin(base_url,logo),"JSONLD_LOGO"))
        except:pass
    for i,img in enumerate(soup.find_all("img")):
        src=img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:continue
        out.append((img_score(img,symbol,i),urljoin(base_url,src),"IMG"))
    # og:image có thể là branding; chỉ dùng điểm vừa phải.
    for m in soup.find_all("meta"):
        prop=(m.get("property") or m.get("name") or "").lower()
        if prop in {"og:image","twitter:image"} and m.get("content"):
            out.append((8,urljoin(base_url,m["content"]),"META_IMAGE"))
    out.sort(key=lambda x:x[0],reverse=True)
    seen=set();res=[]
    for item in out:
        if item[1] not in seen:
            seen.add(item[1]);res.append(item)
    return res

def extract_icons(html,base_url):
    soup=BeautifulSoup(html,"html.parser");out=[]
    for l in soup.find_all("link",href=True):
        rel=" ".join(l.get("rel") or []).lower()
        if "icon" in rel:out.append(urljoin(base_url,l["href"]))
    out += [urljoin(base_url,"/favicon.ico")]
    return list(dict.fromkeys(out))

def decode_image(content):
    im=Image.open(BytesIO(content));im.load();return im.convert("RGBA")

def acceptable(im):
    w,h=im.size
    if w<32 or h<32:return False
    ratio=max(w/h,h/w)
    return ratio<=5

def normalize_and_save(im,path):
    im=im.convert("RGBA")
    box=im.getbbox()
    if box:im=im.crop(box)
    im.thumbnail((220,220),Image.Resampling.LANCZOS)
    canvas=Image.new("RGBA",(SIZE,SIZE),(255,255,255,0))
    x=(SIZE-im.width)//2;y=(SIZE-im.height)//2
    canvas.alpha_composite(im,(x,y))
    path.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(path,"WEBP",lossless=True,quality=95,method=6)

def download_candidate(session,url):
    try:
        r=get(session,url)
        ctype=(r.headers.get("content-type") or "").lower()
        if "svg" in ctype or url.lower().endswith(".svg"):return None
        im=decode_image(r.content)
        return im if acceptable(im) else None
    except Exception:
        return None

def fallback_logo(symbol,path):
    canvas=Image.new("RGBA",(SIZE,SIZE),(245,245,245,255))
    d=ImageDraw.Draw(canvas)
    font=ImageFont.load_default()
    text=symbol[:5]
    bbox=d.textbbox((0,0),text,font=font)
    d.text(((SIZE-(bbox[2]-bbox[0]))/2,(SIZE-(bbox[3]-bbox[1]))/2),text,font=font,fill=(40,40,40,255))
    canvas.save(path,"WEBP",lossless=True,quality=95,method=6)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--watchlist",default="config/watchlist.csv")
    ap.add_argument("--symbols",default="",help="CSV có cột symbol; bỏ trống = toàn watchlist")
    ap.add_argument("--overrides",default="tools/logos/config/logo_overrides.csv")
    ap.add_argument("--out-dir",default="tools/logos/output")
    ap.add_argument("--manifest",default="tools/logos/work/logo_manifest.csv")
    ap.add_argument("--force",action="store_true")
    args=ap.parse_args()

    watch=read_csv(Path(args.watchlist));allsyms=sorted({(r.get("symbol") or "").strip().upper() for r in watch if (r.get("symbol") or "").strip()})
    if args.symbols:
        wanted=sorted({(r.get("symbol") or "").strip().upper() for r in read_csv(Path(args.symbols)) if (r.get("symbol") or "").strip()})
    else:wanted=allsyms
    bad=[s for s in wanted if s not in allsyms]
    if bad:raise RuntimeError("Symbols không có trong watchlist: "+", ".join(bad))

    overrides=load_overrides(Path(args.overrides));out=Path(args.out_dir);manifest_path=Path(args.manifest);session=requests.Session();rows=[]
    old={}
    if manifest_path.exists():
        for r in read_csv(manifest_path):old[(r.get("symbol") or "").upper()]=r

    for idx,symbol in enumerate(wanted,1):
        dest=out/f"{symbol}.webp"
        if dest.exists() and not args.force:
            r=old.get(symbol,{"symbol":symbol,"status":"EXISTS","source":"EXISTING","source_url":"","website_url":"","local_path":str(dest)})
            rows.append(r);print(f"[{idx}/{len(wanted)}] {symbol} EXISTS");continue
        profile=f"{VIETSTOCK}/{symbol}/ho-so-doanh-nghiep.htm";html="";website="";chosen=None;source="";source_url=""
        try:
            pr=get(session,profile);html=pr.text;website=extract_website(html,profile)
        except Exception as e:
            print(f"[{idx}/{len(wanted)}] {symbol} Vietstock error: {e}")

        # 1 manual override
        if overrides.get(symbol):
            im=download_candidate(session,overrides[symbol])
            if im is not None:chosen=im;source="OVERRIDE";source_url=overrides[symbol]

        # 2 Vietstock profile image heuristic
        if chosen is None and html:
            for score,url,kind in extract_img_candidates(html,profile,symbol):
                if score<6:break
                im=download_candidate(session,url)
                if im is not None:
                    chosen=im;source="VIETSTOCK_"+kind;source_url=url;break

        # 3 official website logo / favicon
        if chosen is None and website:
            try:
                wr=get(session,website);whtml=wr.text;final=wr.url
                for score,url,kind in extract_img_candidates(whtml,final,symbol):
                    if score<8:break
                    im=download_candidate(session,url)
                    if im is not None:
                        chosen=im;source="OFFICIAL_"+kind;source_url=url;break
                if chosen is None:
                    for url in extract_icons(whtml,final):
                        im=download_candidate(session,url)
                        if im is not None:
                            chosen=im;source="OFFICIAL_FAVICON";source_url=url;break
            except Exception:pass

        if chosen is not None:
            normalize_and_save(chosen,dest);status="REAL_CANDIDATE"
        else:
            dest.parent.mkdir(parents=True,exist_ok=True);fallback_logo(symbol,dest);status="FALLBACK";source="TICKER_FALLBACK";source_url=""
        row={"symbol":symbol,"status":status,"source":source,"source_url":source_url,"website_url":website,"local_path":str(dest)};rows.append(row)
        write_csv(manifest_path,rows,["symbol","status","source","source_url","website_url","local_path"])
        print(f"[{idx}/{len(wanted)}] {symbol} {status} {source}");time.sleep(DELAY)

    write_csv(manifest_path,rows,["symbol","status","source","source_url","website_url","local_path"])
    real=sum(r["status"]=="REAL_CANDIDATE" for r in rows);fallback=sum(r["status"]=="FALLBACK" for r in rows)
    print(f"XONG: {len(rows)} logo | real candidate {real} | fallback {fallback}")
    print("Manifest:",manifest_path.resolve())

if __name__=="__main__":main()
