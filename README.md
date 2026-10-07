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

`data/reference.json`（戦法経験値表など）は手入力。ゲーム内で確かめたら `verified` を `true` にすると「要検証」表示が消える。

## 新しいツールを追加する

`assets/site.js` の `TOOLS` に1件足すと、トップページにカードが出る。
