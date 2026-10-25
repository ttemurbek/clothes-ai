// Buyer app: catalog + filters, map of shops, product sheet, reservation, try-on, compare & share.
import {
  $, $$, api, apiBlob, closeDialog, el, fmtKm, fmtLeft, fmtPrice, fmtTime, formatPhone, openDialog,
  productArt, shareLink, store, swatch, tg, toast,
} from "./common.js";
import { tryOn3d } from "./fitting3d.js";

const PAGE = 24;
const state = {
  q: "", category: "", size: "", color: "", price: "", sort: "relevance", near: false, shop: "",
  point: null, offset: 0, total: 0, items: [], meta: null,
};
let listAbort = null;

// ---------- URL <-> state ----------
function readUrl() {
  const p = new URLSearchParams(location.search);
  for (const k of ["q", "category", "size", "color", "price", "sort"]) state[k] = p.get(k) || (k === "sort" ? "relevance" : "");
  const shop = location.pathname.match(/^\/shop\/([\w-]+)/);
  state.shop = shop ? shop[1] : "";
}
function writeUrl() {
  const p = new URLSearchParams();
  for (const k of ["q", "category", "size", "color", "price"]) if (state[k]) p.set(k, state[k]);
  if (state.sort !== "relevance") p.set("sort", state.sort);
  const path = state.shop ? `/shop/${state.shop}` : "/";
  const url = path + (p.toString() ? "?" + p : "") + location.hash;
  if (url !== location.pathname + location.search + location.hash && !location.pathname.startsWith("/p/")) {
    history.replaceState(null, "", url);
  }
}
function params(extra = {}) {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.category) p.set("category", state.category);
  if (state.size) p.set("size", state.size);
  if (state.color) p.set("color", state.color);
  if (state.shop) p.set("shop", state.shop);
  if (state.price) {
    const [lo, hi] = state.price.split("-");
    if (lo) p.set("min_price", lo);
    if (hi) p.set("max_price", hi);
  }
  if (state.point) { p.set("lat", state.point[0].toFixed(5)); p.set("lng", state.point[1].toFixed(5)); }
  if (state.near) p.set("radius_km", "15");
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p;
}
const filtered = () => Boolean(state.q || state.category || state.size || state.color || state.price || state.near || state.shop);

// ---------- meta / filters ----------
async function loadMeta() {
  const meta = state.meta = await api("/api/meta");
  $("#demo-bar").hidden = !meta.demo;
  const chips = $("#category-chips");
  const all = el("button.chip", { type: "button", "aria-pressed": String(!state.category), onclick: () => setFilter("category", "") }, "Barchasi");
  chips.replaceChildren(all, ...meta.categories.map(c =>
    el("button.chip", { type: "button", "aria-pressed": String(state.category === c.name), dataset: { value: c.name },
      onclick: () => setFilter("category", state.category === c.name ? "" : c.name) },
      c.name, el("span.count", c.count))));
  $("#f-size").append(...meta.sizes.map(s => el("option", { value: s }, `Oʻlcham: ${s}`)));
  $("#f-color").append(...meta.colors.map(c => el("option", { value: c }, `Rang: ${c}`)));
  for (const k of ["size", "color", "price", "sort"]) $(`#f-${k}`).value = state[k];
  $("#hero-q").value = state.q;
}

function syncChips() {
  $$("#category-chips .chip").forEach(chip => chip.setAttribute("aria-pressed",
    String((chip.dataset.value || "") === state.category)));
  $("#f-near").setAttribute("aria-pressed", String(state.near));
  $("#f-reset").hidden = !filtered();
}

function setFilter(key, value) {
  state[key] = value;
  state.offset = 0;
  syncChips();
  writeUrl();
  loadProducts();
  loadShops();
}

// ---------- products ----------
function skeletons(n = 8) { return Array.from({ length: n }, () => el("div.skeleton", { "aria-hidden": "true" })); }

function card(p) {
  const sizeMatch = state.size;
  return el("button.card", { type: "button", onclick: () => openProduct(p.id), "aria-label": `${p.name}, ${fmtPrice(p.price)}` },
    (() => {
      const art = productArt(p);
      if (!p.in_stock) art.append(el("span.pill.bad.flag", "Qolmagan"));
      else if (p.distance_km != null) art.append(el("span.pill.flag", "📍 " + fmtKm(p.distance_km)));
      return art;
    })(),
    el("div.card-body",
      el("h3", p.name),
      el("div.card-meta", swatch(p.color), p.color, " · ", p.shop?.name || ""),
      el("div.price", fmtPrice(p.price)),
      el("div.card-sizes", p.available_sizes.slice(0, 7).map(s => el(`span.size-dot${s === sizeMatch ? ".match" : ""}`, s)),
        p.available_sizes.length > 7 ? el("span.size-dot", "+" + (p.available_sizes.length - 7)) : null)));
}

async function loadProducts(append = false) {
  listAbort?.abort();
  listAbort = new AbortController();
  const grid = $("#products");
  if (!append) { grid.replaceChildren(...skeletons()); grid.setAttribute("aria-busy", "true"); }
  const sort = state.sort === "near" && !state.point ? "relevance" : state.sort;
  try {
    const data = await api("/api/products?" + params({ sort, limit: PAGE, offset: state.offset }), { signal: listAbort.signal });
    state.total = data.total;
    state.items = append ? state.items.concat(data.items) : data.items;
    if (!append) grid.replaceChildren();
    if (!state.items.length) {
      grid.replaceChildren(el("div.empty", el("b", "Hech narsa topilmadi"),
        "Filtrlarni yumshatib koʻring yoki boshqa soʻz bilan qidiring.",
        el("p.mt", el("button.btn", { onclick: resetFilters }, "Filtrlarni tozalash"))));
    } else {
      grid.append(...data.items.map(card));
    }
    $("#result-count").textContent = state.total ? `${state.total} ta kiyim` + (state.size ? ` · ${state.size} oʻlcham bor` : "") : "";
    $("#load-more").hidden = state.items.length >= state.total;
  } catch (e) {
    if (e.name === "AbortError") return;
    grid.replaceChildren(el("div.empty", el("b", "Katalog yuklanmadi"), e.message,
      el("p.mt", el("button.btn", { onclick: () => loadProducts() }, "Qayta urinish"))));
  } finally {
    grid.setAttribute("aria-busy", "false");
  }
}

function resetFilters() {
  Object.assign(state, { q: "", category: "", size: "", color: "", price: "", sort: "relevance", near: false, offset: 0 });
  for (const k of ["size", "color", "price", "sort"]) $(`#f-${k}`).value = state[k];
  $("#hero-q").value = "";
  if (state.shop) { state.shop = ""; setShopHeader(null); }
  setFilter("q", "");
}

// ---------- location ----------
function locate() {
  return new Promise(resolve => {
    if (state.point) return resolve(state.point);
    if (!navigator.geolocation) { toast("Qurilma joylashuvni aniqlay olmaydi", "error"); return resolve(null); }
    $("#location-note").textContent = "Joylashuv aniqlanmoqda…";
    navigator.geolocation.getCurrentPosition(pos => {
      state.point = [pos.coords.latitude, pos.coords.longitude];
      $("#location-note").textContent = "📍 Joylashuvingiz boʻyicha";
      if (map) showMe();
      resolve(state.point);
    }, () => {
      $("#location-note").textContent = "";
      toast("Joylashuvga ruxsat berilmadi", "error");
      resolve(null);
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
  });
}

// ---------- map ----------
let map = null, markers = null, meMarker = null, leafletLoading = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  leafletLoading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    s.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
    s.crossOrigin = "";
    s.onload = resolve; s.onerror = reject;
    document.head.append(s);
  });
  return leafletLoading;
}
async function initMap() {
  try { await loadLeaflet(); } catch { $("#map").replaceChildren(el("div.empty", "Xarita yuklanmadi. Internetni tekshiring.")); return; }
  map = L.map("map", { scrollWheelZoom: false, zoomControl: true }).setView([41.311, 69.27], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  markers = L.layerGroup().addTo(map);
  if (state.point) showMe();
  renderShops(lastShops);
}
function showMe() {
  const icon = L.divIcon({ className: "", html: '<div class="map-pin me"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
  meMarker?.remove();
  meMarker = L.marker(state.point, { icon, title: "Siz" }).addTo(map);
}

let lastShops = [];
async function loadShops() {
  try {
    const data = await api("/api/shops?" + params());
    lastShops = data.items;
    renderShops(lastShops);
  } catch { /* the catalog already shows the error */ }
}
function renderShops(shops) {
  const list = $("#shop-list");
  $("#map-caption").textContent = filtered()
    ? `${shops.length} ta doʻkonda mos kiyim bor` + (state.size ? ` (${state.size} oʻlcham)` : "")
    : `${shops.length} ta doʻkon`;
  list.replaceChildren(...(shops.length ? shops.map(s => el("button.shop-item", { type: "button", dataset: { id: s.id }, onclick: () => focusShop(s) },
    el("h3", s.name, s.verified ? el("span.pill.ok", "✓ tasdiqlangan") : null, s.demo ? el("span.pill", "namuna") : null,
      s.founding_partner ? el("span.pill.accent", "asoschi hamkor") : null),
    el("div.muted.small", [s.district, s.hours].filter(Boolean).join(" · ")),
    el("div.row-gap.small", filtered() ? el("b", `${s.matches} ta mos kiyim`) : el("span", `${s.matches} ta kiyim`),
      s.distance_km != null ? el("span.muted", "· " + fmtKm(s.distance_km)) : null))) : [el("div.empty", "Bu filtrlar boʻyicha doʻkon topilmadi.")]));
  if (!map) return;
  markers.clearLayers();
  const bounds = [];
  for (const s of shops) {
    if (s.lat == null) continue;
    const icon = L.divIcon({ className: "", html: `<div class="map-pin"><span>${Number(s.matches) || 0}</span></div>`, iconSize: [34, 34], iconAnchor: [17, 34] });
    const popup = el("div", el("b", s.name), el("br"), `${s.matches} ta kiyim`, el("br"),
      el("a", { href: `/shop/${s.slug}`, onclick: e => { e.preventDefault(); openShop(s.slug); } }, "Doʻkon katalogi →"));
    L.marker([s.lat, s.lng], { icon, title: s.name }).bindPopup(popup).addTo(markers);
    bounds.push([s.lat, s.lng]);
  }
  if (state.point) bounds.push(state.point);
  if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
  else if (bounds.length === 1) map.setView(bounds[0], 14);
}
function focusShop(s) {
  $$(".shop-item").forEach(x => x.classList.toggle("active", x.dataset.id === String(s.id)));
  if (map && s.lat != null) map.setView([s.lat, s.lng], 15);
  openShop(s.slug);
}

// ---------- shop view ----------
async function openShop(slug) {
  state.shop = slug;
  state.offset = 0;
  try {
    const data = await api(`/api/shops/${encodeURIComponent(slug)}`);
    setShopHeader(data.shop);
  } catch { state.shop = ""; setShopHeader(null); }
  history.pushState(null, "", `/shop/${slug}`);
  syncChips();
  loadProducts();
  $("#catalog").scrollIntoView({ behavior: "smooth" });
}
function setShopHeader(shop) {
  $("#catalog-eyebrow").textContent = shop ? [shop.district, shop.hours].filter(Boolean).join(" · ") || "Doʻkon" : "Barcha doʻkonlar";
  $("#catalog-title").replaceChildren(shop ? shop.name : "Katalog",
    shop ? el("button.btn.ghost.sm", { onclick: () => { state.shop = ""; setShopHeader(null); history.pushState(null, "", "/"); setFilter("q", state.q); } }, "✕ barcha doʻkonlar") : "");
}

// ---------- product sheet ----------
let current = null, chosenSize = "";
async function openProduct(id, push = true, preferSize = "") {
  const dialog = $("#product-dialog");
  $("#pd-body").replaceChildren(el("div.skeleton", { "aria-hidden": "true" }));
  openDialog(dialog);
  if (push && !location.pathname.startsWith("/p/")) history.pushState({ product: id }, "", `/p/${id}`);
  try {
    const q = state.point ? `?lat=${state.point[0]}&lng=${state.point[1]}` : "";
    current = await api(`/api/products/${id}${q}`);
  } catch (e) {
    $("#pd-body").replaceChildren(el("div.empty", el("b", "Mahsulot topilmadi"), e.message));
    return;
  }
  const wanted = [preferSize, state.size].find(s => s && current.available_sizes.includes(s));
  chosenSize = wanted || (current.available_sizes.length === 1 ? current.available_sizes[0] : "");
  renderProduct();
}

function renderProduct() {
  const p = current, s = p.shop;
  $("#pd-eyebrow").textContent = p.category;
  const sizes = el("div.sizes", { role: "group", "aria-label": "Oʻlcham" }, p.sizes.map(x =>
    el("button.size-btn", { type: "button", disabled: x.available <= 0, "aria-pressed": String(x.size === chosenSize),
      onclick: () => { chosenSize = x.size; renderProduct(); } },
      x.size, x.available > 0 && x.available <= 2 ? el("small", `${x.available} ta`) : null)));
  const inCompare = compare().includes(p.id);
  const mapsUrl = s.lat != null ? `https://yandex.uz/maps/?pt=${s.lng},${s.lat}&z=16&l=map` : null;
  $("#pd-body").replaceChildren(
    el("div.pd",
      productArt(p),
      el("div.pd-info",
        el("h2#pd-title", p.name),
        el("div.row-gap", el("span.pd-price", fmtPrice(p.price)), el("span.card-meta", swatch(p.color), p.color)),
        p.description ? el("p.muted", p.description) : null,
        el("div", el("div.label", "Oʻlcham"), el("div.hint", p.in_stock ? "Doʻkonda hozir bor oʻlchamlar" : "Hozircha barcha oʻlchamlar tugagan"), sizes),
        el("div.row-gap",
          el("button.btn.primary.grow", { disabled: !chosenSize, onclick: () => openReserve() },
            chosenSize ? `${chosenSize} oʻlchamni bron qilish` : "Oʻlchamni tanlang"),
          el("button.btn.accent", { onclick: () => tryOn3d({ ...p, recommended_size: chosenSize || null }) }, "🧍 3D kiyib koʻrish"),
          el("button.btn", { onclick: () => openTryOn(p) }, "📷 Suratda")),
        el("div.row-gap",
          el("button.btn.ghost.sm", { onclick: () => { toggleCompare(p.id); renderProduct(); } }, inCompare ? "✓ Tanlovda" : "＋ Solishtirishga"),
          el("button.btn.ghost.sm", { onclick: () => shareProducts([p.id]) }, "👨‍👩‍👧 Oilamga soʻray")),
        el("div.shop-card",
          el("h3", s.name, s.verified ? el("span.pill.ok", "✓ tasdiqlangan") : null, s.demo ? el("span.pill", "namuna") : null),
          el("div.muted", s.address || s.district),
          el("div.muted", [s.hours && `🕘 ${s.hours}`, s.distance_km != null && `📍 ${fmtKm(s.distance_km)}`].filter(Boolean).join("  ")),
          el("div.links",
            el("button.btn.sm", { onclick: () => { closeDialog($("#product-dialog")); openShop(s.slug); } }, "Doʻkon katalogi"),
            mapsUrl ? el("a.btn.sm", { href: mapsUrl, target: "_blank", rel: "noopener" }, "Yoʻl topish ↗") : null,
            s.phone ? el("a.btn.sm", { href: `tel:${s.phone}` }, "📞 Qoʻngʻiroq") : null)),
        p.demo ? el("div.notice.small", "Bu namuna mahsulot: bron yuborish mumkin, lekin haqiqiy doʻkon uni qabul qilmaydi.") : null)),
    p.similar?.length ? el("div", el("div.label", "Oʻxshash kiyimlar"),
      el("div.similar.mt", p.similar.map(x => el("button.card", { type: "button", onclick: () => openProduct(x.id, false) },
        productArt(x), el("div.card-body", el("h3", x.name), el("div.price", fmtPrice(x.price))))))) : null,
  );
}

$("#product-dialog").addEventListener("close", () => {
  if (location.pathname.startsWith("/p/")) history.replaceState(null, "", (state.shop ? `/shop/${state.shop}` : "/") + location.search);
});
window.addEventListener("cai:open-product", e => openProduct(Number(e.detail.id), true, e.detail.size));
window.addEventListener("popstate", () => {
  const m = location.pathname.match(/^\/p\/(\d+)/);
  if (m) openProduct(Number(m[1]), false);
  else if ($("#product-dialog").open) closeDialog($("#product-dialog"));
});

// ---------- reservation ----------
function openReserve() {
  const p = current;
  const cfg = state.meta?.features || {};
  $("#rv-product").replaceChildren(productArt(p), el("div",
    el("h3", p.name), el("div.row", `Oʻlcham: `, el("b", chosenSize), " · ", fmtPrice(p.price)), el("div.row", p.shop.name)));
  $("#rv-terms").textContent = `Doʻkon ${cfg.reservation_confirm_hours || 3} soat ichida tasdiqlaydi va kiyimni ${cfg.reservation_hold_hours || 24} soat olib qoʻyadi. Toʻlov — doʻkonda, kiyib koʻrganingizdan keyin.`;
  const saved = store.get("contact", {});
  const tgUser = tg?.initDataUnsafe?.user;
  $("#rv-name").value = saved.name || [tgUser?.first_name, tgUser?.last_name].filter(Boolean).join(" ");
  $("#rv-phone").value = saved.phone || "";
  $("#rv-note").value = "";
  $("#rv-agree").checked = false;
  $("#rv-error").textContent = "";
  openDialog($("#reserve-dialog"));
}
$("#rv-phone").addEventListener("input", e => { if (e.target.value.replace(/\D/g, "").length > 2) e.target.value = formatPhone(e.target.value); });
$("#reserve-form").addEventListener("submit", async e => {
  e.preventDefault();
  const button = $("#rv-submit");
  const body = { product_id: current.id, size: chosenSize, name: $("#rv-name").value.trim(), phone: $("#rv-phone").value,
    note: $("#rv-note").value.trim(), agree: $("#rv-agree").checked };
  if (body.name.length < 2) return void ($("#rv-error").textContent = "Ismingizni yozing.");
  if (body.phone.replace(/\D/g, "").length < 12) return void ($("#rv-error").textContent = "Telefon raqamini toʻliq yozing.");
  if (!body.agree) return void ($("#rv-error").textContent = "Rozilik belgisini qoʻying.");
  button.disabled = true; button.classList.add("loading");
  try {
    const { reservation, shop_notified } = await api("/api/reservations", { method: "POST", json: body });
    store.set("contact", { name: body.name, phone: body.phone });
    rememberReservation(reservation.code);
    showReserved(reservation, shop_notified);
    refreshBadge();
    renderProductAvailability();
  } catch (err) {
    $("#rv-error").textContent = err.message;
    if (err.body?.code === "DUPLICATE") rememberReservation(err.body.reservation?.code);
  } finally {
    button.disabled = false; button.classList.remove("loading");
  }
});
function showReserved(r, notified) {
  closeDialog($("#reserve-dialog"));
  const body = $("#pd-body");
  body.replaceChildren(el("div.center",
    el("div.success-mark", "✓"),
    el("h2.mt", "Bron yuborildi"),
    el("p.muted.my", `${r.product.name} · ${r.size} · ${r.shop.name}`),
    el("p.notice.info.small", notified
      ? `Doʻkon Telegram orqali xabar oldi. Tasdiqlash muddati: ${fmtLeft(r.confirm_by)}.`
      : `Doʻkon tasdiqlashi kerak (${fmtLeft(r.confirm_by)} ichida). Holatni “Bronlarim” boʻlimida kuzating.`),
    el("div.row-gap.mt", el("button.btn.primary", { onclick: () => { closeDialog($("#product-dialog")); openReservations(); } }, "Bronlarim"),
      el("button.btn", { "data-close": "" }, "Katalogga qaytish"))));
}
function renderProductAvailability() { /* the sheet now shows the success state; the list refreshes on next open */ }

const myCodes = () => store.get("reservations", []);
function rememberReservation(code) {
  if (!code) return;
  store.set("reservations", [code, ...myCodes().filter(c => c !== code)].slice(0, 20));
}

const RES_PILL = { pending: "warn", confirmed: "ok", declined: "bad", expired: "", cancelled: "", visited: "ok", sold: "ok" };
async function openReservations() {
  openDialog($("#reservations-dialog"));
  const list = $("#mr-list");
  list.replaceChildren(el("div.skeleton", { "aria-hidden": "true" }));
  try {
    const { items } = await api("/api/reservations/mine?codes=" + encodeURIComponent(myCodes().join(",")));
    list.replaceChildren(...(items.length ? items.map(resItem) : [el("div.empty", el("b", "Hozircha bron yoʻq"), "Kiyim tanlab, oʻlchamini bron qiling.")]));
    setBadge(items.filter(r => r.status === "pending" || r.status === "confirmed").length);
  } catch (e) {
    list.replaceChildren(el("div.empty", e.message));
  }
}
function resItem(r) {
  const active = r.status === "pending" || r.status === "confirmed";
  const mapsUrl = r.shop.lat != null ? `https://yandex.uz/maps/?pt=${r.shop.lng},${r.shop.lat}&z=16&l=map` : null;
  return el("div.res", productArt(r.product),
    el("div",
      el("h3", r.product.name),
      el("div.row", el(`span.pill.${RES_PILL[r.status] || ""}`, r.status_label), `${r.size} · ${fmtPrice(r.product.price)}`),
      el("div.row", r.shop.name, r.shop.hours ? ` · 🕘 ${r.shop.hours}` : ""),
      el("div.row", r.status === "pending" ? `Tasdiqlash: ${fmtLeft(r.confirm_by)}` :
        r.status === "confirmed" ? `Olib qoʻyilgan: ${fmtLeft(r.hold_until)}` : fmtTime(r.created_at)),
      el("div.actions",
        active && mapsUrl ? el("a.btn.sm", { href: mapsUrl, target: "_blank", rel: "noopener" }, "Yoʻl topish ↗") : null,
        active && r.shop.phone ? el("a.btn.sm", { href: `tel:${r.shop.phone}` }, "📞") : null,
        active ? el("button.btn.sm.danger", { onclick: async () => {
          if (!confirm("Bronni bekor qilasizmi?")) return;
          try { await api(`/api/reservations/${r.code}/cancel`, { method: "POST" }); toast("Bron bekor qilindi"); openReservations(); }
          catch (e) { toast(e.message, "error"); }
        } }, "Bekor qilish") : null)));
}
function setBadge(n) { $$("[data-res-badge]").forEach(b => { b.hidden = !n; b.textContent = n; }); }
async function refreshBadge() {
  try {
    const { items } = await api("/api/reservations/mine?codes=" + encodeURIComponent(myCodes().join(",")));
    setBadge(items.filter(r => r.status === "pending" || r.status === "confirmed").length);
  } catch { /* offline */ }
}

$("#delete-data").addEventListener("click", async () => {
  if (!confirm("Barcha try-on suratlari, ulashishlar va bronlardagi shaxsiy maʼlumotlar oʻchiriladi. Davom etasizmi?")) return;
  try {
    await api("/api/me/data", { method: "DELETE" });
    store.set("reservations", []); store.set("contact", {}); store.set("compare", []);
    myPhoto = null;
    toast("Maʼlumotlaringiz oʻchirildi");
    openReservations(); renderTray();
  } catch (e) { toast(e.message, "error"); }
});

// ---------- try-on ----------
let myPhoto = null; // kept in memory only: "upload once, try many"
let tryStatus = null;
async function openTryOn(product) {
  openDialog($("#tryon-dialog"));
  const body = $("#to-body"), foot = $("#to-foot");
  foot.replaceChildren();
  try { tryStatus ??= await api("/api/try-on/status"); } catch (e) { body.replaceChildren(el("div.notice.bad", e.message)); return; }
  if (!tryStatus.enabled) {
    body.replaceChildren(
      el("div.res", productArt(product), el("div", el("h3", product.name), el("div.row", product.shop?.name || ""))),
      el("div.notice.info", el("b", "Virtual kiyib koʻrish tez orada. "),
        "AI modeli hali ulanmagan, shuning uchun suratingizni soʻramaymiz va hech narsa yuklanmaydi. ",
        "Hozircha oʻlchamni bron qilib, doʻkonda kiyib koʻrishingiz mumkin."),
      el("div.notice.small", "Ishga tushganda: surat faqat kiyim kiydirish uchun ishlatiladi, asl surat darhol, natija esa ",
        `${tryStatus.retention_hours} soatdan keyin oʻchiriladi. Doʻkonlar suratingizni koʻrmaydi.`));
    foot.replaceChildren(el("button.btn", { "data-close": "" }, "Yopish"));
    return;
  }
  renderTryOnForm(product);
}
function renderTryOnForm(product) {
  const body = $("#to-body"), foot = $("#to-foot");
  const preview = el("img", { alt: "Tanlangan surat", hidden: !myPhoto });
  if (myPhoto) preview.src = URL.createObjectURL(myPhoto);
  const input = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp", "aria-label": "Surat tanlash" });
  const drop = el("label.photo-drop", input, preview,
    el("span", myPhoto ? "Boshqa surat tanlash" : "📷 Toʻliq boʻy, yorugʻ joyda tushgan suratingizni tanlang"),
    el("span.hint", "JPG, PNG yoki WebP · 8 MB gacha"));
  const consent = el("input", { type: "checkbox" });
  const err = el("p.form-error", { role: "alert" });
  input.addEventListener("change", () => {
    const f = input.files[0];
    if (!f) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(f.type) || f.size > 8 * 1024 * 1024) {
      err.textContent = "JPG, PNG yoki WebP, 8 MB gacha boʻlsin."; return;
    }
    myPhoto = f; err.textContent = "";
    preview.src = URL.createObjectURL(f); preview.hidden = false;
    drop.querySelector("span").textContent = "Boshqa surat tanlash";
  });
  body.replaceChildren(
    el("div.res", productArt(product), el("div", el("h3", product.name), el("div.row", product.shop?.name || ""))),
    tryStatus.demo ? el("div.notice.small", "DEMO rejim: natija AI emas, faqat interfeysni tekshirish uchun.") : null,
    drop,
    el("label.check", consent, el("span", `Suratim faqat shu kiyimni kiydirib koʻrsatish uchun qayta ishlanishiga roziman. Asl surat darhol, natija ${tryStatus.retention_hours} soatdan keyin oʻchiriladi.`)),
    err);
  const go = el("button.btn.primary", { onclick: async () => {
    if (!myPhoto) return void (err.textContent = "Avval suratingizni tanlang.");
    if (!consent.checked) return void (err.textContent = "Rozilik belgisini qoʻying.");
    const form = new FormData();
    form.append("photo", myPhoto); form.append("product_id", product.id); form.append("consent", "1");
    go.disabled = true; go.classList.add("loading");
    try {
      const { job } = await api("/api/try-on/jobs", { method: "POST", form });
      pollJob(job, product);
    } catch (e) { err.textContent = e.message; go.disabled = false; go.classList.remove("loading"); }
  } }, "Kiyib koʻrish");
  foot.replaceChildren(el("button.btn", { "data-close": "" }, "Bekor"), go);
}
async function pollJob(job, product) {
  const body = $("#to-body"), foot = $("#to-foot");
  body.replaceChildren(el("div.center", el("p.label", "AI kiyimni kiydiryapti…"), el("p.muted.small.my", "Odatda 20–60 soniya. Oynani yopsangiz ham natija “Kiyinish xonam”da saqlanadi.")),
    el("div.progress", el("i")));
  foot.replaceChildren();
  const started = Date.now();
  while (job.status === "queued" || job.status === "processing") {
    await new Promise(r => setTimeout(r, 2000));
    if (Date.now() - started > 4 * 60 * 1000) break;
    try { ({ job } = await api(`/api/try-on/jobs/${job.id}`)); } catch { /* retry */ }
  }
  if (!$("#tryon-dialog").open) { if (job.status === "completed") toast("Kiyib koʻrish natijasi tayyor"); return; }
  if (job.status !== "completed") {
    body.replaceChildren(el("div.notice.bad", job.error || "Natija olinmadi. Qayta urinib koʻring."));
    foot.replaceChildren(el("button.btn", { onclick: () => renderTryOnForm(product) }, "Qayta urinish"));
    return;
  }
  showResult(job, product);
}
async function showResult(job, product) {
  const body = $("#to-body"), foot = $("#to-foot");
  const img = el("img", { alt: `${product.name} — kiyib koʻrish natijasi` });
  try { img.src = URL.createObjectURL(await apiBlob(job.result)); } catch { img.alt = "Rasm yuklanmadi"; }
  body.replaceChildren(
    job.demo ? el("div.notice.small", "DEMO: bu AI natija emas.") : null,
    el("div.tryon-result", el("figure", img, el("figcaption", "Siz")), el("figure", productArt(product), el("figcaption", product.name))),
    el("p.hint", job.keep ? "Natija 30 kun saqlanadi." : `Natija avtomatik oʻchishiga: ${fmtLeft(job.expires_at)}.`));
  foot.replaceChildren(
    el("button.btn.sm", { onclick: async () => {
      ({ job } = await api(`/api/try-on/jobs/${job.id}/keep`, { method: "POST", json: { keep: !job.keep } }));
      toast(job.keep ? "Natija saqlandi" : "Natija 24 soatda oʻchadi"); showResult(job, product);
    } }, job.keep ? "Saqlamaslik" : "💾 Saqlash"),
    el("button.btn.sm.danger", { onclick: async () => { await api(`/api/try-on/jobs/${job.id}`, { method: "DELETE" }); toast("Oʻchirildi"); closeDialog($("#tryon-dialog")); } }, "🗑 Oʻchirish"),
    el("button.btn.sm", { onclick: () => shareProducts([product.id]) }, "Oilamga soʻray"),
    el("button.btn.primary.sm", { onclick: () => { closeDialog($("#tryon-dialog")); if (current?.id === product.id && $("#product-dialog").open) return; openProduct(product.id); } }, "Bron qilish"));
}
async function openTryOnHistory() {
  openDialog($("#tryon-history-dialog"));
  const body = $("#th-body");
  body.replaceChildren(el("div.skeleton", { "aria-hidden": "true" }));
  try {
    tryStatus ??= await api("/api/try-on/status");
    const { items } = await api("/api/try-on/jobs");
    if (!tryStatus.enabled && !items.length) {
      body.replaceChildren(el("div.empty", el("b", "Virtual kiyinish xonasi tez orada"),
        "Hozircha kiyimni tanlab, doʻkonda kiyib koʻrish uchun bron qiling."));
      return;
    }
    if (!items.length) { body.replaceChildren(el("div.empty", el("b", "Hali kiyib koʻrmadingiz"), "Katalogdan kiyim tanlab “Kiyib koʻrish”ni bosing.")); return; }
    body.replaceChildren(el("div.res-list", items.map(j => el("div.res", el("div.art.art-placeholder", el("span.art-icon", "🪞")),
      el("div", el("h3", `Mahsulot #${j.product_id}`), el("div.row", { "data-status": j.status }, j.status === "completed" ? "Tayyor" : j.status === "failed" ? "Xato" : "Jarayonda", " · ", fmtTime(j.created_at)),
        el("div.actions", el("button.btn.sm", { onclick: async () => { closeDialog($("#tryon-history-dialog")); const p = await api(`/api/products/${j.product_id}`); openDialog($("#tryon-dialog")); j.status === "completed" ? showResult(j, p) : renderTryOnForm(p); } }, "Ochish"),
          el("button.btn.sm.danger", { onclick: async () => { await api(`/api/try-on/jobs/${j.id}`, { method: "DELETE" }); openTryOnHistory(); } }, "Oʻchirish")))))));
  } catch (e) { body.replaceChildren(el("div.empty", e.message)); }
}

// ---------- compare & share ("Oilamga yuborib soʻray") ----------
const compare = () => store.get("compare", []);
function toggleCompare(id) {
  let ids = compare();
  if (ids.includes(id)) ids = ids.filter(x => x !== id);
  else if (ids.length >= 4) { toast("4 tagacha kiyim tanlash mumkin", "error"); return; }
  else ids = [...ids, id];
  store.set("compare", ids);
  renderTray();
}
function renderTray() {
  const ids = compare();
  $("#compare-tray").hidden = !ids.length;
  $("#compare-label").textContent = `${ids.length} ta kiyim tanlandi`;
}
async function shareProducts(ids) {
  try {
    const { url } = await api("/api/shares", { method: "POST", json: { product_ids: ids } });
    shareLink(url, ids.length > 1 ? "Qaysi biri menga yarashadi? Ovoz bering 👇" : "Shu kiyim menga yarashadimi? Fikringizni yozing 👇");
  } catch (e) { toast(e.message, "error"); }
}
$("#compare-share").addEventListener("click", () => shareProducts(compare()));
$("#compare-clear").addEventListener("click", () => { store.set("compare", []); renderTray(); });

// ---------- wiring ----------
$("#hero-search").addEventListener("submit", e => {
  e.preventDefault();
  setFilter("q", $("#hero-q").value.trim());
  $("#catalog").scrollIntoView({ behavior: "smooth" });
});
let qTimer;
$("#hero-q").addEventListener("input", e => { clearTimeout(qTimer); qTimer = setTimeout(() => setFilter("q", e.target.value.trim()), 350); });
for (const k of ["size", "color", "price"]) $(`#f-${k}`).addEventListener("change", e => setFilter(k, e.target.value));
$("#f-sort").addEventListener("change", async e => {
  if (e.target.value === "near" && !(await locate())) { e.target.value = state.sort; return; }
  setFilter("sort", e.target.value);
});
$("#f-near").addEventListener("click", async () => {
  if (!state.near && !(await locate())) return;
  state.near = !state.near;
  if (state.near) { state.sort = "near"; $("#f-sort").value = "near"; }
  setFilter("near", state.near);
});
$("#f-reset").addEventListener("click", resetFilters);
$("#load-more").addEventListener("click", () => { state.offset += PAGE; loadProducts(true); });
document.addEventListener("click", e => {
  const opener = e.target.closest("[data-open]");
  if (!opener) return;
  e.preventDefault();
  if (opener.dataset.open === "reservations") openReservations();
  if (opener.dataset.open === "tryon-history") openTryOnHistory();
});
const filters = $("#filters");
new IntersectionObserver(([entry]) => filters.classList.toggle("stuck", entry.intersectionRatio < 1),
  { threshold: [1], rootMargin: "-65px 0px 0px 0px" }).observe(filters);
new IntersectionObserver((entries, obs) => {
  if (entries.some(x => x.isIntersecting)) { obs.disconnect(); initMap(); }
}, { rootMargin: "300px" }).observe($("#map"));

async function start() {
  readUrl();
  try { await loadMeta(); } catch (e) { toast(e.message, "error"); }
  syncChips();
  if (state.shop) {
    try { setShopHeader((await api(`/api/shops/${encodeURIComponent(state.shop)}`)).shop); }
    catch { state.shop = ""; setShopHeader(null); }
  }
  loadProducts();
  loadShops();
  renderTray();
  refreshBadge();
  const start = tg?.initDataUnsafe?.start_param || new URLSearchParams(location.search).get("startapp") || "";
  const direct = location.pathname.match(/^\/p\/(\d+)/);
  if (direct) openProduct(Number(direct[1]), false);
  else if (/^p_\d+$/.test(start)) openProduct(Number(start.slice(2)));
  else if (/^shop_[\w-]+$/.test(start)) openShop(start.slice(5));
}
start();
