# htvoffcial_cal 📅

[htvoffcial](https://github.com/htvoffcial/htvoffcial) の Discussions をカレンダー形式（iCalendar）で配信・アーカイブするプロジェクトです。

## 🌟 特徴

- **自動更新**: GitHub Actions により、毎日 Discussions の内容が `feed.ical` に書き込まれます。
- **AIによる要約**: 「体操のお兄さん（Gemmaモデル）」が要約した日々の活動記録をカレンダー上で確認できます。
- **アーカイブ**: 月をまたいだデータは `Archive/` ディレクトリに自動的に整理・保存されます。

## 📅 カレンダーの購読方法

お手持ちのカレンダーアプリ（Googleカレンダー、Appleカレンダー、Outlookなど）で以下のURLを読み込むことで、Discussions の更新をカレンダー上で受け取ることができます。

**メインフィード:**
`https://raw.githubusercontent.com/htvoffcial/htvoffcial_cal/main/feed.ical`

**体操のお兄さん専用:**
`https://raw.githubusercontent.com/htvoffcial/htvoffcial_cal/main/oniisan.ical`

## 📁 ディレクトリ構成

- `feed.ical`: 直近の Discussions の内容が含まれるメインのカレンダーファイル。
- `oniisan.ical`: 体操のお兄さん（AI）によるメッセージが含まれるカレンダーファイル。
- `Archive/`: 過去の月ごとのカレンダーデータが保存されています。
- `.github/workflows/`: カレンダーの自動生成とアーカイブを行う GitHub Actions が定義されています。

## 🛠 仕組み

1. GitHub Actions が毎日定刻（JST 00:05頃）に実行されます。
2. `.github/scripts/update_ical.py` が `htvoffcial/htvoffcial` から最新の Discussions を取得します。
3. 取得した内容を `feed.ical` および `oniisan.ical` に反映し、コミットします。
4. 月が変わるタイミングで、古いデータは `Archive/YYYY-MM.ical` に移動されます。

---
Created by [@htvoffcial](https://github.com/htvoffcial)
