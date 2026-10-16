// 全ページ共通: ヘッダー・フッター・データ読み込み・小物
const NAV = [
  ["index.html", "トップ"],
  ["generals.html", "武将一覧"],
  ["tactics.html", "戦法一覧"],
  ["formations.html", "おすすめ編成"],
  ["exp.html", "経験値・資料"],
  ["news.html", "公式ニュース"],
  ["report.html", "情報提供"],
];

export const TOOLS = [
  {
    url: "https://ry12346.github.io/shinsen-pk-stada-navi/",
    icon: "走",
    title: "PKシーズン スタダナビ",
    desc: "前シーズン準備から天守8到達まで、48時間の進行を段階別にガイド",
  },
  {
    url: "https://ry12346.github.io/shinsen-enemy-db-vision/",
    icon: "敵",
    title: "敵部隊データベース",
    desc: "敵部隊の編成を戦報画像とあわせて記録・検索するデータベース",
  },
  {
    url: "https://ry12346.github.io/occupation-time-calculator/",
    icon: "時",
    title: "占領時間・到着予想時刻計算",
    desc: "占領開始日時とマス数から、時間帯別の占領時間を考慮して終了予想日時を計算",
  },
];

export const FACTIONS = ["織田", "豊臣", "徳川", "武田", "上杉", "群雄"];

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function $(sel, root = document) {
  return root.querySelector(sel);
}

export async function loadJSON(name) {
  const res = await fetch(`data/${name}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
}

/** ひらがな・カタカナ・全角英数を揃えて検索しやすくする */
export function fold(s) {
  return String(s ?? "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60))
    .replace(/[\s・·]/g, "");
}

function renderChrome() {
  const here = location.pathname.split("/").pop() || "index.html";
  const header = document.createElement("header");
  header.className = "topbar";
  header.innerHTML = `
    <div class="topbar-inner">
      <a class="brand" href="index.html">
        <span class="brand-mark">真</span>
        <span><strong>真戦データ帳</strong><small>信長の野望 真戦 総合データ</small></span>
      </a>
      <nav class="nav" aria-label="サイト内">
        ${NAV.map(([href, label]) => `<a href="${href}"${href === here ? ' aria-current="page"' : ""}>${label}</a>`).join("")}
      </nav>
    </div>`;
  document.body.prepend(header);

  const footer = document.createElement("footer");
  footer.innerHTML = `<p>非公式のファンサイトです。ゲーム内の名称・数値は各権利者に帰属します。データ更新: <span id="meta-updated">-</span></p>`;
  document.body.append(footer);
  loadJSON("meta.json")
    .then((m) => (document.getElementById("meta-updated").textContent = m.generatedAt))
    .catch(() => {});
}

/** チップ型の複数選択フィルタ。選択なし＝すべて */
export function chipGroup(container, values, onChange, { label = (v) => v } = {}) {
  const selected = new Set();
  container.insertAdjacentHTML(
    "beforeend",
    values.map((v) => `<button type="button" class="chip" aria-pressed="false" data-v="${esc(v)}">${esc(label(v))}</button>`).join("")
  );
  container.addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    const v = b.dataset.v;
    if (selected.has(v)) selected.delete(v);
    else selected.add(v);
    b.setAttribute("aria-pressed", selected.has(v));
    onChange();
  });
  return {
    test: (v) => selected.size === 0 || (Array.isArray(v) ? v.some((x) => selected.has(String(x))) : selected.has(String(v))),
    values: () => [...selected],
    /** 選択状態を外から復元する（onChange は呼ばない） */
    set(list) {
      selected.clear();
      for (const v of list) if (values.map(String).includes(v)) selected.add(v);
      container.querySelectorAll(".chip").forEach((b) => b.setAttribute("aria-pressed", selected.has(b.dataset.v)));
    },
  };
}

// ---- 一覧ページの状態保持（リンク先から「戻る」で帰ってきたとき、見ていた状態に戻す） ----

/** ブラウザの「戻る」「進む」で開かれたか */
export const isBackNav = () => performance.getEntriesByType("navigation")[0]?.type === "back_forward";

/** 絞り込み条件を URL に書く（空の値は省く。配列は「,」区切り） */
export function setQuery(obj) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) {
    const s = Array.isArray(v) ? v.join(",") : v;
    if (s != null && s !== "" && s !== false) p.set(k, s === true ? "1" : s);
  }
  const qs = p.toString();
  history.replaceState(null, "", (qs ? `?${qs}` : location.pathname) + location.hash);
}

/** URL の値を読む。list=true なら「,」区切りの配列 */
export function getQuery(key, list = false) {
  const v = new URLSearchParams(location.search).get(key) || "";
  return list ? v.split(",").filter(Boolean) : v;
}

/** スクロール位置を覚えておき、「戻る」で帰ってきたときに復元する。描画が終わってから呼ぶ */
export function keepScroll(key) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || "null");
    if (isBackNav() && saved && saved.url === location.search) {
      history.scrollRestoration = "manual";
      requestAnimationFrame(() => window.scrollTo(0, saved.y));
    }
  } catch {}
  addEventListener("pagehide", () => {
    try { sessionStorage.setItem(key, JSON.stringify({ url: location.search, y: scrollY })); } catch {}
  });
}

renderChrome();
