#!/usr/bin/env python3
"""
DiscussArchive.md → iCal 変換スクリプト
- 毎日 feed.ical に追記
- 月が変わったら Archive/{yyyy}-{mm}.ical に移動
"""

import re
import os
from datetime import date, timedelta
import urllib.request

ARCHIVE_URL = (
    "https://raw.githubusercontent.com/htvoffcial/htvoffcial"
    "/refs/heads/main/DiscussArchive.md"
)

# ---------------------------------------------------------------------------
# 取得 & パース
# ---------------------------------------------------------------------------

def fetch_archive() -> str:
    print(f"Fetching: {ARCHIVE_URL}")
    with urllib.request.urlopen(ARCHIVE_URL) as resp:
        return resp.read().decode("utf-8")


def parse_discussions(content: str) -> dict[str, list[tuple[str, str, str]]]:
    """
    Returns: { "2026-03-10": [("タイトル", "URL", "説明"), ...], ... }
    """
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
                title = item_match.group(1)
                url   = item_match.group(2)
                # 次行が説明（インデント + "- "）なら取り込む
                desc = ""
                if i + 1 < len(lines):
                    desc_match = re.match(r"^\s+- (.+)", lines[i + 1])
                    if desc_match:
                        raw = desc_match.group(1)
                        # "…" などのトリム
                        desc = raw.replace('"…"', "").strip()
                        i += 1  # 説明行も消費
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


def get_uid_from_vevent(vevent: str) -> str:
    for line in vevent.split("\n"):
        if line.startswith("UID:"):
            return line[4:].strip()
    return ""


def get_month_from_vevent(vevent: str) -> str:
    """VEVENT から 'YYYY-MM' を返す"""
    for line in vevent.split("\n"):
        if line.startswith("DTSTART"):
            val = line.split(":")[-1].strip()  # e.g. 20260310
            return f"{val[:4]}-{val[4:6]}"
    return ""


def get_uids(vevents: list[str]) -> set[str]:
    return {get_uid_from_vevent(v) for v in vevents}


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
# メイン処理
# ---------------------------------------------------------------------------

def main() -> None:
    today      = date.today()
    today_str  = today.strftime("%Y-%m-%d")
    this_month = today.strftime("%Y-%m")

    # ① DiscussArchive.md を取得・パース
    content     = fetch_archive()
    discussions = parse_discussions(content)

    print(f"Today: {today_str}  |  This month: {this_month}")
    print(f"Parsed dates in archive: {sorted(discussions)}")

    # ② 既存の feed.ical を読み込み
    feed_path      = "feed.ical"
    existing_ical  = read_file(feed_path)
    all_vevents    = extract_vevents(existing_ical)

    # ③ 先月以前のイベントを Archive/{yyyy-mm}.ical へ移動
    archive_map: dict[str, list[str]] = {}
    keep_vevents: list[str] = []

    for vevent in all_vevents:
        month = get_month_from_vevent(vevent)
        if month and month < this_month:           # 先月以前
            archive_map.setdefault(month, []).append(vevent)
        else:
            keep_vevents.append(vevent)

    for month, old_vevents in archive_map.items():
        archive_path   = f"Archive/{month}.ical"
        existing_arch  = read_file(archive_path)
        arch_vevents   = extract_vevents(existing_arch)
        arch_uids      = get_uids(arch_vevents)

        to_add = [v for v in old_vevents if get_uid_from_vevent(v) not in arch_uids]
        merged = arch_vevents + to_add

        write_file(archive_path, build_ical(merged))
        print(f"📦 Archived {len(to_add)} events → {archive_path} (total: {len(merged)})")

    # ④ 本日分の新規イベントを追記
    current_uids = get_uids(keep_vevents)
    new_vevents: list[str] = []

    if today_str in discussions:
        for title, url, desc in discussions[today_str]:
            uid = make_uid(today_str, url)
            if uid not in current_uids:
                new_vevents.append(make_vevent(today_str, title, url, desc))
                print(f"✅ New event: {title}")
            else:
                print(f"⏭️  Already exists: {title}")
    else:
        print(f"ℹ️  No discussions found for {today_str}")

    # ⑤ feed.ical を書き出し
    final_vevents = keep_vevents + new_vevents
    write_file(feed_path, build_ical(final_vevents))

    print(
        f"\n🎉 Done! feed.ical: {len(final_vevents)} events "
        f"({len(new_vevents)} new, {len(archive_map)} month(s) archived)"
    )


if __name__ == "__main__":
    main()
