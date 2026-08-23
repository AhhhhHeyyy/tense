"""
抓立法院 LYAPI 真實資料，組成「事件線」。

實測發現（2026-08-07）：/v2/bills、/v2/meets 這類清單端點的 query string 篩選
(?提案編號=..., ?法律編號=..., ?議案狀態=... 等) 目前完全沒有作用——不管填什麼值，
total 永遠是全量、filter 永遠是空物件。這點與官方 swagger 文件（narumiruna/ly-mcp
repo 的 swagger.yaml）描述的行為不符。

能正常運作、且本檔案實際採用的是「關聯式」端點：
  - GET /v2/bills/{議案編號}                 單一議案詳情，含完整「議案流程」時間軸
  - GET /v2/bills/{議案編號}/related_bills    同議題的相關議案群組
  - GET /v2/law/{法律編號}/bills              同一部法律的所有相關議案

用法：
  python fetch_lyapi.py <議案編號> [--anchor YYYY-MM-DD] [--out out.json]

議案編號 從何而來：目前清單端點篩選失效，所以還沒有辦法直接用「輸入法律編號/
提案關鍵字」自動找到起點議案編號，得先去 https://ppg.ly.gov.tw/ 手動查一次
起點的議案編號，之後同一條線就能靠 related_bills 自動展開。這正是共筆裡「事件線
編輯」角色要做的事。
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime

API_BASE = "https://ly.govapi.tw/v2"


def _get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "tense-project/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_bill(bill_no: str) -> dict:
    return _get(f"/bills/{bill_no}")["data"]


def get_related_bills(bill_no: str) -> list[dict]:
    data = _get(f"/bills/{bill_no}/related_bills")
    return data.get("bills", [])


def _earliest_date(date_field) -> str | None:
    """議案流程.日期 是陣列（一場會議可能橫跨多天），取最早一天代表這個階段。"""
    if not date_field:
        return None
    if isinstance(date_field, str):
        return date_field
    return sorted(date_field)[0]


def build_line(seed_bill_no: str, anchor_date: str, line_name: str | None = None) -> dict:
    """以 seed_bill_no 為起點，展開同議題全部議案，攤平成一條依時間排序的事件線。

    anchor_date: 這條線的「計時錨點」（clock_anchor），例如特別條例三讀日、
    法案付委日等——由人決定，這是共筆裡〈規格缺口〉那節講的東西，程式不猜。
    """
    seed = get_bill(seed_bill_no)
    related = get_related_bills(seed_bill_no)
    all_bills = [seed] + [b for b in related if b.get("議案編號") != seed_bill_no]

    raw_nodes = []
    for b in all_bills:
        bill_no = b.get("議案編號") or b.get("billNo")
        bill_title = b.get("議案名稱", "")
        bill_url = b.get("url") or f"https://ppg.ly.gov.tw/ppg/bills/{bill_no}/details"
        bill_type = b.get("議案類別")
        proposal_source = b.get("提案來源")
        proposer_unit = b.get("提案單位/提案委員")
        proposers = b.get("提案人") or []
        cosigners = b.get("連署人") or []
        # /bills/{id} 回傳欄位叫「屆」，但 /bills/{id}/related_bills 回傳的精簡版叫「屆期」——
        # 同一個概念兩個端點用不同鍵名，只取「屆」會讓所有 related_bills 展開出來的節點 term 全是 null。
        term = b.get("屆") or b.get("屆期")
        term_session = b.get("會期")
        for stage in b.get("議案流程", []):
            date = _earliest_date(stage.get("日期"))
            if not date:
                continue
            raw_nodes.append({
                "date": date,
                "bill_no": bill_no,
                "bill_title": bill_title,
                "bill_url": bill_url,
                "status": stage.get("狀態"),
                "meeting_code": stage.get("會議代碼"),
                "bill_type": bill_type,
                "proposal_source": proposal_source,
                "proposer_unit": proposer_unit,
                "proposers": proposers,
                "cosigners": cosigners,
                "term": term,
                "term_session": term_session,
            })

    raw_nodes.sort(key=lambda n: n["date"])

    anchor = datetime.fromisoformat(anchor_date)
    nodes = []
    prev_date = None
    for i, n in enumerate(raw_nodes, start=1):
        d = datetime.fromisoformat(n["date"])
        days_since_anchor = (d - anchor).days
        days_since_prev = (d - prev_date).days if prev_date else None
        nodes.append({
            **n,
            "node_index": i,
            "days_since_anchor": days_since_anchor,
            "days_since_prev": days_since_prev,
        })
        prev_date = d

    return {
        "line_name": line_name or seed.get("議案名稱"),
        "line_id": seed_bill_no,
        "seed_bill_no": seed_bill_no,
        "clock_anchor": anchor_date,
        "clock_anchor_note": "起算點由人指定，程式不自動判定——見共筆〈clock_anchor 規格缺口〉",
        "bill_count": len(all_bills),
        "nodes": nodes,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seed_bill_no", help="起點議案編號，例如 202110228820000")
    ap.add_argument("--anchor", required=True, help="計時錨點日期 YYYY-MM-DD")
    ap.add_argument("--name", default=None, help="這條線的顯示名稱")
    ap.add_argument("--out", default=None, help="輸出 JSON 檔路徑，預設印到 stdout")
    args = ap.parse_args()

    line = build_line(args.seed_bill_no, args.anchor, args.name)

    output = json.dumps(line, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"寫入 {args.out}（{len(line['nodes'])} 個節點，來自 {line['bill_count']} 筆議案）", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
