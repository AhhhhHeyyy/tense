"""
產生議題目錄頁要用的 data/catalog.json。

背景：spec/multi_line_rollout.md Phase 2 要求新增「議題目錄頁」，每條線要能
看到主題名稱、追蹤中的法案數、日期範圍、分類分佈快照、最後更新時間、選線
判准的連結——不是坑主腦中的標準，要能被檢視。

這支腳本不重新打 API，只讀現有 build_data.py 產出的 events*.json，統計出
目錄頁要顯示的摘要欄位。跟 build_data.py 一樣走「跑一次腳本、產出 JSON、
git commit」這個沒有常駐後端的模式（見 spec/multi_line_rollout.md 2 節）。

選線判准連結：Phase 2 規格要求投給整個開放國會社群共用、獨立於本專案，
但目前那份公開文件還沒有人寫、也還沒有這篇文件本身的公開網址。在那件事
完成之前，這裡誠實指向本專案 repo 內的 spec/multi_line_rollout.md，不假裝
已經有一個外部公開頁面可以連——沒有的東西不要編網址出來騙讀者。

用法：
  python build_catalog.py --entry data/events.json "這週即時資料" auto \
      --entry data/events_military_budget.json "軍購特別預算案聯席會議（2026/05/25–29，真實歷史資料）" static \
      --entry data/events_multi_demo.json "兩線同框比較（食安修法線＋軍購特別預算線，2026/05/25–08/21）" static \
      --out data/catalog.json

MODE 是 auto 或 static：
- auto：資料在 refresh_data.py 的每日排程路徑上，會自己跟著更新，不用人管。
- static：資料是某次手動跑 fetch 腳本產生的快照，不在每日排程覆蓋範圍內，
  「最後更新」那個日期不會自己往前走——要更新只能有人手動重跑對應的
  fetch 腳本。目錄頁需要誠實標出這個差別，不能讓兩種資料看起來一樣新。
"""
import argparse
import json

STATIC_NOTE = ("此卡片資料是某次手動執行 fetch 腳本產生的快照，不在 "
               "refresh_data.py 的每日排程路徑上——「最後更新」不會自己更新，"
               "要更新內容必須有人手動重跑對應腳本。")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def summarize(path: str, label: str, is_static: bool) -> dict:
    d = load(path)
    legis = d["rows"]["立法"]["cells"]

    bill_nos = set()
    bill_type_counts: dict[str, int] = {}
    has_meeting = False

    for cell in legis.values():
        if cell.get("state") != "hit":
            continue
        for n in cell["nodes"]:
            if n.get("kind") == "bill":
                bill_nos.add(n.get("bill_no"))
                bt = n.get("bill_type") or "未分類"
                bill_type_counts[bt] = bill_type_counts.get(bt, 0) + 1
            elif n.get("kind") == "meeting":
                has_meeting = True

    # 分類分佈快照用「議案」筆數而非節點筆數算，一個議案通常對應多個節點（多個流程階段）
    seen_bill_type_by_no: dict[str, str] = {}
    for cell in legis.values():
        if cell.get("state") != "hit":
            continue
        for n in cell["nodes"]:
            if n.get("kind") == "bill" and n.get("bill_no") not in seen_bill_type_by_no:
                seen_bill_type_by_no[n["bill_no"]] = n.get("bill_type") or "未分類"
    snapshot_counts: dict[str, int] = {}
    for bt in seen_bill_type_by_no.values():
        snapshot_counts[bt] = snapshot_counts.get(bt, 0) + 1
    snapshot_parts = [f"{c} {bt}" for bt, c in snapshot_counts.items()]
    if has_meeting:
        snapshot_parts.append("1 委員會聯席會議")
    category_snapshot = "・".join(snapshot_parts) if snapshot_parts else "（此區間無節點）"

    return {
        "label": label,
        "data_path": path,
        "bill_count": len(bill_nos),
        "has_meeting": has_meeting,
        "date_start": d["dates"][0],
        "date_end": d["dates"][-1],
        "category_snapshot": category_snapshot,
        "generated_at": d.get("generated_at"),
        "selection_rationale_note": "選線判准目前記錄於 spec/multi_line_rollout.md（Phase 2 規劃要求另外整理成獨立公開文件，投給開放國會社群，尚未完成）",
        "selection_rationale_path": "spec/multi_line_rollout.md",
        "is_static": is_static,
        "static_note": STATIC_NOTE if is_static else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entry", nargs=3, action="append", metavar=("PATH", "LABEL", "MODE"),
                     required=True,
                     help="一筆目錄項目：events json 路徑 + 顯示用標籤 + auto/static，可重複")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for _, _, mode in args.entry:
        if mode not in ("auto", "static"):
            ap.error(f"MODE 必須是 auto 或 static，收到：{mode!r}")

    catalog = {
        "entries": [summarize(path, label, mode == "static") for path, label, mode in args.entry],
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"寫入 {args.out}（{len(catalog['entries'])} 筆）")


if __name__ == "__main__":
    main()
