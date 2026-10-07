"""外部ソースの生HTML/JSONを .cache/ に保存する。

  python scripts/fetch_sources.py          # 未取得のものだけ取得
  python scripts/fetch_sources.py --force  # すべて取り直す

取得先:
  - Qookka 公開設定 cfg.json（武将・戦法マスタ、日本語訳）
  - はてなの真戦Wiki 武将ページ（Lv1・成長値・兵種ボーナス・固有戦法の数値入り効果）
  - はてなの真戦Wiki 戦法伝授ページ（伝授戦法の数値入り効果）
  - SLGSIM 戦法一覧・詳細（発動確率、数値入り効果）、武将一覧（Lv50の値）
  - kenbo-no-palette 武将・戦法データベース（Lv50の値、凸別特性、発動確率、Lv10の効果）
"""
import gzip
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
UA = "Mozilla/5.0 (shinsen-portal data builder)"
WAIT = 1.0  # 相手サーバーへの負荷を避けるための間隔（秒）

CFG_URL = "https://p11386-media-cdn.qookkagames.com/P11386/sns/public_config/release/cfg.json"
HZ = "https://www.sanguo-zhi.com"
SLG = "https://slgsim.com"
KENBO = "https://kenbo-no-palette.com"

force = "--force" in sys.argv


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body


def save(url: str, path: Path, polite: bool = True) -> bytes:
    if path.exists() and not force:
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = get(url)
    path.write_bytes(body)
    print(f"  saved {path.relative_to(ROOT)} ({len(body):,} bytes)")
    if polite:
        time.sleep(WAIT)
    return body


def main() -> None:
    print("Qookka cfg.json")
    # cfg.json は毎回取り直す（ゲーム更新で増えるため）
    body = get(CFG_URL)
    (CACHE / "cfg.json").parent.mkdir(parents=True, exist_ok=True)
    (CACHE / "cfg.json").write_bytes(body)
    print(f"  saved .cache/cfg.json ({len(body):,} bytes)")

    print("はてなの真戦Wiki 武将")
    html = save(f"{HZ}/wiki/general/", CACHE / "hz" / "general_index.html").decode("utf-8")
    slugs = sorted(set(re.findall(r'href="(?:https://www\.sanguo-zhi\.com)?/wiki/general/([a-z0-9_-]+)/"', html)))
    print(f"  {len(slugs)} 件")
    for s in slugs:
        save(f"{HZ}/wiki/general/{s}/", CACHE / "hz" / "general" / f"{s}.html")

    print("はてなの真戦Wiki 戦法伝授")
    html = save(f"{HZ}/wiki/tactic/", CACHE / "hz" / "tactic_index.html").decode("utf-8")
    slugs = sorted(set(re.findall(r'href="(?:https://www\.sanguo-zhi\.com)?/wiki/tactic/([a-z0-9_-]+)/"', html)))
    print(f"  {len(slugs)} 件")
    for s in slugs:
        save(f"{HZ}/wiki/tactic/{s}/", CACHE / "hz" / "tactic" / f"{s}.html")

    print("SLGSIM 武将一覧")
    save(f"{SLG}/generals", CACHE / "slg" / "generals.html")

    print("kenbo-no-palette 武将・戦法データベース")
    save(f"{KENBO}/database/busho/", CACHE / "kenbo" / "busho.html")
    save(f"{KENBO}/database/senpo/", CACHE / "kenbo" / "senpo.html")

    print("SLGSIM 戦法")
    html = save(f"{SLG}/tactics", CACHE / "slg" / "tactics.html").decode("utf-8")
    slugs = sorted(set(re.findall(r'href="/skill/([A-Za-z0-9_-]+)"', html)))
    print(f"  {len(slugs)} 件")
    for s in slugs:
        save(f"{SLG}/skill/{s}", CACHE / "slg" / "skill" / f"{s}.html")


if __name__ == "__main__":
    main()
