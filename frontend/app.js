const $ = id => document.getElementById(id);
const fmt = n => new Intl.NumberFormat("uz-UZ").format(n) + " so‘m";
const icons = ["🧥", "👗", "👔", "🧥"];
let catalog = [];
function display(items) {
  const q = ($("search")?.value || "").trim().toLowerCase();
  const size = $("size-filter")?.value || "";
  return items.filter(p => (!q || (p.name + " " + p.category + " " + p.color).toLowerCase().includes(q)) && (!size || (p.stock_by_size?.[size] || 0) > 0));
}
function render(items) {
  try {
    $("products").replaceChildren(...items.map((p, i) => {
      const article = document.createElement("article");
      article.className = "product";
      const art = document.createElement("div");
      art.className = "product-art";
      art.textContent = icons[i] || "👕";
      const info = document.createElement("div");
      info.className = "product-info";
      const title = document.createElement("h3");
      title.textContent = p.name;
      const details = document.createElement("p");
      details.textContent = p.category + " · " + p.color;
      const price = document.createElement("strong");
      price.textContent = fmt(p.price);
      const stock = document.createElement("p");
      stock.textContent = "Namuna do‘kon: " + p.shop_id + " · Mavjud o‘lchamlar: " + Object.entries(p.stock_by_size || {}).filter(([,n]) => n > 0).map(([s]) => s).join(", ");
      info.append(title, details, price, stock);
      article.append(art, info);
      return article;
    }));
}
async function init() {
  try {
    const response = await fetch("/api/products");
    if (!response.ok) throw new Error("API error");
    const {items} = await response.json();
    catalog = items;
    render(display(catalog));
    $("product").replaceChildren(...items.map(p => {
      const option = document.createElement("option");
      option.value = p.id;
      option.textContent = p.name + " — " + fmt(p.price);
      return option;
    }));
  } catch(e) { $("result").textContent = "API bilan aloqa o‘rnatilmadi."; }
}
["search", "size-filter"].forEach(id => $(id)?.addEventListener(id === "search" ? "input" : "change", () => render(display(catalog))));
$("photo").addEventListener("change", () => {
  const file = $("photo").files[0];
  if (!file) return;
  if (!["image/jpeg","image/png","image/webp"].includes(file.type) || file.size > 8*1024*1024) {
    $("result").textContent = "JPG, PNG yoki WebP, maksimum 8 MB tanlang.";
    return;
  }
  const url = URL.createObjectURL(file);
  $("preview").src = url;
  $("preview").hidden = false;
  $("preview").onload = () => URL.revokeObjectURL(url);
  $("result").textContent = "Surat tanlandi. AI modeli hali ulanmagan.";
});
$("generate").addEventListener("click", async () => {
  const photo = $("photo").files[0];
  if (!photo) { $("result").textContent = "Avval suratingizni tanlang."; return; }
  const body = new FormData();
  body.append("photo", photo);
  body.append("product_id", $("product").value);
  $("generate").disabled = true;
  try {
    const response = await fetch("/api/try-on", {method:"POST",body});
    const result = await response.json();
    $("result").textContent = result.error || "Javob olindi.";
  } catch(e) { $("result").textContent = "Server bilan aloqa uzildi."; }
  finally { $("generate").disabled = false; }
});
init();
