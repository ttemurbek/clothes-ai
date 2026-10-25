// Shared helpers for every page: API calls (with Telegram auth), formatting, DOM building, toasts.
export const tg = window.Telegram?.WebApp?.initData ? window.Telegram.WebApp : null;

if (tg) {
  tg.ready();
  tg.expand();
  document.documentElement.classList.add("in-telegram");
  const apply = () => document.documentElement.dataset.theme = tg.colorScheme === "dark" ? "dark" : "light";
  apply();
  tg.onEvent?.("themeChanged", apply);
}

export class ApiError extends Error {
  constructor(message, status, body) { super(message); this.status = status; this.body = body || {}; }
}

export async function api(path, { method = "GET", json, form, signal } = {}) {
  const headers = {};
  if (tg) headers["X-Telegram-Init-Data"] = tg.initData;
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  else if (form) body = form;
  let response;
  try {
    response = await fetch(path, { method, headers, body, signal, credentials: "same-origin" });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError("Internet aloqasi yoʻq yoki server javob bermadi.", 0);
  }
  const data = response.headers.get("Content-Type")?.includes("json") ? await response.json() : {};
  if (!response.ok) throw new ApiError(data.error || "Xatolik yuz berdi.", response.status, data);
  return data;
}

export async function apiBlob(path) {
  const headers = tg ? { "X-Telegram-Init-Data": tg.initData } : {};
  const response = await fetch(path, { headers, credentials: "same-origin" });
  if (!response.ok) throw new ApiError("Rasm yuklanmadi.", response.status);
  return response.blob();
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** el("div.card#x", {onclick, dataset, ...attrs}, ...children) — text children are escaped. */
export function el(tag, props = {}, ...children) {
  const [, name = "div", rest = ""] = tag.match(/^([a-z0-9-]*)(.*)$/i) || [];
  const node = document.createElement(name || "div");
  for (const part of rest.match(/[.#][^.#]+/g) || []) {
    if (part[0] === ".") node.classList.add(part.slice(1)); else node.id = part.slice(1);
  }
  if (props != null && (typeof props !== "object" || props instanceof Node || Array.isArray(props))) {
    children.unshift(props); props = {};
  }
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "class") node.className = value;
    else if (key === "html") throw new Error("html is not allowed");
    else if (key in node && typeof value !== "string") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const fmtPrice = n => new Intl.NumberFormat("uz-UZ").format(n).replace(/,/g, " ") + " soʻm";
export const fmtKm = km => km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(km < 10 ? 1 : 0)} km`;
export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("uz-UZ", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
export function fmtLeft(iso) {
  const ms = new Date(iso) - Date.now();
  if (ms <= 0) return "muddati tugadi";
  const h = Math.floor(ms / 3600000), m = Math.floor(ms % 3600000 / 60000);
  return h ? `${h} soat ${m} daqiqa` : `${m} daqiqa`;
}

export function formatPhone(value) {
  let d = value.replace(/\D/g, "");
  if (d.startsWith("998")) d = d.slice(3);
  d = d.slice(0, 9);
  const parts = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean);
  return "+998 " + parts.join(" ");
}

// ---------- visuals for products without a photo ----------
const CATEGORY_ICON = {
  "Kelinlik libosi": "👰", "Kechki libos": "👗", "Kostyum": "🤵", "Milliy libos": "🧕",
  "Koʻylak": "👔", "Ustki kiyim": "🧥", "Bolalar kiyimi": "🧒", "Aksessuar": "🧣",
  "Sviter va kofta": "🧶", "Shim va yubka": "👖", "Poyabzal": "🥾",
};
export const COLOR_HEX = {
  "Oq": "#f4f1ea", "Qora": "#1d1b1f", "Bej": "#d9c4a5", "Kulrang": "#9a9a9f", "Koʻk": "#2f4f8f",
  "Moviy": "#7fb2dc", "Yashil": "#3f7d5a", "Qizil": "#b2283a", "Pushti": "#eaa7bd", "Binafsha": "#7b4fa8",
  "Oltin rang": "#c9a24b", "Kumush rang": "#c4c7cc", "Jigarrang": "#7a5236",
  "Rang-barang": "conic-gradient(#e76f51,#f4a261,#e9c46a,#2a9d8f,#457b9d,#9b5de5,#e76f51)",
};

export function productArt(product, cls = "art") {
  if (product.image) {
    return el(`div.${cls}`, {}, el("img", { src: product.image, alt: product.name, loading: "lazy", decoding: "async" }));
  }
  const tint = COLOR_HEX[product.color] || "#e9e4ee";
  const node = el(`div.${cls}.art-placeholder`, { role: "img", "aria-label": product.name },
    el("span.art-icon", CATEGORY_ICON[product.category] || "👕"));
  node.style.setProperty("--tint", tint.startsWith("conic") ? "#e8dff0" : tint);
  return node;
}

export function swatch(color) {
  const s = el("span.swatch", { title: color, "aria-hidden": "true" });
  s.style.background = COLOR_HEX[color] || "#ccc";
  return s;
}

// ---------- toasts and dialogs ----------
export function toast(message, kind = "info") {
  let host = $("#toasts");
  if (!host) { host = el("div#toasts", { role: "status", "aria-live": "polite" }); document.body.append(host); }
  const item = el(`div.toast.toast-${kind}`, message);
  host.append(item);
  setTimeout(() => item.classList.add("hide"), 3800);
  setTimeout(() => item.remove(), 4300);
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred(kind === "error" ? "error" : "success");
}

const openDialogs = [];
export function openDialog(dialog) {
  if (!dialog.open) dialog.showModal();
  if (!openDialogs.includes(dialog)) openDialogs.push(dialog);
  document.documentElement.classList.add("modal-open");
  if (tg) tg.BackButton.show();
}
export function closeDialog(dialog) {
  if (dialog.open) dialog.close();
}
function onDialogClosed(dialog) {
  const i = openDialogs.indexOf(dialog);
  if (i >= 0) openDialogs.splice(i, 1);
  if (!openDialogs.length) {
    document.documentElement.classList.remove("modal-open");
    if (tg) tg.BackButton.hide();
  }
}
document.addEventListener("close", e => { if (e.target.tagName === "DIALOG") onDialogClosed(e.target); }, true);
document.addEventListener("click", e => {
  if (e.target.tagName === "DIALOG") closeDialog(e.target);  // click on the backdrop
  const closer = e.target.closest("[data-close]");
  if (closer) closeDialog(closer.closest("dialog"));
});
if (tg) tg.BackButton.onClick(() => { const top = openDialogs.at(-1); if (top) closeDialog(top); });

export function shareLink(url, text) {
  const full = new URL(url, location.origin).href;
  const link = `https://t.me/share/url?url=${encodeURIComponent(full)}&text=${encodeURIComponent(text)}`;
  if (tg) { tg.openTelegramLink(link); return; }
  if (navigator.share) { navigator.share({ url: full, text }).catch(() => {}); return; }
  window.open(link, "_blank", "noopener");
}

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("Nusxa olindi"); }
  catch { toast("Nusxa olib boʻlmadi", "error"); }
}

export const store = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ } },
};
