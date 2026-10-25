// Share page: friends and family vote for the outfit that suits best.
import { $, api, el, fmtPrice, productArt, toast } from "./common.js";

const token = location.pathname.split("/").pop();

function render(data) {
  $("#question").textContent = data.question;
  $("#summary").textContent = data.total_votes
    ? `${data.total_votes} kishi ovoz berdi` + (data.my_vote ? " · siz ham ovoz berdingiz" : "")
    : data.items.length > 1 ? "Eng yarashganiga ovoz bering." : "Yarashsa — ovoz bering.";
  const total = Math.max(1, data.total_votes);
  $("#items").replaceChildren(...data.items.map(p => {
    const bar = el("i"); bar.style.width = `${(p.votes / total) * 100}%`;
    return el(`div.card.vote-card${data.my_vote === p.id ? ".mine" : ""}`,
      productArt(p),
      el("div.card-body",
        el("h3", p.name), el("div.card-meta", p.shop?.name || ""), el("div.price", fmtPrice(p.price)),
        el("div.vote-bar", bar), el("div.small.muted", `${p.votes} ovoz`),
        el("div.row-gap.mt",
          el("button.btn.primary.sm.grow", { onclick: () => vote(p.id), "aria-pressed": String(data.my_vote === p.id) },
            data.my_vote === p.id ? "✓ Ovozingiz" : data.items.length > 1 ? "Shunisi yarashadi" : "👍 Yarashadi"),
          el("a.btn.sm", { href: `/p/${p.id}` }, "Koʻrish"))));
  }));
}
async function vote(id) {
  try { render(await api(`/api/shares/${token}/vote`, { method: "POST", json: { product_id: id } })); toast("Rahmat! Ovozingiz qabul qilindi"); }
  catch (e) { toast(e.message, "error"); }
}
api(`/api/shares/${token}`).then(render).catch(e => {
  $("#question").textContent = "Havola topilmadi";
  $("#summary").textContent = e.message;
});
