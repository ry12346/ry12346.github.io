""".cache/ の生データから data/*.json を生成する。

  python scripts/fetch_sources.py   # 先に取得
  python scripts/build_data.py

マスタの土台は Qookka 公開設定 cfg.json（IDが主キー）。
ステータス・成長値・数値入り効果文・発動確率は外部ページから名前で突き合わせて補う。
"""
import difflib
import html as htmllib
import unicodedata
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "data"

JST = timezone(timedelta(hours=9))
GRADE = {5: "S", 4: "A", 3: "B", 2: "C", 1: "D"}
DESC_MATCH = 0.7  # 外部の効果文を採用する、公式の説明文との最低類似度（別の効果文は0.5以下、言い回し違いは0.7〜0.85）
MAIN_KINDS = {"主动", "被动", "指挥", "突击", "兵种", "阵法"}
STAT_KEYS = [("武勇", "bu"), ("知略", "chi"), ("統率", "tou"), ("速度", "spd"), ("政務", "sei"), ("魅力", "mi")]

# cfg.json の multi_lang に日本語が無い名前の補正（中国語簡体 → 日本語）
NAME_FIXES = {
    "百战炼磨": "百戦錬磨",
    "千军辟易·拓": "千軍辟易・拓",
    "临时枪之铃": "臨時槍之鈴",
    "士气高扬": "士気高揚",
    "速战": "速戦",
    # multi_lang の訳は「斬り」だが、ゲーム内の名称は「薙ぎ払い」（効果文が一致）
    "挥砍": "薙ぎ払い",
}


def text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[☀-➿\U0001f300-\U0001faff️]", "", htmllib.unescape(s))  # 装飾の絵文字
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


# 外部サイトとcfgで表記が違う名前（外部の表記 → cfgの日本語名）
ALIASES = {
    "出奇制勝": "奇策制勝",
    "薩摩鉄砲隊": "薩摩鉄砲兵",
    "三河武士": "三河武士隊",
    "網紀粛正": "綱紀粛正",
    "弾嵐雨霞": "弾嵐雨霰",
    "雷神切り": "雷神斬り",
}
VARIANTS = str.maketrans({"髙": "高", "熙": "煕", "簞": "箪", "訚": "誾", "凛": "凜"})


def norm_raw(name: str) -> str:
    return re.sub(r"[\s・·･]", "", name).translate(VARIANTS)


def norm(name: str) -> str:
    """名前照合用の正規化（中黒・空白・異体字のゆれを吸収）"""
    name = norm_raw(name)
    return ALIASES.get(name, name)


def put(out: dict, name: str, value) -> None:
    """別名で入ってきた行が、正式名で入っている行を上書きしないようにする"""
    key = norm(name)
    if key not in out or norm_raw(name) == key:
        out[key] = value


def core(t: str) -> str:
    """効果文の比較用: 数値・○・記号・空白を除いた骨格"""
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[\d.]+%?(→[\d.]+%?)?|○%?", "", t)
    return re.sub(r"[\s、。,.()（）「」【】:：;；~～・/]", "", t)


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, core(a), core(b)).ratio()


# ---------------------------------------------------------------- Qookka cfg
def load_cfg():
    cfg = json.loads((CACHE / "cfg.json").read_text(encoding="utf-8"))
    ja = {}
    for row in cfg["multi_lang"]:
        if row.get("ja"):
            for k in ("zh-hans", "id"):
                if row.get(k):
                    ja.setdefault(row[k], row["ja"])
    return cfg, ja


def official_tips(s: str) -> str:
    """公式説明文: <font> を外し、Lvで変わる値のプレースホルダ {1%} などを ○ に置き換える"""
    s = re.sub(r"<font[^>]*>(.*?)</font>", r"\1", s)
    s = re.sub(r"\{\d+(%?)\}", lambda m: "○" + m.group(1), s)
    return s.strip()


# ---------------------------------------------------------------- はてなの真戦Wiki
def parse_hz_general(path: Path):
    h = path.read_text(encoding="utf-8")
    m = re.search(r'<h1>(.*?)<span class="kana">(.*?)</span></h1>', h, re.S)
    if not m:
        return None
    rec = {"slug": path.stem, "name": text(m.group(1)), "kana": text(m.group(2)), "stats": {}}
    t = re.search(r'<table class="table">(.*?)</table>', h, re.S)
    if t:
        for label, key in STAT_KEYS:
            r = re.search(rf"<th>{label}</th><td>([\d.]+)</td><td>([\d.]+)</td>", t.group(1))
            if r:
                rec["stats"][key] = [float(r.group(1)), float(r.group(2))]
    tb = re.search(r'<section class="troop-bonus">\s*<h3>兵種ボーナス</h3>(.*?)</section>', h, re.S)
    rec["troopBonus"] = []
    if tb:
        for tr, val in re.findall(r'<span class="tb-troop">(.*?)</span><span class="tb-val">(.*?)</span>', tb.group(1)):
            rec["troopBonus"].append({"troop": text(tr), "value": text(val)})
    ut = re.search(r'<p class="ut-name">(.*?)</p>\s*<p class="ut-effect">(.*?)</p>', h, re.S)
    if ut:
        rec["uniqueName"] = text(re.sub(r"<span.*?</span>", "", ut.group(1), flags=re.S))
        rec["uniqueEffect"] = text(ut.group(2))
    rec["traits"] = []
    for row in re.findall(r'<div class="tr-row">(.*?)<p class="tr-effect">(.*?)</p>', h, re.S):
        lv = re.search(r'<span class="tr-lv[^"]*">(.*?)</span>', row[0])
        nm = re.search(r'class="tr-name"[^>]*>(.*?)</a>', row[0]) or re.search(r'class="tr-name"[^>]*>(.*?)</span>', row[0])
        if lv and nm:
            rec["traits"].append({"rank": text(lv.group(1)), "name": text(nm.group(1)), "effect": text(row[1])})
    return rec


def parse_hz_tactic(path: Path):
    h = path.read_text(encoding="utf-8")
    m = re.search(r"<h1>(.*?)</h1>", h, re.S)
    eff = re.search(r'<div class="effect-text">(.*?)</div>', h, re.S)
    if not m or not eff:
        return None
    name = text(re.sub(r"<span.*?</span>", "", m.group(1), flags=re.S))
    src = re.search(r'<span class="tac-src-type[^"]*">(.*?)</span>(.*?)</div>', h, re.S)
    teachers = [text(x) for x in re.findall(r'<a href="/wiki/general/[^"]+">(.*?)</a>', src.group(2))] if src else []
    return {
        "name": name,
        "effect": text(eff.group(1)),
        "sourceType": text(src.group(1)) if src else "",
        "teachers": teachers,
    }


# ---------------------------------------------------------------- SLGSIM
def parse_slg_tactics(path: Path):
    h = path.read_text(encoding="utf-8")
    out = {}
    for card in re.findall(r'<a href="/skill/[^"]+" class="tactic-card(.*?)</a>', h, re.S):
        attrs = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', card))
        nm = re.search(r'<h3[^>]*>\s*<span[^>]*>.*?</span><span>(.*?)</span>', card, re.S)
        if not nm:
            continue
        rate = re.search(r"発動確率\s*([^<]+)</span>", card)
        tokens = attrs.get("search", "").split()
        out[norm(text(nm.group(1)))] = {
            "rate": text(rate.group(1)) if rate else "",
            "source": attrs.get("source", ""),
            "kana": tokens[1] if len(tokens) > 1 and re.fullmatch(r"[ぁ-ゖー・]+", tokens[1]) else "",
        }
    # カードの並びとリンク先を対応させて詳細ページのパスを付ける
    for (slug, card) in re.findall(r'<a href="/skill/([^"]+)" class="tactic-card(.*?)</a>', h, re.S):
        nm = re.search(r'<h3[^>]*>\s*<span[^>]*>.*?</span><span>(.*?)</span>', card, re.S)
        if nm:
            out[norm(text(nm.group(1)))]["slug"] = slug
    return out


def parse_slg_skill(path: Path):
    """SLGSIM 戦法詳細ページの本文（最初の効果ブロック）"""
    h = path.read_text(encoding="utf-8")
    m = re.search(r'<div class="text-sm text-secondary leading-relaxed whitespace-pre-line">(.*?)</div>', h, re.S)
    return text(m.group(1)) if m else ""


SLG_STAT = {"bu": "bu", "chi": "chi", "tou": "tou", "spd": "spd", "gov": "sei", "cha": "mi"}


def parse_slg_generals(path: Path):
    """SLGSIM 武将一覧: Lv50の値とよみ。※Wikiと1割ほど食い違うので kenbo が無いときだけ使う"""
    h = path.read_text(encoding="utf-8")
    out = {}
    for a, body in re.findall(r'(<a href="/hero/[^"]+" class="hero-card[^>]*>)(.*?)</h3>', h, re.S):
        d = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', a))
        name = text(re.search(r"<h3[^>]*>(.*)", body, re.S).group(1))
        kana = next((t for t in d.get("search", "").split() if re.fullmatch(r"[ぁ-ゖー]+", t)), "")
        lv50 = {ours: int(float(d[k])) for k, ours in SLG_STAT.items() if d.get(k, "").replace(".", "").isdigit()}
        out[norm(name)] = {"kana": kana, "lv50": lv50 if len(lv50) == 6 and any(lv50.values()) else None}
    return out


KENBO_STAT = [("武勇", "bu"), ("知略", "chi"), ("統率", "tou"), ("速度", "spd"), ("政務", "sei"), ("魅力", "mi")]
KENBO_RANK = {"主特性": "無凸", "ランク1": "1凸", "ランク2": "2凸", "ランク3": "3凸", "ランク4": "4凸", "ランク5": "5凸"}


def parse_kenbo_busho(path: Path):
    """kenbo 武将データベース: Lv50の値（Wikiと一致することを確認済み）と凸別特性"""
    h = path.read_text(encoding="utf-8")
    out = {}
    for attrs, row in re.findall(r"<tr (data-faction[^>]*)>(.*?)</tr>", h, re.S):
        name = re.search(r'data-busho-name="([^"]*)"', attrs)
        if not name:
            continue
        tds = {lab: text(v) for lab, v in re.findall(r'<td data-label="([^"]*)"[^>]*>(.*?)</td>', row, re.S)}
        lv50 = {key: int(tds[lab]) for lab, key in KENBO_STAT if tds.get(lab, "").isdigit()}
        traits = []
        for label, tname, eff in re.findall(
            r'<div class="tokusei-slot-label">(.*?)</div>\s*<button[^>]*data-name="([^"]*)" data-effect="([^"]*)"', row, re.S
        ):
            traits.append({"rank": KENBO_RANK.get(text(label), text(label)), "name": htmllib.unescape(tname), "effect": htmllib.unescape(eff)})
        out[norm(name.group(1))] = {"lv50": lv50 if len(lv50) == 6 else None, "traits": traits}
    return out


def parse_kenbo_senpo(path: Path):
    """kenbo 戦法データベース: 発動率と効果（数値はLv10の値のみ）"""
    h = path.read_text(encoding="utf-8")
    out = {}
    for row in re.findall(r"<tr data-kind=[^>]*>(.*?)</tr>", h, re.S):
        tds = {lab: text(v) for lab, v in re.findall(r'<td data-label="([^"]*)"[^>]*>(.*?)</td>', row, re.S)}
        if not tds.get("戦法名"):
            continue
        desc = tds.get("効果", "")
        if tds.get("大将技") and tds["大将技"] not in ("-", "－"):
            desc += "\n大将技：" + tds["大将技"]
        rate = tds.get("発動率", "")
        put(out, tds["戦法名"], {"rate": rate if re.search(r"\d", rate) else "", "desc": desc})
    return out


# ---------------------------------------------------------------- build
def main():
    cfg, ja = load_cfg()
    tr = lambda v: NAME_FIXES.get(v) or ja.get(v) or v

    hz_gen = {}
    for p in sorted((CACHE / "hz" / "general").glob("*.html")):
        r = parse_hz_general(p)
        if r:
            hz_gen[norm(r["name"])] = r
    hz_tac = {}
    for p in sorted((CACHE / "hz" / "tactic").glob("*.html")):
        r = parse_hz_tactic(p)
        if r:
            hz_tac[norm(r["name"])] = r
    slg = parse_slg_tactics(CACHE / "slg" / "tactics.html") if (CACHE / "slg" / "tactics.html").exists() else {}
    slg_gen = parse_slg_generals(CACHE / "slg" / "generals.html") if (CACHE / "slg" / "generals.html").exists() else {}
    ken_gen = parse_kenbo_busho(CACHE / "kenbo" / "busho.html") if (CACHE / "kenbo" / "busho.html").exists() else {}
    ken_tac = parse_kenbo_senpo(CACHE / "kenbo" / "senpo.html") if (CACHE / "kenbo" / "senpo.html").exists() else {}
    kana_file = json.loads((OUT / "kana.json").read_text(encoding="utf-8")) if (OUT / "kana.json").exists() else {}
    kana_fix = {norm(k): v for k, v in kana_file.get("読み", {}).items()}
    kana_unsure = {norm(k) for k in kana_file.get("要確認", [])}
    hero_kana = {norm(k): v for k, v in kana_file.get("武将の読み", {}).items()}

    # ---- 戦法
    skills = {}
    by_cn = {}
    for s in cfg["skill"]:
        if s["skill_kind"] not in MAIN_KINDS or s["grade"] < 3:  # C・D戦法は収録しない
            continue
        name = tr(s["name"])
        rec = {
            "id": s["id"],
            "name": name,
            "kana": "",
            "kanaUnsure": False,
            "grade": GRADE.get(s["grade"], str(s["grade"])),
            "kind": tr(s["skill_kind"]),
            "effectTypes": [tr(e) for e in s["effect_type_list"]],
            "troops": [tr(a) for a in s["arm_limit"]],
            "target": tr(s["target_tips"]),
            "summary": tr(s["short_tips"]),
            "desc": official_tips(tr(s["tips"])),
            "descHasValues": False,
            "valuesNote": "",
            "rate": "",
            "rateUnsure": False,
            "source": "",
            "owners": [],
            "teachers": [],
            "officialOnly": True,  # 外部ソースのどれにも載っていない（未実装の可能性）
            "_cands": [],  # 数値入り効果文の候補 (出典, 文, Lv10のみか)
        }
        w = hz_tac.get(norm(name))
        if w:
            rec["_cands"].append(("wiki", w["effect"], False))
            rec["teachers"] = w["teachers"]
            rec["officialOnly"] = False
        sl = slg.get(norm(name))
        if sl:
            rec["rate"] = sl["rate"]
            rec["source"] = sl["source"]
            rec["kana"] = sl["kana"]
            rec["officialOnly"] = False
        if norm(name) in ken_tac:
            rec["officialOnly"] = False
        skills[s["id"]] = rec
        by_cn.setdefault(s["name"], s["id"])

    # ---- 武将
    heroes = []
    unmatched_hz = set(hz_gen)
    for h in sorted(cfg["hero"], key=lambda x: x["sort"]):
        if h["name"].startswith("军略_"):
            continue
        name = tr(h["name"])
        sid = by_cn.get(h["born_skill"])
        rec = {
            "id": h["id"],
            "name": name,
            "kana": "",
            "star": h["star"],
            "cost": h["cost"],
            "faction": tr(h["camp"]),
            "family": tr(h["family"]),
            "uniqueSkillId": sid,
            "uniqueSkill": skills[sid]["name"] if sid else tr(h["born_skill"]),
            "stats": None,  # {key: [Lv1, 成長値]}
            "lv50": None,  # Lv1・成長値が無い武将のみ: {key: Lv50の値}
            "troopBonus": [],
            "traits": [],
        }
        key = norm(name)
        w = hz_gen.get(key)
        if w:
            unmatched_hz.discard(key)
            rec["kana"] = w["kana"]
            rec["stats"] = w["stats"] or None
            rec["troopBonus"] = w["troopBonus"]
            rec["traits"] = w["traits"]
            if sid and w.get("uniqueEffect"):
                skills[sid]["_cands"].append(("wiki武将", w["uniqueEffect"], False))
                skills[sid]["officialOnly"] = False
            if sid and not skills[sid]["rate"] and w.get("uniqueEffect"):
                r = re.search(r"発動確率\s*(\d+%(?:→\d+%)?)", w["uniqueEffect"])
                if r:
                    skills[sid]["rate"] = r.group(1)
        if not rec["stats"]:
            # Lv1・成長値はどこにも無いので Lv50 の値だけ持つ（kenbo を優先。SLGSIM は Wiki と1割ほど食い違うため）
            rec["lv50"] = (ken_gen.get(key) or {}).get("lv50") or (slg_gen.get(key) or {}).get("lv50")
        if not rec["traits"] and key in ken_gen:
            rec["traits"] = ken_gen[key]["traits"]
        if not rec["kana"] and key in slg_gen:
            rec["kana"] = slg_gen[key]["kana"]
        rec["kana"] = hero_kana.get(key, rec["kana"])
        if sid:
            skills[sid]["owners"].append(name)
            if not skills[sid]["source"]:
                skills[sid]["source"] = "固有戦法"
            if key in hz_gen or key in ken_gen or key in slg_gen:  # 外部ソースに載っている武将の固有戦法なら実装済み
                skills[sid]["officialOnly"] = False
        if rec["star"] >= 4 and rec["cost"] > 2:  # 星1〜3・コスト2の武将は一覧に載せない
            heroes.append(rec)

    # 数値入り効果文の候補: Wiki → Wiki武将ページ → SLGSIM詳細 → kenbo（Lv10の値のみ）
    by_name = {norm(s["name"]): s for s in skills.values()}
    for key, sl in slg.items():
        s = by_name.get(key)
        p = CACHE / "slg" / "skill" / f"{sl.get('slug')}.html"
        if s and p.exists():
            desc = parse_slg_skill(p)
            if desc:
                s["_cands"].append(("SLGSIM", desc, False))
    for key, s in by_name.items():
        k = ken_tac.get(key)
        if not k:
            continue
        if k["desc"]:
            s["_cands"].append(("kenbo", k["desc"], True))
        if k["rate"]:
            lv10 = lambda r: (re.findall(r"(\d+(?:\.\d+)?)%", r) or [None])[-1]
            if not s["rate"]:
                s["rate"] = k["rate"]
            elif lv10(s["rate"]) != lv10(k["rate"]):
                # SLGSIM と kenbo で食い違う: kenbo の方が公式の効果文とよく一致するので kenbo を採り、要確認にする
                s["rate"], s["rateUnsure"] = k["rate"], True

    # 公式の説明文（数値は○）に最も近い候補を採用する。
    # 外部サイトには別の効果文や途中で切れた文が混じっているため（例: SLGSIMの越後先手組）、
    # 類似度が DESC_MATCH 未満なら採用しない。Lv1→Lv10 が分かる候補は、ほぼ同等なら優先する。
    rejected = []
    for s in skills.values():
        official = s["desc"]
        scored = [(similarity(official, cand), i, src, cand, lv10) for i, (src, cand, lv10) in enumerate(s["_cands"])]
        if scored:
            top = max(x[0] for x in scored)
            near = [x for x in scored if x[0] >= top - 0.05 and x[0] >= DESC_MATCH]
            near.sort(key=lambda x: (x[4], x[1]))  # Lv1→Lv10 の候補を優先、次に出典の優先順
            if near:
                _, _, src, cand, lv10 = near[0]
                s["desc"], s["descHasValues"] = cand, True
                s["valuesNote"] = "数値はLv10の値" if lv10 else ""
                s["_from"] = src
            rejected += [(s["name"], x[2], round(x[0], 2)) for x in scored if x[0] < DESC_MATCH]
        del s["_cands"]
    for s in skills.values():
        if s["kind"] in ("指揮", "受動", "兵種", "陣法"):  # 戦闘中常に発動する種別
            s["rate"], s["rateUnsure"] = "100%", False
        # 読みがな: 手入力の data/kana.json を最優先
        key = norm(s["name"])
        if key in kana_fix:
            s["kana"] = kana_fix[key]
        s["kanaUnsure"] = key in kana_unsure
        # 伝授戦法なのに伝授元が取れていないもの（星3・4武将の固有戦法）は、所持武将を伝授元として表示
        if s["source"] == "伝授戦法" and not s["teachers"] and s["owners"]:
            s["teachers"], s["owners"] = s["owners"], []

    chosen_from = {s["name"]: s.pop("_from", "公式") for s in skills.values()}
    skill_list = sorted(skills.values(), key=lambda x: (x["grade"], x["id"]))

    OUT.mkdir(exist_ok=True)
    dump = lambda name, obj: (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    dump("heroes.json", heroes)
    dump("skills.json", skill_list)
    meta = {
        "generatedAt": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "cfgVersion": cfg.get("version"),
        "heroCount": len(heroes),
        "heroWithStats": sum(1 for x in heroes if x["stats"]),
        "heroWithLv50Only": sum(1 for x in heroes if x["lv50"]),
        "skillCount": len(skill_list),
        "skillWithValues": sum(1 for x in skill_list if x["descHasValues"]),
        "skillWithRate": sum(1 for x in skill_list if x["rate"]),
        "skillOfficialOnly": sum(1 for x in skill_list if x["officialOnly"]),
    }
    dump("meta.json", meta)

    # ---- レポート
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    names = {norm(s["name"]) for s in skill_list}
    if unmatched_hz:
        print("Wiki武将のうちcfgに一致しなかった名前:", sorted(hz_gen[k]["name"] for k in unmatched_hz))
    for label, src in (("Wiki戦法", hz_tac), ("SLGSIM戦法", slg), ("kenbo戦法", ken_tac)):
        miss = [k for k in src if k not in names]
        if miss:
            print(f"{label}のうちcfgに一致しなかった名前:", miss)
    print("ステータス未取得:", [x["name"] for x in heroes if not x["stats"] and not x["lv50"]])
    print("読みがな未設定の戦法:", [s["name"] for s in skill_list if not s["kana"]])
    print("公式データのみの戦法:", [s["name"] for s in skill_list if s["officialOnly"]])
    print(f"公式の説明文と一致せず不採用にした効果文（類似度 < {DESC_MATCH}）:", rejected)
    print("数値なし（公式の説明文のまま）:", [s["name"] for s in skill_list if not s["descHasValues"]])


if __name__ == "__main__":
    main()
