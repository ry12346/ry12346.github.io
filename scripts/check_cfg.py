"""公式の設定ファイル cfg.json に新しい武将・戦法が増えたかを調べる（GitHub Actions で毎日実行）。

  python scripts/check_cfg.py [報告ファイル]

前回見た武将名・戦法名を data/cfg_seen.json に記録しておき、増えていれば
報告ファイル（Markdown）に書き出す。Actions はそれを GitHub の Issue にする。
初回は記録だけして報告しない。
"""
import json
import sys
import urllib.request
import gzip
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_data as b  # noqa: E402  名前の翻訳や戦法の種別の判定を共有する

SEEN = b.ROOT / "data" / "cfg_seen.json"
CFG_URL = "https://p11386-media-cdn.qookkagames.com/P11386/sns/public_config/release/cfg.json"


def main():
    report = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    req = urllib.request.Request(CFG_URL, headers={"User-Agent": "Mozilla/5.0 (shinsen-portal cfg check)"})
    body = urllib.request.urlopen(req, timeout=60).read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    (b.CACHE).mkdir(exist_ok=True)
    (b.CACHE / "cfg.json").write_bytes(body)
    cfg, ja = b.load_cfg()
    tr = lambda v: b.NAME_FIXES.get(v) or ja.get(v) or v

    heroes = sorted({tr(h["name"]) for h in cfg["hero"] if not h["name"].startswith("军略_")})
    skills = sorted({tr(s["name"]) for s in cfg["skill"] if s["skill_kind"] in b.MAIN_KINDS and s["grade"] >= 3})
    now = {"version": cfg.get("version"), "heroes": heroes, "skills": skills}

    if not SEEN.exists():
        SEEN.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
        print("初回: 現在の武将・戦法を記録しました")
        return
    before = json.loads(SEEN.read_text(encoding="utf-8"))
    new_heroes = [n for n in heroes if n not in before["heroes"]]
    new_skills = [n for n in skills if n not in before["skills"]]
    SEEN.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"新しい武将 {len(new_heroes)} / 戦法 {len(new_skills)}")
    if (new_heroes or new_skills) and report:
        lines = ["公式の設定ファイル（cfg.json）に新しいデータが追加されました。新シーズンの準備の可能性があります。", ""]
        if new_heroes:
            lines += ["### 新しい武将", *[f"- {n}" for n in new_heroes], ""]
        if new_skills:
            lines += ["### 新しい戦法", *[f"- {n}" for n in new_skills], ""]
        lines += [
            "### やること",
            "- `python scripts/fetch_sources.py` → `python scripts/build_data.py` でサイトのデータを作り直す",
            "- 公式ニュースに「新武将徹底解説」が出たら、Lv1・成長値などを `data/official.json` に反映する",
        ]
        report.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
