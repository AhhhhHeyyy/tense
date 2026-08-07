"""
把三支 fetch 腳本 + build_data.py 串成一次執行，供排程（cron / GitHub Actions）
每天呼叫一次，重新產生 data/events.json。

有一個限制專門處理：行政院公報 API 只吐「今天」，沒有歷史區間查詢。
唯一能建立起真正歷史的方法，是每天跑的時候把當天結果累積進
data/gazette_archive.json（用 meta_id 去重），而不是每次覆蓋。這支腳本
負責做這個累積動作；隨排程跑得越久，這份存檔涵蓋的歷史就越長——這也是
為什麼「每天更新」對這個資料源來說不是選配，是唯一的資料來源方式。

用法：
  python refresh_data.py [--seed-bill 202110228820000] [--anchor 2026-01-01]
                          [--wiki-article 立法院] [--window-days 5]
"""
import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCRIPTS = ROOT / "scripts"


def run(args):
    print("$", " ".join(str(a) for a in args), file=sys.stderr)
    subprocess.run(args, check=True)


def rolling_weekdays(n: int) -> list[date]:
    """回推到今天為止最近 n 個平日（含今天，若今天是平日）。"""
    days = []
    d = date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def merge_gazette_archive(today_records: list[dict]) -> dict:
    archive_path = DATA / "gazette_archive.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {}
    for rec in today_records:
        if rec.get("meta_id"):
            archive[rec["meta_id"]] = rec
    archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    return archive


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed-bill", default="202110228820000", help="立法列示範事件線的起點議案編號")
    ap.add_argument("--anchor", default="2026-01-01", help="示範事件線的計時錨點")
    ap.add_argument("--line-name", default="食品安全衛生管理法修法（demo線）")
    ap.add_argument("--wiki-article", default="立法院", help="搜尋次數列要頂替的維基百科條目")
    ap.add_argument("--window-days", type=int, default=5, help="顯示範圍：最近 N 個平日")
    args = ap.parse_args()

    window = rolling_weekdays(args.window_days)
    start, end = window[0], window[-1]

    run([sys.executable, SCRIPTS / "fetch_gazette.py",
         "--agency", "行政院", "--out", DATA / "gazette_today.json"])
    today_records = json.loads((DATA / "gazette_today.json").read_text(encoding="utf-8"))
    archive = merge_gazette_archive(today_records)

    window_dates = {d.isoformat() for d in window}
    window_records = [r for r in archive.values() if r.get("date_published") in window_dates]
    (DATA / "gazette_window.json").write_text(
        json.dumps(window_records, ensure_ascii=False, indent=2), encoding="utf-8")

    run([sys.executable, SCRIPTS / "fetch_wikipedia.py", args.wiki_article,
         "--start", start.strftime("%Y%m%d"), "--end", end.strftime("%Y%m%d"),
         "--out", DATA / "wiki_pageviews.json"])

    run([sys.executable, SCRIPTS / "fetch_lyapi.py", args.seed_bill,
         "--anchor", args.anchor, "--name", args.line_name,
         "--out", DATA / "demo_line.json"])

    run([sys.executable, SCRIPTS / "build_data.py",
         "--line", DATA / "demo_line.json",
         "--gazette", DATA / "gazette_window.json",
         "--wikipedia", DATA / "wiki_pageviews.json",
         "--start", start.isoformat(), "--end", end.isoformat(),
         "--out", DATA / "events.json"])

    print(f"完成：{start} ~ {end}，公報存檔累積 {len(archive)} 筆", file=sys.stderr)


if __name__ == "__main__":
    main()
