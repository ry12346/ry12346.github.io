""".cache/ の生データから data/*.json を生成する。

  python scripts/fetch_sources.py   # 先に取得
  python scripts/build_data.py

マスタの土台は Qookka 公開設定 cfg.json（IDが主キー）。
ステータス・成長値・数値入り効果文・発動確率は外部ページから名前で突き合わせて補う。
"""
import html as htmllib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "data"

JST = timezone(timedelta(hours=9))
GRADE = {5: "S", 4: "A", 3: "B", 2: "C", 1: "D"}
MAIN_KINDS = {"主动", "被动", "指挥", "突击", "兵种", "阵法"}
STAT_KEYS = [("武勇", "bu"), ("知略", "chi"), ("統率", "tou"), ("速度", "spd"), ("政務", "sei"), ("魅力", "mi")]

# cfg.json の multi_lang に日本語が無い名前の補正（中国語簡体 → 日本語）
NAME_FIXES = {
    "百战炼磨": "百戦錬磨",
    "千军辟易·拓": "千軍辟易・拓",
    "临时枪之铃": "臨時槍之鈴",
    "士气高扬": "士気高揚",
    "速战": "速戦",
}


def text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t\r\f\v]+", " ", htmllib.unescape(s)).strip()


# 外部サイトとcfgで表記が違う名前（外部の表記 → cfgの日本語名）
ALIASES = {
    "出奇制勝": "奇策制勝",
    "薩摩鉄砲隊": "薩摩鉄砲兵",
    "三河武士": "三河武士隊",
    "網紀粛正": "綱紀粛正",
    "弾嵐雨霞": "弾嵐雨霰",
    "雷神切り": "雷神斬り",
}
VARIANTS = str.maketrans({"髙": "高", "熙": "煕", "簞": "箪", "訚": "誾"})


def norm(name: str) -> str:
    """名前照合用の正規化（中黒・空白・異体字のゆれを吸収）"""
    name = re.sub(r"[\s・·･]", "", name).translate(VARIANTS)
    return ALIASES.get(name, name)


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

    # ---- 戦法
    skills = {}
    by_cn = {}
    for s in cfg["skill"]:
        if s["skill_kind"] not in MAIN_KINDS:
            continue
        name = tr(s["name"])
        rec = {
            "id": s["id"],
            "name": name,
            "kana": "",
            "grade": GRADE.get(s["grade"], str(s["grade"])),
            "kind": tr(s["skill_kind"]),
            "effectTypes": [tr(e) for e in s["effect_type_list"]],
            "troops": [tr(a) for a in s["arm_limit"]],
            "target": tr(s["target_tips"]),
            "summary": tr(s["short_tips"]),
            "desc": "",
            "descHasValues": False,
            "rate": "",
            "source": "",
            "owners": [],
            "teachers": [],
        }
        official = official_tips(tr(s["tips"]))
        w = hz_tac.get(norm(name))
        if w:
            rec["desc"], rec["descHasValues"] = w["effect"], True
            rec["teachers"] = w["teachers"]
        else:
            rec["desc"] = official
        sl = slg.get(norm(name))
        if sl:
            rec["rate"] = sl["rate"]
            rec["source"] = sl["source"]
            rec["kana"] = sl["kana"]
        if not rec["rate"] and rec["kind"] in ("指揮", "受動", "兵種", "陣法"):
            rec["rate"] = "100%"
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
            "stats": None,
            "troopBonus": [],
            "traits": [],
        }
        w = hz_gen.get(norm(name))
        if w:
            unmatched_hz.discard(norm(name))
            rec["kana"] = w["kana"]
            rec["stats"] = w["stats"] or None
            rec["troopBonus"] = w["troopBonus"]
            rec["traits"] = w["traits"]
            if sid and not skills[sid]["descHasValues"] and w.get("uniqueEffect"):
                skills[sid]["desc"], skills[sid]["descHasValues"] = w["uniqueEffect"], True
            if sid and not skills[sid]["rate"] and w.get("uniqueEffect"):
                r = re.search(r"発動確率\s*(\d+%(?:→\d+%)?)", w["uniqueEffect"])
                if r:
                    skills[sid]["rate"] = r.group(1)
        if sid:
            skills[sid]["owners"].append(name)
            if not skills[sid]["source"]:
                skills[sid]["source"] = "固有戦法"
        heroes.append(rec)

    # Wikiで数値入りの効果文が取れなかった戦法は SLGSIM の詳細ページで補う
    slg_by_name = {norm(s["name"]): s for s in skills.values()}
    for key, sl in slg.items():
        s = slg_by_name.get(key)
        p = CACHE / "slg" / "skill" / f"{sl.get('slug')}.html"
        if s and not s["descHasValues"] and p.exists():
            desc = parse_slg_skill(p)
            if desc:
                s["desc"], s["descHasValues"] = desc, True

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
        "skillCount": len(skill_list),
        "skillWithValues": sum(1 for x in skill_list if x["descHasValues"]),
        "skillWithRate": sum(1 for x in skill_list if x["rate"]),
    }
    dump("meta.json", meta)

    # ---- レポート
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    untrans = [x["name"] for x in heroes if re.search(r"[一-鿿]", x["name"]) and x["name"] != x["name"]]
    if unmatched_hz:
        print("Wiki武将のうちcfgに一致しなかった名前:", sorted(hz_gen[k]["name"] for k in unmatched_hz))
    unmatched_tac = [hz_tac[k]["name"] for k in hz_tac if k not in {norm(s["name"]) for s in skill_list}]
    if unmatched_tac:
        print("Wiki戦法のうちcfgに一致しなかった名前:", unmatched_tac)
    unmatched_slg = [k for k in slg if k not in {norm(s["name"]) for s in skill_list}]
    if unmatched_slg:
        print("SLGSIM戦法のうちcfgに一致しなかった名前:", unmatched_slg)
    no_stats = [x["name"] for x in heroes if not x["stats"] and x["star"] >= 3]
    print(f"ステータス未取得の星3以上: {len(no_stats)}件", no_stats)


if __name__ == "__main__":
    main()
