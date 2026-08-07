"""
抓「委員會聯席會議」節點——用會議代碼當結構化錨點，取代還沒查到的
議案編號。

背景：115年度軍購特別預算案的委員會初審，LYAPI 沒有把它跟正式議案編號
建立關聯（/meets/{id}/bills 回傳 0 筆，查證過是資料源本身的缺口，不是
查詢方法錯）。但這場聯席會議自己有明確、可驗證的會議代碼，而且財政部、
國防部、行政院主計總處回覆的公文/簡報都結構化掛在同一場會議底下——
用會議代碼當錨點一樣是「規則決定，不是人決定」，跟共筆〈不靠人排線〉
的精神一致，只是錨點從議案編號換成會議代碼。

限制：這個做法只對「有正式聯席審查會議」的事件好用。沒有排審、只是
部會單獨發新聞稿的行政行為，沒有會議代碼可掛，還是得回到零散來源，
不是這支腳本能解的。

用法：
  python fetch_meeting.py "聯席會議-11-5-20,35-1" --out out.json
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

API_BASE = "https://ly.govapi.tw/v2"


def _get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "tense-project/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_meeting(meeting_code: str) -> dict:
    encoded = urllib.parse.quote(meeting_code, safe="")
    return _get(f"/meets/{encoded}")["data"]


def _extract_items(entry: dict) -> list[dict]:
    """把一個「議事網資料」條目裡的附件＋連結攤平成同一種格式，保留在各自日期底下。"""
    items = []
    for att in entry.get("附件", []):
        if att.get("連結"):
            items.append({"title": att.get("標題"), "url": att.get("連結"), "format": att.get("格式")})
    for link in entry.get("連結", []):
        if link.get("連結"):
            items.append({"title": link.get("標題"), "url": link.get("連結"), "format": link.get("類型")})
    return items


def build_meeting_node(meeting_code: str) -> dict:
    m = get_meeting(meeting_code)

    committees = m.get("委員會代號:str", [])

    # 議事網資料的日期跟會議資料的日期用同一個「日期」欄位對齊，
    # 一場會議橫跨多天時，附件通常只掛在提交當天，不是每天都重複列。
    items_by_date: dict[str, list[dict]] = {}
    for entry in m.get("議事網資料", []):
        for d in entry.get("日期", []):
            # 格式「115年05月25日 (一) 09:00-17:30」，只取民國年月日轉西元
            roc_match = d.split(" ")[0]
            items_by_date.setdefault(roc_match, []).extend(_extract_items(entry))

    sessions = []
    for s in m.get("會議資料", []):
        date_iso = s.get("日期")
        roc_year = int(date_iso[:4]) - 1911 if date_iso else None
        roc_key = f"{roc_year}年{date_iso[5:7]}月{date_iso[8:10]}日" if date_iso else None
        sessions.append({
            "date": date_iso,
            "time_range": s.get("會議時間區間"),
            "location": s.get("會議地點"),
            "agenda": s.get("會議事由"),
            "convener": s.get("委員會召集委員"),
            "ppg_url": s.get("ppg_url"),
            "attachments": items_by_date.get(roc_key, []),
        })

    dates = sorted({s["date"] for s in sessions if s.get("date")})

    return {
        "meeting_code": meeting_code,
        "meeting_title": m.get("會議標題"),
        "committees": committees,
        "dates": dates,
        "sessions": sessions,
        "gazette_url": (m.get("議事錄") or {}).get("ppg_url"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("meeting_code", help='會議代碼，例如 "聯席會議-11-5-20,35-1"')
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    node = build_meeting_node(args.meeting_code)
    output = json.dumps(node, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        att_count = sum(len(s["attachments"]) for s in node["sessions"])
        print(f"寫入 {args.out}（{len(node['sessions'])} 場次，{att_count} 個附件）", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
