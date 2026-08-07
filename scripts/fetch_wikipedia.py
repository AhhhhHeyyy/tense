"""
抓維基百科條目瀏覽量（Wikimedia Pageviews API），當「搜尋次數」列的替代來源。

背景：Google Trends 沒有官方公開 API。用非官方介面測過兩種方式
（裸 request、pytrends 函式庫）都在第一次請求就被 429 擋掉，機房 IP
被 Google 封鎖，不適合當每日自動更新的資料來源。

Wikimedia Pageviews 是官方公開 API，免金鑰、無流量限制，已實測可用。

但要誠實：這量的是「這個主題頁面的長期關注度」，不是「當天這則新聞的
搜尋量」。同一件事如果沒有自己的維基條目（多數單一新聞事件都沒有），
只能掛在上位主題條目（例如「立法院」「食品安全衛生管理法」）底下，
訊號會被稀釋，跟事件本身的關聯度是弱的。這點要在 viewer 上如實標註，
不能讓它看起來像「這篇新聞被搜尋了幾次」。

用法：
  python fetch_wikipedia.py <條目名稱> --start YYYYMMDD --end YYYYMMDD [--out out.json]
  例：python fetch_wikipedia.py 立法院 --start 20260803 --end 20260807
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

API_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def fetch_pageviews(article: str, start: str, end: str, project: str = "zh.wikipedia") -> list[dict]:
    encoded = urllib.parse.quote(article, safe="")
    url = f"{API_BASE}/{project}/all-access/all-agents/{encoded}/daily/{start}/{end}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "tense-project/0.1 (g0v civic tech prototype)"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise

    out = []
    for item in data.get("items", []):
        # timestamp 格式 "2026080100" -> "2026-08-01"
        ts = item["timestamp"]
        date = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
        out.append({
            "date": date,
            "article": item["article"],
            "views": item["views"],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("article", help="維基百科條目名稱，例如 立法院")
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    records = fetch_pageviews(args.article, args.start, args.end)
    output = json.dumps(records, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"寫入 {args.out}（{len(records)} 天，條目「{args.article}」）", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
