"""一門メンバーの報告文を data/overrides.json に取り込む。

  python scripts/import_reports.py reports.txt     # 報告文を貼ったテキストファイル
  python scripts/import_reports.py reports.txt --overwrite   # 既存の値と違うときは上書き
  python scripts/build_data.py                      # その後サイトのデータを作り直す

報告文の形式（情報提供ページの「コピー」で作られるもの。手書きでもよい）:

  【真戦データ報告】
  戦法：鬼義重
  発動率：35%
  ①：32.5→65
  ②：107→214
  ③：7.5→15
  読み：おによししげ
  入手：伝授戦法
  伝授元：〇〇・〇〇        （事件戦法は「交換：〇〇・〇〇」）
  備考：その他の訂正（自動では反映しない。一覧に表示する）
  報告者：〇〇

・1つのファイルに何件貼ってもよい（「戦法：」の行で区切る）
・空欄の行は無視する。①②は「1：」「(1)」でも可。区切りは「：」「:」どちらでも可
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "data" / "overrides.json"
SKILLS = ROOT / "data" / "skills.json"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def parse(text: str):
    reports, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)\s*[：:]\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        key_n = unicodedata.normalize("NFKC", key).strip("()（） ")
        if key == "戦法":
            cur = {"戦法": val, "数値": {}}
            reports.append(cur)
        elif cur is None or not val:
            continue
        elif key in CIRCLED:
            cur["数値"][str(CIRCLED.index(key) + 1)] = val
        elif key_n.isdigit():
            cur["数値"][key_n] = val
        elif key in ("発動率", "読み", "報告者", "入手", "伝授元", "交換", "備考"):
            cur["伝授元" if key == "交換" else key] = val
    return reports


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    overwrite = "--overwrite" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    text = Path(args[0]).read_text(encoding="utf-8")
    reports = parse(text)
    data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    tactics = data.setdefault("戦法", {})
    known = {s["name"]: s for s in json.loads(SKILLS.read_text(encoding="utf-8"))}

    added, conflicts, unknown, notes = 0, [], [], []
    for r in reports:
        name = r["戦法"]
        if name not in known:
            unknown.append(name)
            continue
        slots = {str(x["n"]) for x in known[name]["slots"]}
        entry = tactics.setdefault(name, {})
        who = r.get("報告者", "")
        fields = [("発動率", r.get("発動率"))] + [(f"数値{n}", v) for n, v in r["数値"].items()]
        fields += [("読み", r.get("読み")), ("入手", r.get("入手")), ("伝授元", r.get("伝授元"))]
        if r.get("備考"):
            notes.append(f"{name}：{r['備考']}（{who}）")
            entry.setdefault("備考", []).append(r["備考"] + (f"（{who}）" if who else ""))
        for field, val in fields:
            if not val:
                continue
            if field.startswith("数値"):
                n = field[2:]
                if n not in slots:
                    conflicts.append(f"{name} {CIRCLED[int(n) - 1]}：この戦法に{CIRCLED[int(n) - 1]}の欄はありません（{who}）")
                    continue
                box, k = entry.setdefault("数値", {}), n
            else:
                box, k = entry, field
            old = box.get(k)
            if old and norm_val(old) != norm_val(val):
                label = field if not field.startswith("数値") else CIRCLED[int(k) - 1]
                conflicts.append(f"{name} {label}：登録済み「{old}」と報告「{val}」が違います（{who}）")
                if not overwrite:
                    continue
            if old != val:
                box[k] = val
                added += 1

    OVERRIDES.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"報告 {len(reports)} 件を読み込み、{added} 項目を反映しました。")
    if unknown:
        print("戦法名が見つからなかった報告:", unknown)
    if conflicts:
        print("値の食い違い（" + ("上書きしました" if overwrite else "登録済みの値を残しました。報告を採るなら --overwrite") + "）:")
        for c in conflicts:
            print("  " + c)
    if notes:
        print("備考（自動では反映しません。内容を見て手で直してください）:")
        for n in notes:
            print("  " + n)
    print("続けて python scripts/build_data.py を実行してください。")


def norm_val(v: str) -> str:
    v = unicodedata.normalize("NFKC", str(v))
    return re.sub(r"[\s%]|->|～|〜|~", lambda m: "→" if m.group(0) in ("->", "～", "〜", "~") else "", v)


if __name__ == "__main__":
    main()
