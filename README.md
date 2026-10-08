# 真戦データ帳

信長の野望 真戦の武将・戦法データと、攻略ツールへのリンクをまとめた総合ページ。

https://ry12346.github.io/

| ページ | 内容 |
|---|---|
| `index.html` | トップ（ツールへのリンク） |
| `generals.html` | 武将一覧（Lv1・成長値・任意レベルの値、勢力、コスト、固有戦法、凸別特性） |
| `tactics.html` | 戦法一覧（種別・品質・発動確率・効果・兵種制限） |
| `exp.html` | 戦法経験値の計算、その他の資料 |

## データの更新

ゲームのアップデートで武将・戦法が増えたら、次の2つを実行してコミットする。

```bash
python scripts/fetch_sources.py
python scripts/build_data.py
```

- `fetch_sources.py` は外部ページを `.cache/` に保存する（取得済みのものは再取得しない。`--force` で全件取り直し）
- `build_data.py` は `.cache/` から `data/heroes.json` `data/skills.json` `data/meta.json` を作る。最後に、名前が突き合わなかったものを表示するので、表記ゆれは `ALIASES` に追加する

`data/kana.json` は読みがなの手入力表。自動取得した読みより優先される。戦法の読みは公式データにも無いので、誤りを見つけたらここに書いて `build_data.py` を再実行する。「要確認」に入れた名前は一覧で「?」付きになる。

`data/official.json` は公式ニュース（シーズン前の「新武将徹底解説」の画像）から読み取った値。武将のLv1・成長値、戦法の発動率・数値・伝授元、設定ファイルにまだ無い戦法（追加戦法）を入れる。自動取得より優先され、`overrides.json` よりは下。

`data/overrides.json` はゲーム内で確認した値（発動率・Lv1→Lv10の数値・読み）。自動取得の値より優先される。

## 一門メンバーの報告を取り込む

1. メンバーは `report.html`（情報提供）で戦法を選び、ゲーム内の値（発動率・数値・入手・伝授元など）を入力して「コピー」した報告文を一門チャットに貼る
2. 集まった報告文をそのまま `reports.txt` などに貼り付けて保存する（何件でも可）
3. 次を実行してコミットする

```bash
python scripts/import_reports.py reports.txt
python scripts/build_data.py
```

登録済みの値と違う報告は上書きせずに一覧表示する。「備考」は自動では反映せず一覧表示するので、内容を見て手で直す。報告の方を採るときは `--overwrite` を付ける。数値の①②…がすべてそろった戦法は、公式の説明文に数値を入れた形で表示され「確認済み」になる。

`data/reference.json`（戦法経験値表など）は手入力。ゲーム内で確かめたら `verified` を `true` にすると「要検証」表示が消える。

## 公式ニュース（自動）

`news.html` は公式サイトのニュースを表示する。GitHub Actions（`.github/workflows/update-news.yml`）が毎日 06:00 JST に `scripts/fetch_news.py` を実行し、新着があれば `data/news.json`（一覧）・`data/news/{id}.json`（本文）・`data/news_text.json`（検索用）をコミットする。手で動かすときは GitHub の Actions 画面で「公式ニュースの取り込み」→「Run workflow」。

画像だけの記事（新武将徹底解説、大名録など）の数値をデータに反映するときは、画像を読んで `data/official.json` に入れる。

## 新しいツールを追加する

`assets/site.js` の `TOOLS` に1件足すと、トップページにカードが出る。
