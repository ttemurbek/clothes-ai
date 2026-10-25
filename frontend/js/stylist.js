// AI stylist: profile form -> analysis + outfit assembled from in-stock products.
import { $, $$, api, el, fmtKm, fmtPrice, productArt, shareLink, store, swatch, toast } from "./common.js";
import { openFitting } from "./fitting3d.js";

const SKIN = { oq: "#f2dcc9", bugdoy: "#d4a373", qoracha: "#a26b45", qora: "#5b3a26" };
const form = $("#stylist-form");
const result = $("#stylist-result");
let options = null, last = null, point = null;
const choice = {}; // gender, skin_tone, season, occasion

function radioChips(container, items, key, render = x => x.label) {
  container.replaceChildren(...items.map(item => el("button.chip", {
    type: "button", role: "radio", dataset: { value: item.key }, "aria-pressed": String(choice[key] === item.key),
    onclick: () => select(container, key, item.key),
  }, render(item))));
}
function select(container, key, value) {
  choice[key] = value;
  $$("[data-value]", container).forEach(b => b.setAttribute("aria-pressed", String(b.dataset.value === value)));
}

async function init() {
  try { options = await api("/api/stylist/options"); } catch { return; }
  const saved = store.get("stylist-profile", {});
  Object.assign(choice, { gender: saved.gender, skin_tone: saved.skin_tone,
    season: saved.season || options.current_season, occasion: saved.occasion });
  $$("#st-gender [data-value]").forEach(b => b.addEventListener("click", () => select($("#st-gender"), "gender", b.dataset.value)));
  select($("#st-gender"), "gender", choice.gender);
  $("#st-skin").replaceChildren(...options.skin_tones.map(t => {
    const dot = el("span.skin-dot", { "aria-hidden": "true" });
    dot.style.background = SKIN[t.key];
    return el("button.skin", { type: "button", role: "radio", dataset: { value: t.key }, "aria-pressed": "false",
      onclick: () => select($("#st-skin"), "skin_tone", t.key) }, dot, el("span", t.label));
  }));
  select($("#st-skin"), "skin_tone", choice.skin_tone);
  radioChips($("#st-season"), options.seasons, "season",
    s => [s.label, s.key === options.current_season ? el("span.count", " · hozir") : null]);
  radioChips($("#st-occasion"), options.occasions, "occasion");
  for (const [id, key] of [["st-height", "height_cm"], ["st-weight", "weight_kg"], ["st-budget", "budget"],
    ["st-size", "usual_size"], ["st-shoe", "shoe_size"], ["st-note", "note"]]) {
    if (saved[key]) $("#" + id).value = saved[key];
  }
  $("#st-submit").textContent = options.ai ? "✨ AI tahlil qilsin" : "✨ Tahlil qilish";
  if (options.ai) $(".stylist-intro .hint").textContent = "Maʼlumotlaringiz serverda saqlanmaydi. Tahlil uchun boʻy, vazn, rang va istaklaringiz AI xizmatiga (Anthropic Claude) yuboriladi.";
}

function profile() {
  return {
    ...choice, height_cm: $("#st-height").value, weight_kg: $("#st-weight").value, budget: $("#st-budget").value,
    usual_size: $("#st-size").value, shoe_size: $("#st-shoe").value, note: $("#st-note").value.trim(),
  };
}

function locate() {
  return new Promise(resolve => {
    if (point || !navigator.geolocation) return resolve(point);
    navigator.geolocation.getCurrentPosition(p => { point = [p.coords.latitude, p.coords.longitude]; resolve(point); },
      () => resolve(null), { timeout: 8000, maximumAge: 600000 });
  });
}

form.addEventListener("submit", async e => {
  e.preventDefault();
  const body = profile();
  const err = $("#st-error");
  err.textContent = "";
  if (!body.gender) return void (err.textContent = "Jinsni tanlang.");
  if (!body.height_cm || !body.weight_kg) return void (err.textContent = "Boʻy va vaznni yozing.");
  if (!body.skin_tone) return void (err.textContent = "Tana rangini tanlang.");
  if (!body.occasion) return void (err.textContent = "Qayerga kiyishingizni tanlang.");
  store.set("stylist-profile", body);
  if ($("#st-near").checked) {
    const p = await locate();
    if (p) { body.lat = p[0]; body.lng = p[1]; }
  }
  const button = $("#st-submit");
  button.disabled = true; button.classList.add("loading");
  result.hidden = false;
  result.replaceChildren(el("div.box.center",
    el("p.label", options?.ai ? "AI qomatingiz, rangingiz va faslni tahlil qilyapti…" : "Tahlil qilinmoqda…"),
    el("div.progress.mt", el("i"))));
  result.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    last = await api("/api/stylist", { method: "POST", json: body });
    render(last);
  } catch (ex) {
    result.replaceChildren(el("div.notice.bad", ex.message));
    err.textContent = ex.message;
  } finally {
    button.disabled = false; button.classList.remove("loading");
  }
});

function tile(label, value, sub) {
  return el("div.metric", el("span", label), el("strong", value), sub ? el("small", sub) : null);
}

function render(data) {
  const a = data.analysis;
  const swatches = (colors, cls = "") => el("div.palette", colors.map(c => el(`span.palette-item${cls}`, swatch(c), c)));
  const outfit = el("div.outfit");
  data.outfit.forEach((item, i) => outfit.append(outfitCard(item, i)));
  result.replaceChildren(...[
    el("div.box.stylist-summary",
      el("div.row-gap", el(`span.pill.${data.engine === "ai" ? "accent" : ""}`, data.engine === "ai" ? "✨ Claude AI tahlili" : "📐 Qoidalar asosidagi tahlil"),
        el("span.muted.small", `${data.profile.height_cm} sm · ${data.profile.weight_kg} kg · ${a.season.label} · ${a.occasion.label}`)),
      el("p.lead.mt", data.summary)),
    el("div.metrics.mt.st-metrics",
      tile("Oʻlchamingiz", `${a.size.letter} / ${a.size.numeric}`, a.size.estimated ? "boʻy va vazndan taxmin" : "siz koʻrsatgan"),
      tile("Qomat", a.build_label, `BMI ${a.bmi} · boʻy ${a.height_label}`),
      tile("Fasl", a.season.label, a.season.key === "qish" ? "issiq qatlamlar" : ""),
      tile("Qayerga", a.occasion.label, ""),
      tile("Toʻplam narxi", fmtPrice(data.total_price), data.over_budget ? "byudjetdan oshdi" : `${data.outfit.length} ta kiyim`)),
    data.over_budget ? el("div.notice.small.mt", `Bu fasl va joy uchun zarur kiyimlar byudjetingizdan qimmatroq chiqdi (${fmtPrice(data.total_price)}). `,
      "Eng arzon mos variantlar tanlandi — “↻ Boshqasi” bilan solishtiring.") : null,
    el("div.box.mt",
      el("h3", "🎨 Sizga yarashadigan ranglar"),
      el("p.muted.small.my", a.color_note),
      el("div.label", "Eng mos"), swatches(a.palette.best),
      el("div.label.mt", "Ehtiyot boʻling"), swatches(a.palette.avoid, ".avoid")),
    el("div.section-head.mt", el("div", el("p.eyebrow", "Sizning toʻplamingiz"), el("h2", "AI tanlagan kiyimlar")),
      data.outfit.length ? el("button.btn.primary", { onclick: () => openFitting(last.outfit, last.profile) }, "🧍 3D'da kiyib koʻrish") : null),
    outfit,
    data.missing.length ? el("div.notice.small.mt", "Katalogda hozircha mos topilmadi: ",
      data.missing.map(m => m.slot_label).join(", "), ". Doʻkonlar qoʻshilgan sari tavsiya toʻliqlashadi.") : null,
    el("div.row-gap.mt",
      data.outfit.length ? el("button.btn.primary", { onclick: () => openFitting(last.outfit, last.profile) }, "🧍 3D'da kiyib koʻrish") : null,
      data.outfit.length ? el("button.btn.accent", { onclick: shareOutfit }, "👨‍👩‍👧 Oilamga yuborib soʻray") : null,
      el("button.btn", { onclick: () => form.scrollIntoView({ behavior: "smooth" }) }, "Maʼlumotlarni oʻzgartirish")),
    el("div.box.mt", el("h3", "💡 Maslahatlar"), el("ul.tips", a.tips.map(t => el("li", t)))),
  ].filter(Boolean));
}

function outfitCard(item, index) {
  const p = item.product;
  const reasons = item.why ? [item.why] : item.reasons;
  const card = el("article.card.outfit-card",
    el("div.slot-label", item.slot_label),
    (() => { const art = productArt(p); art.addEventListener("click", () => openProduct(p.id, p.recommended_size)); return art; })(),
    el("div.card-body",
      el("h3", p.name),
      el("div.card-meta", swatch(p.color), p.color, " · ", p.shop?.name || "", p.distance_km != null ? ` · ${fmtKm(p.distance_km)}` : ""),
      el("div.price", fmtPrice(p.price), p.recommended_size ? el("span.pill.accent.size-pill", `Sizga: ${p.recommended_size}`) : null),
      el("ul.reasons", reasons.map(r => el("li", r))),
      el("div.row-gap.mt",
        el("button.btn.sm.primary", { onclick: () => openProduct(p.id, p.recommended_size) }, "Koʻrish va bron"),
        item.alternatives.length ? el("button.btn.sm", { onclick: () => swap(index) }, "↻ Boshqasi") : null)));
  return card;
}

function swap(index) {
  const item = last.outfit[index];
  const next = item.alternatives.shift();
  item.alternatives.push(item.product);
  item.product = next;
  item.why = null;
  item.reasons = ["Muqobil variant: shu toifadagi keyingi eng mos kiyim"];
  last.total_price = last.outfit.reduce((n, x) => n + x.product.price, 0);
  render(last);
  $$(".outfit-card")[index]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function openProduct(id, size) {
  window.dispatchEvent(new CustomEvent("cai:open-product", { detail: { id, size } }));
}

async function shareOutfit() {
  const ids = last.outfit.map(x => x.product.id).slice(0, 4);
  try {
    const { url } = await api("/api/shares", { method: "POST", json: { product_ids: ids, question: "AI shu toʻplamni tavsiya qildi — qaysi biri yoqdi?" } });
    shareLink(url, "AI stilist menga shu toʻplamni tanladi. Fikringiz? 👇");
  } catch (ex) { toast(ex.message, "error"); }
}

init();
