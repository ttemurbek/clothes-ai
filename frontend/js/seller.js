// Seller panel: sign in / register, statistics, reservations, products and stock, shop profile.
import { $, $$, api, closeDialog, el, fmtLeft, fmtPrice, fmtTime, formatPhone, openDialog, productArt, toast } from "./common.js";

let me = null, products = [], editing = null, pickMap = null, pickMarker = null;

// ---------- auth ----------
function showAuth() { $("#auth").hidden = false; $("#panel").hidden = true; $("#logout").hidden = true; }
function selectAuthTab(register) {
  $("#tab-login").setAttribute("aria-selected", String(!register));
  $("#tab-register").setAttribute("aria-selected", String(register));
  $("#login-form").hidden = register;
  $("#register-form").hidden = !register;
}
$("#tab-login").addEventListener("click", () => selectAuthTab(false));
$("#tab-register").addEventListener("click", () => selectAuthTab(true));
for (const id of ["#rg-phone"]) $(id).addEventListener("input", e => { if (e.target.value.replace(/\D/g, "").length > 2) e.target.value = formatPhone(e.target.value); });

async function submit(form, button, fn) {
  button.disabled = true; button.classList.add("loading");
  try { await fn(); } finally { button.disabled = false; button.classList.remove("loading"); }
}
$("#login-form").addEventListener("submit", e => {
  e.preventDefault();
  submit(e.target, e.submitter || $("#login-form button"), async () => {
    try {
      me = await api("/api/seller/login", { method: "POST", json: { login: $("#li-login").value, password: $("#li-password").value } });
      $("#li-password").value = "";
      enterPanel();
    } catch (err) { $("#li-error").textContent = err.message; }
  });
});
$("#register-form").addEventListener("submit", e => {
  e.preventDefault();
  submit(e.target, e.submitter || $("#register-form button"), async () => {
    try {
      me = await api("/api/seller/register", { method: "POST", json: {
        shop_name: $("#rg-shop").value, district: $("#rg-district").value, address: $("#rg-address").value,
        phone: $("#rg-phone").value, name: $("#rg-name").value, login: $("#rg-login").value,
        password: $("#rg-password").value, agree: $("#rg-agree").checked } });
      enterPanel();
      toast("Doʻkon roʻyxatdan oʻtdi");
    } catch (err) { $("#rg-error").textContent = err.message; }
  });
});
$("#logout").addEventListener("click", async () => { await api("/api/seller/logout", { method: "POST" }); location.reload(); });

// ---------- panel ----------
function enterPanel() {
  $("#auth").hidden = true; $("#panel").hidden = false; $("#logout").hidden = false;
  renderStatus();
  fillCategoryOptions();
  showTab(location.hash.slice(1) || "overview");
  refreshPending();
}
function renderStatus() {
  const shop = me.shop;
  const note = $("#status-note");
  const parts = [];
  if (shop.status === "pending") parts.push(el("div.notice.mt", el("b", "Doʻkon tekshirilmoqda. "),
    "Maʼlumotlaringiz tasdiqlangach katalogda koʻrinadi. Hozir mahsulot va qoldiqlarni qoʻshib turing."));
  if (shop.demo) parts.push(el("div.notice.mt", el("b", "Namuna doʻkon. "), "Bu demo hisob — koʻrsatkichlar haqiqiy savdo emas."));
  if (!shop.telegram_linked) parts.push(el("div.notice.info.mt", "Bronlar haqida darhol xabar olish uchun ",
    el("a", { href: "#shop", onclick: () => showTab("shop") }, "Telegramni ulang"), "."));
  if (shop.lat == null) parts.push(el("div.notice.info.mt", "Xaridorlar sizni xaritada topishi uchun ",
    el("a", { href: "#shop", onclick: () => showTab("shop") }, "doʻkon joyini belgilang"), "."));
  note.replaceChildren(...parts);
  if (parts.length) note.lastChild.classList.add("mb");
}
function showTab(name) {
  if (!["overview", "reservations", "products", "shop"].includes(name)) name = "overview";
  $$(".side button").forEach(b => b.setAttribute("aria-current", String(b.dataset.tab === name)));
  $$("[data-section]").forEach(s => s.hidden = s.dataset.section !== name);
  history.replaceState(null, "", "#" + name);
  ({ overview: loadStats, reservations: loadReservations, products: loadProducts, shop: fillShop })[name]();
}
$$(".side button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));

// ---------- statistics ----------
const KIND = [["view", "Koʻrishlar"], ["tryon", "Kiyib koʻrishlar"], ["share", "Ulashishlar"], ["reservation", "Bronlar"], ["visit", "Kelgan xaridorlar"]];
async function loadStats() {
  const days = $("#stats-days").value;
  const data = await api(`/api/seller/stats?days=${days}`);
  $("#metrics").replaceChildren(...KIND.map(([k, label]) => el("div.metric", el("span", label), el("strong", data.totals[k]),
    el("small", `${days} kunda`))));
  const max = Math.max(1, data.totals.view);
  $("#funnel").replaceChildren(...KIND.filter(([k]) => k !== "share").map(([k, label]) => {
    const bar = el("i"); bar.style.width = `${(data.totals[k] / max) * 100}%`;
    return el("div.funnel-row", el("span", label), el("div.bar", bar), el("b", data.totals[k]));
  }));
  const byDay = new Map(data.series.map(d => [d.date, d]));
  const cols = [];
  const peak = Math.max(1, ...data.series.map(d => d.view + d.reservation));
  for (let i = Number(days) - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    const row = byDay.get(d) || { view: 0, reservation: 0 };
    const a = el("i"), b = el("i.r");
    a.style.height = `${(row.view / peak) * 100}%`; b.style.height = `${(row.reservation / peak) * 100}%`;
    cols.push(el("div.col", { title: `${d}: ${row.view} koʻrish, ${row.reservation} bron` }, a, b));
  }
  $("#chart").replaceChildren(...cols);
  $("#top-products").replaceChildren(data.top_products.length
    ? el("thead", el("tr", el("th", "Mahsulot"), el("th", "Koʻrish"), el("th", "Try-on"), el("th", "Bron"), el("th", "Keldi")))
    : el("tbody", el("tr", el("td.muted", "Hali maʼlumot yoʻq. Mahsulot qoʻshing va doʻkon tasdiqlanishini kuting."))),
    el("tbody", data.top_products.map(p => el("tr", el("td", p.name), el("td", p.view || 0), el("td", p.tryon || 0),
      el("td", p.reservation || 0), el("td", p.visit || 0)))));
}
$("#stats-days").addEventListener("change", loadStats);

// ---------- reservations ----------
const RES_PILL = { pending: "warn", confirmed: "ok", declined: "bad", expired: "", cancelled: "", visited: "ok", sold: "ok" };
async function loadReservations() {
  const list = $("#res-list");
  list.replaceChildren(el("div.skeleton", { "aria-hidden": "true" }));
  const data = await api(`/api/seller/reservations?status=${$("#res-filter").value}`);
  setPending(data.pending);
  list.replaceChildren(...(data.items.length ? data.items.map(resRow) : [el("div.empty", el("b", "Bron yoʻq"),
    "Yangi bron kelganda shu yerda va Telegramda koʻrasiz.")]));
}
function resRow(r) {
  const act = (action, label, cls = "") => el(`button.btn.sm${cls}`, { onclick: async e => {
    e.target.disabled = true;
    try { await api(`/api/seller/reservations/${r.id}/${action}`, { method: "POST" }); toast("Saqlandi"); loadReservations(); }
    catch (err) { toast(err.message, "error"); e.target.disabled = false; }
  } }, label);
  return el("div.res", productArt(r.product),
    el("div",
      el("h3", `#${r.id} · ${r.product.name}`),
      el("div.row", el(`span.pill.${RES_PILL[r.status] || ""}`, r.status_label), el("b", r.size), fmtPrice(r.product.price)),
      el("div.row", "👤 ", r.name, " · ", r.phone ? el("a", { href: `tel:${r.phone}` }, r.phone) : "—", r.via_telegram ? " · Telegram" : ""),
      r.note ? el("div.row", "💬 ", r.note) : null,
      el("div.row", fmtTime(r.created_at),
        r.status === "pending" ? ` · tasdiqlash uchun ${fmtLeft(r.confirm_by)}` : "",
        r.status === "confirmed" ? ` · olib qoʻyilgan: ${fmtLeft(r.hold_until)}` : ""),
      el("div.actions",
        r.status === "pending" ? [act("confirm", "✅ Tasdiqlash", ".primary"), act("decline", "Rad etish", ".danger")] : null,
        r.status === "confirmed" ? [act("visited", "🚶 Keldi"), act("sold", "🛍 Sotildi", ".primary")] : null,
        r.status === "visited" ? act("sold", "🛍 Sotildi", ".primary") : null)));
}
$("#res-filter").addEventListener("change", loadReservations);
function setPending(n) { const b = $("#pending-badge"); b.hidden = !n; b.textContent = n; }
async function refreshPending() { try { setPending((await api("/api/seller/reservations?status=pending")).pending); } catch { /* ignore */ } }
setInterval(() => { if (me && document.visibilityState === "visible") refreshPending(); }, 60000);

// ---------- products ----------
async function loadProducts() {
  const { items } = await api("/api/seller/products");
  products = items;
  const units = items.reduce((n, p) => n + p.variants.reduce((m, v) => m + v.stock, 0), 0);
  $("#products-summary").textContent = `${items.length} ta mahsulot · ${units} dona qoldiq`;
  const table = $("#product-table");
  if (!items.length) {
    table.replaceChildren(el("tbody", el("tr", el("td", el("div.empty", el("b", "Hali mahsulot yoʻq"), "Birinchi mahsulotni qoʻshing — 1 daqiqa vaqt oladi.")))));
    return;
  }
  table.replaceChildren(
    el("thead", el("tr", el("th", "Mahsulot"), el("th", "Narx"), el("th", "Qoldiq (oʻlcham: dona)"), el("th", "Holat"), el("th", ""))),
    el("tbody", items.map(p => el("tr",
      el("td.full", el("div.prod-cell", productArt(p, "art.thumb"), el("div", el("b", p.name), el("span.muted.small", `${p.category} · ${p.color}`)))),
      el("td", fmtPrice(p.price)),
      el("td", el("div.stock-line", p.variants.map(v => el(`span${v.stock - v.reserved <= 0 ? ".zero" : ""}`,
        `${v.size}: ${v.stock}` + (v.reserved ? ` (${v.reserved} bron)` : ""))))),
      el("td", p.active ? el("span.pill.ok", "koʻrinadi") : el("span.pill", "yashirin")),
      el("td", el("button.btn.sm", { onclick: () => openEditor(p) }, "Tahrirlash"))))));
}
$("#add-product").addEventListener("click", () => openEditor(null));

function fillCategoryOptions() {
  $("#pe-category").replaceChildren(...me.options.categories.map(c => el("option", { value: c }, c)));
  $("#pe-color").replaceChildren(...me.options.colors.map(c => el("option", { value: c }, c)));
  $("#pe-ai-row").hidden = !me.options.ai_photo;
}
function variantRow(size = "", stock = 1) {
  const row = el("div.variant-row",
    el("input.input", { placeholder: "Oʻlcham (M, 48…)", value: size, "aria-label": "Oʻlcham", maxlength: "16" }),
    el("input.input", { type: "number", min: "0", max: "9999", value: String(stock), "aria-label": "Qoldiq, dona" }),
    el("button.icon-btn", { type: "button", "aria-label": "Oʻlchamni olib tashlash", onclick: () => row.remove() }, "✕"));
  return row;
}
let pendingImage = null;
function openEditor(p) {
  editing = p;
  pendingImage = null;
  $("#pe-title").textContent = p ? "Mahsulotni tahrirlash" : "Yangi mahsulot";
  $("#pe-name").value = p?.name || "";
  $("#pe-category").value = p?.category || me.options.categories[0];
  $("#pe-color").value = p?.color || me.options.colors[0];
  $("#pe-price").value = p ? new Intl.NumberFormat("uz-UZ").format(p.price).replace(/,/g, " ") : "";
  $("#pe-description").value = p?.description || "";
  $("#pe-active").checked = p ? p.active : true;
  $("#pe-variants").replaceChildren(...(p ? p.variants.map(v => variantRow(v.size, v.stock)) : [variantRow("M", 1)]));
  $("#pe-preview").hidden = !p?.image;
  if (p?.image) $("#pe-preview").src = p.image;
  $("#pe-drop-text").textContent = p?.image ? "Rasmni almashtirish" : "📷 Telefonda oddiy suratga oling va shu yerga yuklang";
  $("#pe-remove-image").hidden = !p?.image;
  $("#pe-delete").hidden = !p;
  $("#pe-error").textContent = "";
  $("#pe-image").value = "";
  openDialog($("#product-editor"));
}
$("#pe-image").addEventListener("change", e => {
  const f = e.target.files[0];
  if (!f) return;
  if (f.size > 8 * 1024 * 1024) { $("#pe-error").textContent = "Rasm 8 MB dan kichik boʻlsin."; return; }
  pendingImage = f;
  $("#pe-preview").src = URL.createObjectURL(f); $("#pe-preview").hidden = false;
  $("#pe-drop-text").textContent = "Saqlaganda yuklanadi";
});
$("#pe-add-size").addEventListener("click", () => $("#pe-variants").append(variantRow("", 1)));
$$("[data-preset]").forEach(b => b.addEventListener("click", () => {
  const existing = new Set($$("#pe-variants .variant-row input:first-child").map(i => i.value.trim().toUpperCase()));
  for (const s of b.dataset.preset.split(",")) if (!existing.has(s.toUpperCase())) $("#pe-variants").append(variantRow(s, 0));
}));
$("#pe-price").addEventListener("input", e => {
  const digits = e.target.value.replace(/\D/g, "");
  e.target.value = digits ? Number(digits).toLocaleString("ru-RU").replace(/ /g, " ") : "";
});
$("#pe-form").addEventListener("submit", async e => {
  e.preventDefault();
  const variants = $$("#pe-variants .variant-row").map(row => {
    const [size, stock] = row.querySelectorAll("input");
    return { size: size.value.trim(), stock: Number(stock.value || 0) };
  }).filter(v => v.size);
  const body = { name: $("#pe-name").value.trim(), category: $("#pe-category").value, color: $("#pe-color").value,
    price: Number($("#pe-price").value.replace(/\D/g, "")), description: $("#pe-description").value.trim(),
    active: $("#pe-active").checked, variants };
  const button = $("#pe-save");
  button.disabled = true; button.classList.add("loading");
  try {
    const { product } = editing
      ? await api(`/api/seller/products/${editing.id}`, { method: "PATCH", json: body })
      : await api("/api/seller/products", { method: "POST", json: body });
    if (pendingImage) {
      const form = new FormData();
      form.append("image", pendingImage);
      if ($("#pe-ai").checked) form.append("ai", "1");
      const result = await api(`/api/seller/products/${product.id}/image`, { method: "POST", form });
      if (result.ai_note) toast(result.ai_note, "error");
      else if (result.ai_used) toast("AI fotograf rasmni tayyorladi ✨");
    }
    closeDialog($("#product-editor"));
    toast("Saqlandi");
    loadProducts();
  } catch (err) {
    $("#pe-error").textContent = err.message;
  } finally {
    button.disabled = false; button.classList.remove("loading");
  }
});
$("#pe-remove-image").addEventListener("click", async () => {
  if (!editing) return;
  await api(`/api/seller/products/${editing.id}/image`, { method: "DELETE" });
  $("#pe-preview").hidden = true; $("#pe-remove-image").hidden = true;
  toast("Rasm olib tashlandi"); loadProducts();
});
$("#pe-delete").addEventListener("click", async () => {
  if (!editing || !confirm(`“${editing.name}” oʻchirilsinmi? Buni qaytarib boʻlmaydi.`)) return;
  try {
    await api(`/api/seller/products/${editing.id}`, { method: "DELETE" });
    closeDialog($("#product-editor")); toast("Oʻchirildi"); loadProducts();
  } catch (err) { $("#pe-error").textContent = err.message; }
});

// ---------- shop profile ----------
let picked = null;
function fillShop() {
  const shop = me.shop, form = $("#shop-form");
  for (const name of ["name", "phone", "district", "hours", "address", "instagram", "description"]) form.elements[name].value = shop[name] || "";
  picked = shop.lat != null ? [shop.lat, shop.lng] : null;
  $("#tg-state").textContent = shop.telegram_linked
    ? "✅ Telegram ulangan: yangi bronlar shu chatga keladi va tugma bilan tasdiqlanadi."
    : me.options.telegram_bot ? "Ulansa, har bir yangi bron Telegramga keladi va bir tugma bilan tasdiqlanadi." : "Telegram bot hali sozlanmagan (administrator).";
  $("#tg-link").textContent = shop.telegram_linked ? "Boshqa chatga ulash" : "Telegramga ulash";
  $("#tg-link").disabled = !me.options.telegram_bot;
  initPickMap();
}
async function initPickMap() {
  if (!window.L) {
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      s.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="; s.crossOrigin = "";
      s.onload = resolve; s.onerror = reject; document.head.append(s);
    }).catch(() => { $("#pick-hint").textContent = "Xarita yuklanmadi."; });
    if (!window.L) return;
  }
  if (!pickMap) {
    pickMap = L.map("pick-map").setView(picked || [41.311, 69.27], picked ? 15 : 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(pickMap);
    pickMap.on("click", e => setPick([e.latlng.lat, e.latlng.lng]));
  } else {
    setTimeout(() => pickMap.invalidateSize(), 50);
  }
  if (picked) setPick(picked, false);
}
function setPick(point, announce = true) {
  picked = point;
  if (pickMarker) pickMarker.setLatLng(point); else pickMarker = L.marker(point).addTo(pickMap);
  $("#pick-hint").textContent = announce ? "Belgilandi — “Saqlash”ni bosing." : "Joy belgilangan. Oʻzgartirish uchun xaritani bosing.";
}
$("#shop-form").addEventListener("submit", async e => {
  e.preventDefault();
  const form = e.target;
  const body = Object.fromEntries(["name", "phone", "district", "hours", "address", "instagram", "description"].map(n => [n, form.elements[n].value]));
  if (picked) { body.lat = picked[0]; body.lng = picked[1]; }
  try {
    me = await api("/api/seller/shop", { method: "PATCH", json: body });
    $("#shop-error").textContent = "";
    renderStatus(); toast("Doʻkon maʼlumotlari saqlandi");
  } catch (err) { $("#shop-error").textContent = err.message; }
});
$("#tg-link").addEventListener("click", async () => {
  try {
    const { url } = await api("/api/seller/shop/telegram-link", { method: "POST" });
    window.open(url, "_blank", "noopener");
    $("#tg-state").textContent = "Telegramda “Start”ni bosing, soʻng bu sahifani yangilang.";
  } catch (err) { toast(err.message, "error"); }
});
$("#password-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api("/api/seller/password", { method: "POST", json: { current: $("#pw-current").value, new: $("#pw-new").value } });
    $("#pw-current").value = $("#pw-new").value = ""; $("#pw-error").textContent = "";
    toast("Parol oʻzgartirildi");
  } catch (err) { $("#pw-error").textContent = err.message; }
});

// ---------- start ----------
(async () => {
  try { me = await api("/api/seller/me"); enterPanel(); }
  catch (e) { if (e.status === 401) showAuth(); else { showAuth(); toast(e.message, "error"); } }
})();
