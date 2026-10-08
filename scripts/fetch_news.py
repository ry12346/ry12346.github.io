"""公式サイトのニュースを取り込んで data/news.json（一覧）と data/news/{id}.json（本文）を作る。

  python scripts/fetch_news.py            # 新着だけ取得（GitHub Actions で毎日実行）
  python scripts/fetch_news.py --all      # ID 1 から全件取り直す

公式サイト（nobunaga-shinsen.qookkagames.jp）のニュースは、連番のIDで
get-entity API から取れる。前回の最大IDより先を順に問い合わせ、
一定数続けて見つからなければ終わる。直近の数件は修正に備えて取り直す。
"""
import html as htmllib
import json
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "news.json"
SEARCH = ROOT / "data" / "news_text.json"  # 本文の全文検索用（ページでは検索したときだけ読み込む）
BODY_DIR = ROOT / "data" / "news"
API = "https://cubeapi-jp.qookkagames.com/lingxigamescube/api/information/get-entity"
ACTIVE_CODE = "s11g-jp_rbyygw"
ARTICLE_URL = "https://nobunaga-shinsen.qookkagames.jp/prism-mfqju6aj/#/news/{}"
JST = timezone(timedelta(hours=9))
MISS_LIMIT = 25  # これだけ続けて見つからなければ打ち切る（削除された記事で番号が飛ぶため）
REFRESH = 8  # 直近の記事は修正に備えて取り直す
WAIT = 0.3

CATEGORIES = [
    ("サーバー予定", r"一部サーバー"),
    ("メンテナンス", r"メンテナンス|アップデート|不具合"),
    ("武将・戦法", r"新武将|武将|戦法|兵装|事件"),
    ("大名録・戦況", r"大名録|戦況|結果公開"),
    ("シーズン", r"シーズン|評定|開幕|攻略|地形|覇業"),
    ("イベント", r"イベント|キャンペーン|祭|記念|募集|プレゼント"),
]


def fetch(entity_id: int):
    body = json.dumps({"activeCode": ACTIVE_CODE, "informationEntityId": entity_id}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://nobunaga-shinsen.qookkagames.jp",
            "User-Agent": "Mozilla/5.0 (shinsen-portal news sync)",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    return data.get("result")


def category(title: str) -> str:
    title = unicodedata.normalize("NFKC", title)
    for name, pattern in CATEGORIES:
        if re.search(pattern, title):
            return name
    return "お知らせ"


ALLOWED = {"p", "br", "strong", "b", "u", "ul", "ol", "li", "table", "tbody", "tr", "td", "th"}


def sanitize(content: str) -> str:
    """公式の本文HTMLから、表示に必要なタグだけ残す（属性は img の src と a の href だけ）"""
    def tag(m):
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if name == "img":
            src = re.search(r'src="(https://[^"]+)"', attrs)
            return f'<img src="{htmllib.escape(src.group(1))}" loading="lazy" alt="">' if src else ""
        if name == "a":
            if closing:
                return "</a>"
            href = re.search(r'href="(https?://[^"]+)"', attrs)
            return f'<a href="{htmllib.escape(href.group(1))}" target="_blank" rel="noopener">' if href else "<a>"
        if name in ALLOWED:
            return f"<{closing}{name}>"
        return ""

    content = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content or "", flags=re.S | re.I)
    content = re.sub(r"<(/?)([a-zA-Z0-9]+)([^>]*)>", tag, content)
    return re.sub(r"(<p>\s*</p>)+", "", content).strip()


def summary(content: str, n: int = 90) -> str:
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", content))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^いつも『?信長の野望 ?真戦』?を応援いただき、?ありがとうございます。?", "", text).strip()
    return text[:n] + ("…" if len(text) > n else "")


def link_list(r: dict) -> str:
    """本文が空で、ほかの記事へのリンク集（jsonExt）だけを持つ記事を、リンクの一覧にする"""
    try:
        links = json.loads(r.get("jsonExt") or "[]")
    except ValueError:
        return ""
    items = []
    for x in links if isinstance(links, list) else []:
        url, name = str(x.get("content", "")), htmllib.escape(str(x.get("name", "")))
        m = re.search(r"#/news/(\d+)", url)
        if m:
            items.append(f'<li><a href="news.html#{m.group(1)}" data-news="{m.group(1)}">{name}</a></li>')
        elif url.startswith("http"):
            items.append(f'<li><a href="{htmllib.escape(url)}" target="_blank" rel="noopener">{name}</a></li>')
    return f"<ul>{''.join(items)}</ul>" if items else ""


def to_item(r: dict):
    if str(r.get("entityType")) != "1" or not r.get("name"):  # 1 = 記事（3 は画像バナー、2 は動画）
        return None, None
    # 公開前のテスト記事（中国語・韓国語の題名）や内部コード名の記事は除く
    if not re.search(r"[ぁ-んァ-ヶ]", r["name"]) or r["name"].startswith("S11G-"):
        return None, None
    content = sanitize(r.get("longContent") or "")
    if not re.sub(r"<[^>]+>|\s", "", content) and "<img" not in content:
        content = link_list(r)
    when = datetime.fromtimestamp(int(r["gmtCreate"]) / 1000, JST)
    images = len(re.findall(r"<img", content))
    text_len = len(re.sub(r"<[^>]+>|\s", "", content))
    item = {
        "id": int(r["id"]),
        "title": r["name"].strip(),
        "date": when.strftime("%Y-%m-%d"),
        "category": category(r["name"]),
        "images": images,
        "textOnly": images == 0,
        "imageOnly": text_len < 20 and images > 0,
        "summary": summary(content),
        "empty": not re.sub(r"<[^>]+>|\s", "", content) and images == 0,  # 公式側でも本文が無い（後で入ることがある）
        "url": ARTICLE_URL.format(r["id"]),
    }
    return item, content


def main():
    BODY_DIR.mkdir(parents=True, exist_ok=True)
    items = {} if "--all" in sys.argv or not INDEX.exists() else {x["id"]: x for x in json.loads(INDEX.read_text(encoding="utf-8"))}
    last = max(items, default=0)
    ids = list(range(max(1, last - REFRESH + 1), last + 1)) if items else []
    ids += [i for i, x in items.items() if x.get("empty") and i not in ids]  # 本文が空だった記事は取り直す
    added = []

    def take(i):
        r = fetch(i)
        time.sleep(WAIT)
        if not r:
            return False
        item, content = to_item(r)
        if item:
            if i not in items:
                added.append(item)
            items[i] = item
            (BODY_DIR / f"{i}.json").write_text(json.dumps({"id": i, "html": content}, ensure_ascii=False), encoding="utf-8")
        return True

    for i in ids:
        take(i)
    i, miss = last + 1, 0
    while miss < MISS_LIMIT:
        miss = 0 if take(i) else miss + 1
        i += 1

    data = sorted(items.values(), key=lambda x: x["id"], reverse=True)
    INDEX.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    texts = {}
    for x in data:
        f = BODY_DIR / f"{x['id']}.json"
        if f.exists():
            h = json.loads(f.read_text(encoding="utf-8"))["html"]
            texts[x["id"]] = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", h))).strip()
    SEARCH.write_text(json.dumps(texts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ニュース {len(data)} 件（新着 {len(added)} 件）")
    for x in added:
        print(f"  #{x['id']} {x['date']} [{x['category']}] {x['title']}")


if __name__ == "__main__":
    main()
