"""
把 fetch_lyapi.py / fetch_gazette.py 的輸出合併成 viewer.html 要吃的
data/events.json：一個「日期 x 分類」的格狀結構。

分類固定四列：行政、立法、搜尋次數、媒體報導。
每一格是三種狀態之一：
  - "hit"  ：當日有節點，附節點資料
  - "none" ：已查證，當日無事（空心圈）
  - "gap"  ：沒有同尺度公開資料，我們不知道（斜紋）

搜尋次數用維基百科條目瀏覽量頂替 Google Trends——後者沒有官方公開 API，
非官方介面實測兩種方式都被 429 擋掉，機房 IP 常態性封鎖，不適合當每日
自動更新的來源。維基百科瀏覽量量的是「主題頁面的長期關注度」，不是
「當天這則新聞的搜尋量」，訊號跟事件的關聯度是弱的，這點誠實標在
viewer 上，不能包裝成看起來像搜尋量。

原本另外開的「點閱率」（Cofacts analytics.csv）列先拿掉，合併進搜尋次數
的概念底下——兩者都是「公眾關注度」的代理指標，在 Cofacts 資料還被 HF
gated dataset 鎖住、搜尋次數又只有 Wikipedia 弱訊號可用的階段，開兩列
分別放缺口只會讓人以為在講兩件不同的事。等你在 Hugging Face 同意授權、
拿到 token，把 fetch_cofacts.py（還沒寫）接上，再決定要併回搜尋次數列
還是重新拆成獨立列。

媒體報導列目前也固定是 gap：還沒有做「盤點部會新聞稿結構化來源」那項
好上手任務，沒有可信的自動來源，寧可留白也不假裝有資料。

用法：
  python build_data.py --line data/demo_line.json --gazette data/gazette_today.json \
      --wikipedia data/wiki_pageviews.json \
      --start 2026-08-03 --end 2026-08-07 --out data/events.json
"""
import argparse
import json
from datetime import datetime, timedelta


def daterange(start: str, end: str) -> list[str]:
    d0 = datetime.fromisoformat(start)
    d1 = datetime.fromisoformat(end)
    days = []
    d = d0
    while d <= d1:
        days.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return days


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_legislative_row(dates: list[str], line: dict) -> dict:
    all_nodes = line["nodes"]
    date_by_index = {n["node_index"]: n["date"] for n in all_nodes}
    dates_in_view = set(dates)

    def neighbor(index):
        target_date = date_by_index.get(index)
        if not target_date:
            return None
        return {
            "node_index": index,
            "date": target_date,
            "in_range": target_date in dates_in_view,
        }

    by_date = {}
    for node in all_nodes:
        by_date.setdefault(node["date"], []).append(node)

    row = {}
    for d in dates:
        nodes_today = by_date.get(d)
        if nodes_today:
            enriched = [
                {
                    **n,
                    "prev_node": neighbor(n["node_index"] - 1),
                    "next_node": neighbor(n["node_index"] + 1),
                }
                for n in nodes_today
            ]
            row[d] = {"state": "hit", "line_name": line["line_name"], "nodes": enriched}
        else:
            row[d] = {"state": "none", "note": "已查議事日程，本線當日無進度"}
    return row


def build_admin_row(dates: list[str], gazette_records: list[dict]) -> dict:
    by_date = {}
    for rec in gazette_records:
        if rec.get("date_published"):
            by_date.setdefault(rec["date_published"], []).append(rec)

    row = {}
    for d in dates:
        recs = by_date.get(d)
        if recs:
            row[d] = {"state": "hit", "records": recs}
        else:
            # downloadXML.jsp 只吐「今天」，非今天一律誠實標成 gap，不假裝查過
            row[d] = {"state": "gap", "note": "公報 API 只提供當日資料，非今日區間標為缺口"}
    return row


def build_placeholder_row(dates: list[str], note: str) -> dict:
    return {d: {"state": "gap", "note": note} for d in dates}


def build_search_row(dates: list[str], pageview_records: list[dict]) -> dict:
    by_date = {r["date"]: r for r in pageview_records}

    row = {}
    for d in dates:
        rec = by_date.get(d)
        if rec:
            row[d] = {"state": "hit", "article": rec["article"], "views": rec["views"]}
        else:
            # Wikimedia pageviews 有 1-2 天處理延遲，近期日期常常還沒有資料
            row[d] = {"state": "gap", "note": "維基百科瀏覽量有處理延遲，這天資料還沒生成"}
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--line", required=True, help="fetch_lyapi.py 輸出的事件線 JSON")
    ap.add_argument("--gazette", required=True, help="fetch_gazette.py 輸出的公報 JSON")
    ap.add_argument("--wikipedia", required=True, help="fetch_wikipedia.py 輸出的瀏覽量 JSON")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    dates = daterange(args.start, args.end)
    line = load(args.line)
    gazette_records = load(args.gazette)
    pageview_records = load(args.wikipedia)

    events = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dates": dates,
        "rows": {
            "行政": {
                "source": "行政院公報（data.gov.tw dataset 5959）",
                "cells": build_admin_row(dates, gazette_records),
            },
            "立法": {
                "source": "LYAPI ly.govapi.tw/v2",
                "cells": build_legislative_row(dates, line),
            },
            "搜尋次數": {
                "source": "維基百科瀏覽量（Wikimedia Pageviews API，頂替被封鎖的 Google Trends；Cofacts 點閱率待 HF token 後再併入或拆列）",
                "caveat": "量的是主題頁面長期關注度，不是當日新聞搜尋量，與事件關聯度弱",
                "cells": build_search_row(dates, pageview_records),
            },
            "媒體報導": {
                "source": "尚無結構化來源（good-first-issue 待盤點）",
                "cells": build_placeholder_row(dates, "尚未盤點部會新聞稿結構化來源"),
            },
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"寫入 {args.out}")


if __name__ == "__main__":
    main()
