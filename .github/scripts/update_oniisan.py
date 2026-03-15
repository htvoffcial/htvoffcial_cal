#!/usr/bin/env python3
"""
README.md の <!-- DISCUSS_COACH_START/END --> ブロックを読み取り
oniisan.ical に追記するスクリプト。

■ 仕様
  - 当月分   → oniisan.ical に蓄積
  - 月をまたいだら前月分を Archive/{yyyy-mm}-oniisan.ical へ移動
  - UID で重複チェック済み → 何度実行しても安全
"""

import re
import os
import urllib.request
from datetime import date, timedelta

README_URL = (
    "https://raw.githubusercontent.com/htvoffcial/htvoffcial"
    "/refs/heads/main/README.md"
)

# ---------------------------------------------------------------------------
# 取得
# ---------------------------------------------------------------------------

def fetch_readme() -> str:
    print(f"📡 Fetching: {README_URL}")
    with urllib.request.urlopen(README_URL) as resp:
        return resp.read().decode("utf-8")

# ---------------------------------------------------------------------------
# パース
# ---------------------------------------------------------------------------

def parse_coach_block(content: str) -> dict | None:
    """
    <!-- DISCUSS_COACH_START --> 〜 <!-- DISCUSS_COACH_END --> を抽出。
    Returns:
        {
          "date": "2026-03-14",   # 対象日（見つからなければ今日）
          "body": "<本文全体>",
          "summary": "<1行目タイトル>",
          "one_liner": "<今日の一言>",
        }
        見つからなければ None
    """
    m = re.search(
        r"<!-- DISCUSS_COACH_START -->(.*?)<!-- DISCUSS_COACH_END -->",
        content,
        re.DOTALL,
    )
    if not m:
        return None

    block = m.group(1).strip()

    # 対象日
    date_match = re.search(r"\*\*対象日（JST）:\*\*\s*(\d{4}-\d{2}-\d{2})", block)
    target_date = date_match.group(1) if date_match else date.today().strftime("%Y-%m-%d")

    # 「今日の一言」を抽出
    one_liner_match = re.search(r"今日の一言[：:]\s*(.+)", block)
    one_liner = one_liner_match.group(1).strip() if one_liner_match else ""

    # SUMMARY: 一言があればそれ、なければデフォルト
    summary = f"🤸 {one_liner}" if one_liner else f"🤸 体操のお兄さんの一言 {target_date}"

    # 本文（Markdownタグ・対象日行 を軽くクリーン）
    body = re.sub(r"^##\s+.+\n?", "", block, flags=re.MULTILINE)  # ## 見出し除去
    body = re.sub(r"\*\*対象日（JST）:\*\*\s*\d{4}-\d{2}-\d{2}\n?", "", body)
    body = body.strip()

    return {
        "date":      target_date,
        "body":      body,
        "summary":   summary,
        "one_liner": one_liner,
    }

# ---------------------------------------------------------------------------
# iCal ユーティリティ
# ---------------------------------------------------------------------------

ICAL_HEADER = "\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//htvoffcial//OniisanCoach//JA",
    "CALSCALE:GREGORIAN",
    "X-WR-CALNAME:体操のお兄さん日報",
    "X-WR-TIMEZONE:Asia/Tokyo",
])
ICAL_FOOTER = "END:VCALENDAR"

# iCal 仕様: 75 オクテットで折り返し
def fold_line(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    result, start = [], 0
    while start < len(encoded):
        chunk = encoded[start:start + (75 if start == 0 else 74)]
        # UTF-8 のマルチバイト境界を壊さないよう末尾をトリム
        while len(chunk) > 0:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        result.append((" " if start > 0 else "") + chunk.decode("utf-8"))
        start += len(chunk)
    return "\r\n".join(result)


def ical_escape(text: str) -> str:
    for ch, esc in [("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")]:
        text = text.replace(ch, esc)
    return text


def make_uid(date_str: str) -> str:
    return f"oniisan-coach-{date_str}@htvoffcial"


def make_vevent(date_str: str, summary: str, description: str) -> str:
    d       = date.fromisoformat(date_str)
    dtstart = d.strftime("%Y%m%d")
    dtend   = (d + timedelta(days=1)).strftime("%Y%m%d")
    uid     = make_uid(date_str)

    lines = [
        "BEGIN:VEVENT",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{ical_escape(summary)}",
        f"DESCRIPTION:{ical_escape(description)}",
        f"UID:{uid}",
        "END:VEVENT",
    ]
    return "\n".join(lines)


def build_ical(vevents: list[str]) -> str:
    return "\n".join([ICAL_HEADER] + vevents + [ICAL_FOOTER]) + "\n"


def extract_vevents(content: str | None) -> list[str]:
    if not content:
        return []
    vevents, current, in_event = [], [], False
    for line in content.split("\n"):
        if line.strip() == "BEGIN:VEVENT":
            in_event, current = True, [line]
        elif line.strip() == "END:VEVENT":
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


def get_month(vevent: str) -> str:
    for line in vevent.split("\n"):
        if line.startswith("DTSTART"):
            v = line.split(":")[-1].strip()
            return f"{v[:4]}-{v[4:6]}"
    return ""


def read_file(path: str) -> str | None:
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    today      = date.today()
    this_month = today.strftime("%Y-%m")
    feed_path  = "oniisan.ical"

    # ① README.md 取得 & パース
    readme  = fetch_readme()
    coach   = parse_coach_block(readme)

    if not coach:
        print("⚠️  DISCUSS_COACH ブロックが見つかりませんでした。スキップします。")
        return

    print(f"\n🤸 お兄さん情報")
    print(f"   対象日  : {coach['date']}")
    print(f"   一言    : {coach['one_liner']}")
    print(f"   本文    : {coach['body'][:60]}…")

    # ② 既存 oniisan.ical を読み込み
    existing     = read_file(feed_path)
    all_vevents  = extract_vevents(existing)

    # ③ 先月以前を Archive へ移動
    archive_map: dict[str, list[str]] = {}
    keep_vevents: list[str] = []

    for v in all_vevents:
        m = get_month(v)
        if m and m < this_month:
            archive_map.setdefault(m, []).append(v)
        else:
            keep_vevents.append(v)

    for month, old_vevents in archive_map.items():
        arch_path    = f"Archive/{month}-oniisan.ical"
        arch_content = read_file(arch_path)
        arch_events  = extract_vevents(arch_content)
        arch_uids    = {get_uid(v) for v in arch_events}

        to_add = [v for v in old_vevents if get_uid(v) not in arch_uids]
        merged = arch_events + to_add
        write_file(arch_path, build_ical(merged))
        print(f"📦 Archive: {arch_path} ({len(merged)} 件)")

    # ④ 今日分を追記（重複チェック）
    current_uids = {get_uid(v) for v in keep_vevents}
    new_uid      = make_uid(coach["date"])

    if new_uid in current_uids:
        print(f"\n⏭️  {coach['date']} 分はすでに存在します。スキップ。")
    else:
        vevent = make_vevent(coach["date"], coach["summary"], coach["body"])
        keep_vevents.append(vevent)
        print(f"\n✅ 追記: {coach['date']} 「{coach['summary']}」")

    # ⑤ 書き出し
    write_file(feed_path, build_ical(keep_vevents))
    print(f"\n🎉 {feed_path} 更新完了！ ({len(keep_vevents)} 件)")


if __name__ == "__main__":
    main()
