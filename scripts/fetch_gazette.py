"""
抓行政院公報開放資料（data.gov.tw dataset 5959），篩出「行政」列要用的事件。

已驗證：https://gazette.nat.gov.tw/egFront/OpenData/downloadXML.jsp
  - 免金鑰、免登入，200 OK 直接吐 XML
  - 每個工作日下午 6:30 更新「當日已刊登」的公報
  - 只有「今天」，沒有歷史區間查詢——這點跟 LYAPI 不同，要注意

覆蓋範圍：法規、行政規則、公告、送達、處分、特載（總統文告及院長談話）、
轉載、專載（院會院長提示、決定、決議事項）等 8 大類。這是「正式行政行為」，
不包含記者會口頭發言——那塊共筆裡本來就標「未串線」，這支腳本不處理。

用法：
  python fetch_gazette.py [--agency 行政院] [--out out.json]
"""
import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

DOWNLOAD_URL = "https://gazette.nat.gov.tw/egFront/OpenData/downloadXML.jsp"

_ROC_DATE_RE = re.compile(r"中華民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日")


def roc_to_iso(roc_date: str) -> str | None:
    """「中華民國115年8月7日」 -> "2026-08-07" """
    m = _ROC_DATE_RE.search(roc_date or "")
    if not m:
        return None
    year, month, day = (int(x) for x in m.groups())
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def fetch_records() -> list[dict]:
    req = urllib.request.Request(DOWNLOAD_URL, headers={"User-Agent": "tense-project/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    records = []
    for rec in root.findall("Record"):
        def text(tag):
            el = rec.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        records.append({
            "meta_id": text("MetaId"),
            "gazette_id": text("GazetteId"),
            "title": text("Title"),
            "agency": text("PubGovName"),
            "undertake_agency": text("UndertakeGov"),
            "category": text("Doc_Style_LName"),
            "chapter": text("Chapter"),
            "date_published_roc": text("Date_Published"),
            "date_published": roc_to_iso(text("Date_Published")),
            "url": text("PreviewStageURL"),
        })
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agency", default=None, help="只保留 agency 欄位包含此字串的記錄，例如 行政院")
    ap.add_argument("--out", default=None, help="輸出 JSON 檔路徑，預設印到 stdout")
    args = ap.parse_args()

    records = fetch_records()
    if args.agency:
        records = [r for r in records if args.agency in r["agency"]]

    output = json.dumps(records, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"寫入 {args.out}（{len(records)} 筆，篩選條件 agency={args.agency!r}）", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
