#!/usr/bin/env python3
"""
DiscussArchive.md の全データを一括処理するバックフィルスクリプト。
- 当月分  → feed.ical
- 過去月分 → Archive/{yyyy-mm}.ical
既存ファイルがある場合は UID で重複チェックしてマージします。
"""

import re
import os
import urllib.request
from datetime import date, timedelta
from collections import defaultdict

ARCHIVE_URL = (
    "https://raw.githubusercontent.com/htvoffcial/htvoffcial"
    "/refs/heads/main/DiscussArchive.md"
)

# ---------------------------------------------------------------------------
# 取得
# ---------------------------------------------------------------------------

def fetch_archive() -> str:
    print(f"📡 Fetching: {ARCHIVE_URL}")
    with urllib.request.urlopen(ARCHIVE_URL) as resp:
        return resp.read().decode("utf-8")

# ---------------------------------------------------------------------------
# パース
# ---------------------------------------------------------------------------

def parse_discussions(content: str) -> dict[str, list[tuple[str, str, str]]]:
    result: dict[str, list[tuple[str, str, str]]] = {}
    current_date: str | None = None
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        date_match = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
        if date_match:
            current_date = date_match.group(1)
            result.setdefault(current_date, [])
            i += 1
            continue
        if current_date:
            item_match = re.match(r"^- \[(.+?)\]\((https?://[^\)]+)\)", line)
            if item_match:
                title, url = item_match.group(1), item_match.group(2)
                desc = ""
                if i + 1 < len(lines):
                    dm = re.match(r"^\s+- (.+)", lines[i + 1])
                    if dm:
                        desc = dm.group(1).replace('"…"', "").strip()
                        i += 1
                result[current_date].append((title, url, desc))
        i += 1
    return result

# ---------------------------------------------------------------------------
# iCal ユーティリティ
# ---------------------------------------------------------------------------

ICAL_HEADER = "\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//htvoffcial//DiscussArchive//JA",
    "CALSCALE:GREGORIAN",
    "X-WR-CALNAME:htvoffcial Discussions",
    "X-WR-TIMEZONE:Asia/Tokyo",
])
ICAL_FOOTER = "END:VCALENDAR"


def ical_escape(text: str) -> str:
    for ch, esc in [("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")]:
        text = text.replace(ch, esc)
    return text


def make_uid(date_str: str, url: str) -> str:
    discussion_id = url.rstrip("/").split("/")[-1]
    return f"discussion-{discussion_id}-{date_str}@htvoffcial"


def make_vevent(date_str: str, title: str, url: str, desc: str = "") -> str:
    d = date.fromisoformat(date_str)
    dtstart = d.strftime("%Y%m%d")
    dtend   = (d + timedelta(days=1)).strftime("%Y%m%d")
    uid     = make_uid(date_str, url)
    lines = [
        "BEGIN:VEVENT",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{ical_escape(title)}",
        f"URL:{url}",
        f"UID:{uid}",
    ]
    if desc:
        lines.append(f"DESCRIPTION:{ical_escape(desc)}")
    lines.append("END:VEVENT")
    return "\n".join(lines)


def build_ical(vevents: list[str]) -> str:
    parts = [ICAL_HEADER] + vevents + [ICAL_FOOTER]
    return "\n".join(parts) + "\n"


def extract_vevents(ical_content: str | None) -> list[str]:
    if not ical_content:
        return []
    vevents, current, in_event = [], [], False
    for line in ical_content.split("\n"):
        stripped = line.strip()
        if stripped == "BEGIN:VEVENT":
            in_event, current = True, [line]
        elif stripped == "END:VEVENT":
            current.append(line)
            vevents.append("\n".join(current))
            in_event = False
        elif in_event:
            current.append(line)
    return vevents


def get_uid(vevent: str) -> str:
    for line in vevent.split("\n"):
        if line.startswith("UID:"):
            return line[4:].strip()
    return ""


def read_file(path: str) -> str | None:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    today_str  = date.today().strftime("%Y-%m-%d")
    this_month = date.today().strftime("%Y-%m")

    # ① 全データ取得
    content     = fetch_archive()
    discussions = parse_discussions(content)

    all_dates = sorted(discussions)
    print(f"\n📚 アーカイブ内の日付: {len(all_dates)} 日分")
    for d in all_dates:
        count = len(discussions[d])
        marker = " 👈 当月" if d.startswith(this_month) else ""
        print(f"   {d}: {count} 件{marker}")

    # ② 月ごとに VEVENT を仕分け
    #    { "2026-03": [vevent, ...], "2026-02": [...], ... }
    month_map: dict[str, list[str]] = defaultdict(list)

    total_items = 0
    for date_str in all_dates:
        month = date_str[:7]  # "YYYY-MM"
        for title, url, desc in discussions[date_str]:
            month_map[month].append(make_vevent(date_str, title, url, desc))
            total_items += 1

    print(f"\n🗂️  月別内訳:")
    for m in sorted(month_map):
        label = "feed.ical" if m == this_month else f"Archive/{m}.ical"
        print(f"   {m}: {len(month_map[m])} 件 → {label}")

    # ③ 各ファイルに書き出し（既存とマージ）
    written_files: list[str] = []

    for month, new_vevents in sorted(month_map.items()):
        if month == this_month:
            out_path = "feed.ical"
        else:
            out_path = f"Archive/{month}.ical"

        # 既存ファイルを読み込んで重複 UID を除外
        existing      = read_file(out_path)
        existing_vevents = extract_vevents(existing)
        existing_uids    = {get_uid(v) for v in existing_vevents}

        to_add = [v for v in new_vevents if get_uid(v) not in existing_uids]
        merged = existing_vevents + to_add

        write_file(out_path, build_ical(merged))
        written_files.append(out_path)

        skipped = len(new_vevents) - len(to_add)
        skip_note = f" (既存 {skipped} 件スキップ)" if skipped else ""
        print(f"   ✅ {out_path}: {len(merged)} 件書き込み{skip_note}")

    # ④ サマリー
    print(f"""
╔══════════════════════════════════════════╗
║  🎉 バックフィル完了！                    ║
║  合計 {total_items:>3} 件 / {len(month_map):>2} ヶ月分を処理しました ║
╚══════════════════════════════════════════╝
書き出したファイル:
""")
    for f in written_files:
        size = os.path.getsize(f)
        print(f"   📄 {f}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
