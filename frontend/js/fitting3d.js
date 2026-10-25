// 3D fitting room: a mannequin built from the person's height, weight, gender and skin tone, dressed in
// the chosen products (shape from category/name, colour and pattern from the product), rotatable 360°.
// It shows fit, silhouette, colours and layering — not the exact fabric of the real garment.
import { $, $$, closeDialog, el, fmtPrice, openDialog, store, toast } from "./common.js";

let THREE = null;
const SKIN = { oq: 0xf0d5c0, bugdoy: 0xd2a070, qoracha: 0x9c6640, qora: 0x5a3724 };
const COLOR = {
  "Oq": 0xf3f0e8, "Qora": 0x232126, "Bej": 0xd8c3a3, "Kulrang": 0x8f9096, "Koʻk": 0x2c4a86, "Moviy": 0x86b4dd,
  "Yashil": 0x5b6b3a, "Qizil": 0x8e2433, "Pushti": 0xe7a6bb, "Binafsha": 0x6f4a9c, "Oltin rang": 0xc9a24b,
  "Kumush rang": 0xc3c6cc, "Jigarrang": 0x7a5236, "Rang-barang": 0xffffff,
};
const CATEGORY_SLOT = {
  "Ustki kiyim": "outer", "Sviter va kofta": "layer", "Koʻylak": "top", "Shim va yubka": "bottom",
  "Poyabzal": "shoes", "Aksessuar": "accessory", "Kelinlik libosi": "full", "Kechki libos": "full",
  "Kostyum": "full", "Milliy libos": "full", "Bolalar kiyimi": "full",
};
const SLOT_LABEL = { outer: "Ustki kiyim", layer: "Issiq qatlam", top: "Koʻylak", bottom: "Shim / yubka",
  full: "Asosiy libos", shoes: "Poyabzal", accessory: "Aksessuar" };
const ORDER = ["bottom", "top", "full", "layer", "outer", "shoes", "accessory"];

// ---------------- body model ----------------
// All heights are fractions of the person's height H (feet at y = 0); radii are fractions of H too.
function bodyModel(p) {
  const H = Math.min(2.2, Math.max(1.2, (Number(p.height_cm) || 172) / 100));
  const kg = Math.min(200, Math.max(30, Number(p.weight_kg) || 65));
  const bmi = kg / (H * H);
  const w = Math.min(1.45, Math.max(0.82, Math.pow(bmi / 22, 0.62)));   // girth factor
  const female = p.gender === "ayol";
  const torso = female
    ? [[0.040, 0.47], [0.098, 0.50], [0.108, 0.53], [0.094, 0.58], [0.074, 0.62], [0.080, 0.67], [0.094, 0.71],
       [0.090, 0.75], [0.088, 0.79], [0.068, 0.825], [0.030, 0.845]]
    : [[0.040, 0.47], [0.090, 0.50], [0.096, 0.53], [0.090, 0.58], [0.086, 0.62], [0.092, 0.67], [0.100, 0.72],
       [0.104, 0.76], [0.102, 0.795], [0.074, 0.83], [0.030, 0.85]];
  return {
    H, w, female, bmi,
    torso: torso.map(([r, y]) => [r * (r > 0.05 ? w : 1), y]),
    depth: female ? 0.72 : 0.68,
    shoulderX: (female ? 0.098 : 0.112) * Math.min(w, 1.2),
    shoulderY: 0.805,
    hipX: 0.046 * Math.min(w, 1.25),
    leg: [[0.054 * w, 0.49], [0.050 * w, 0.42], [0.038 * w, 0.30], [0.033, 0.27], [0.030 * Math.min(w, 1.15), 0.20],
          [0.020, 0.07], [0.018, 0.045]],
    arm: [[0.030 * w, 0], [0.026 * w, 0.10], [0.021 * Math.min(w, 1.2), 0.19], [0.020, 0.21], [0.017, 0.34], [0.014, 0.36]],
    armAngle: 0.20,
    neck: [0.028, 0.84, 0.885],
    head: [0.060, 0.935],
  };
}

const radiusAt = (profile, y) => {
  for (let i = 0; i < profile.length - 1; i++) {
    const [r0, y0] = profile[i], [r1, y1] = profile[i + 1];
    if ((y - y0) * (y - y1) <= 0) return r0 + (r1 - r0) * ((y - y0) / ((y1 - y0) || 1));
  }
  const first = profile[0], last = profile.at(-1);
  return Math.abs(y - first[1]) < Math.abs(y - last[1]) ? first[0] : last[0];
};

/** Lathe from a [radius, y] profile clipped to [from, to], radii grown by `add` (all in H units). */
function lathe(profile, from, to, add, H, opts = {}) {
  const ys = [from, ...profile.map(p => p[1]).filter(y => y > Math.min(from, to) && y < Math.max(from, to)), to]
    .sort((a, b) => a - b);
  const pts = ys.map(y => new THREE.Vector2(Math.max(0.004, radiusAt(profile, y) + add + (opts.flare ? opts.flare(y) : 0)) * H, y * H));
  if (opts.closeBottom) pts.unshift(new THREE.Vector2(0.001, ys[0] * H));
  if (opts.closeTop) pts.push(new THREE.Vector2(0.001, ys.at(-1) * H));
  return new THREE.LatheGeometry(pts, 48);
}

// ---------------- materials ----------------
function patternTexture(kind, base) {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d");
  const hex = "#" + base.toString(16).padStart(6, "0");
  g.fillStyle = hex; g.fillRect(0, 0, 256, 256);
  if (kind === "plaid") {
    g.globalAlpha = 0.45; g.fillStyle = "#1d1a1a";
    for (let i = 0; i < 256; i += 64) { g.fillRect(i, 0, 22, 256); g.fillRect(0, i, 256, 22); }
    g.globalAlpha = 0.5; g.fillStyle = "#f1e7d6";
    for (let i = 40; i < 256; i += 64) { g.fillRect(i, 0, 3, 256); g.fillRect(0, i, 256, 3); }
  } else if (kind === "ikat") {
    const colors = ["#c8203c", "#f2b134", "#1f6fb2", "#2a9d6f", "#7b2c86", "#f4efe6"];
    for (let x = 0; x < 256; x += 32) {
      for (let y = 0; y < 256; y += 8) {
        g.fillStyle = colors[(x / 32 + Math.floor(Math.sin(y / 20 + x) * 2 + 2)) % colors.length];
        g.fillRect(x + Math.sin(y / 9) * 5, y, 30, 8);
      }
    }
  } else if (kind === "knit") {
    g.globalAlpha = 0.18; g.strokeStyle = "#000";
    for (let x = 0; x < 256; x += 12) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, 256); g.lineWidth = 4; g.stroke(); }
  } else if (kind === "denim") {
    g.globalAlpha = 0.12; g.strokeStyle = "#fff";
    for (let i = -256; i < 256; i += 5) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i + 256, 256); g.stroke(); }
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(kind === "plaid" ? 4 : kind === "ikat" ? 3 : 6, kind === "plaid" ? 3 : 4);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function garmentMaterial(product) {
  const text = (product.name + " " + (product.description || "")).toLowerCase();
  const base = COLOR[product.color] ?? 0x9a8fa6;
  const m = { color: base, roughness: 0.85, metalness: 0, side: THREE.DoubleSide };
  let pattern = null;
  if (product.color === "Rang-barang" || /atlas|adras/.test(text) && product.color === "Rang-barang") pattern = "ikat";
  else if (/katak|flanel/.test(text)) pattern = "plaid";
  else if (/jinsi|denim/.test(text)) pattern = "denim";
  else if (/trikotaj|sviter|jun|toʻqilgan|kofta/.test(text)) pattern = "knit";
  if (pattern) { m.map = patternTexture(pattern, base); m.color = 0xffffff; }
  if (/charm|teri/.test(text)) { m.roughness = 0.38; }
  if (/puxovik|bomber/.test(text)) { m.roughness = 0.45; }
  if (/atlas|ipak|shifon|paetka|baxmal/.test(text)) { m.roughness = 0.35; m.metalness = 0.08; }
  if (/zarbof|paetka|oltin/.test(text) || product.color === "Oltin rang") { m.metalness = 0.55; m.roughness = 0.35; }
  return new THREE.MeshStandardMaterial(m);
}

// ---------------- garment shapes ----------------
function kindOf(product, slot) {
  const t = (product.name + " " + (product.description || "")).toLowerCase();
  if (slot === "outer") {
    if (/puxovik/.test(t)) return /uzun|tizza/.test(t) ? "puffer-long" : "puffer";
    if (/palto|trench/.test(t)) return "coat";
    if (/blazer|jaket/.test(t)) return "blazer";
    return "jacket";
  }
  if (slot === "layer") return /zamok|flis/.test(t) ? "fleece" : /boʻgʻiz/.test(t) ? "turtleneck" : "sweater";
  if (slot === "top") return /bluzka/.test(t) ? "blouse" : "shirt";
  if (slot === "bottom") return /yubka/.test(t) ? "skirt" : /keng|palazzo/.test(t) ? "wide-pants" : "pants";
  if (slot === "shoes") return /etik/.test(t) ? "tall-boots" : /botinka/.test(t) ? "boots" : "sneakers";
  if (slot === "accessory") return /ryukzak/.test(t) ? "backpack" : "scarf";
  if (product.category === "Kostyum") return "suit";
  if (/chopon/.test(t)) return "robe";
  if (/kamzul/.test(t)) return "vest";
  if (/kokteyl|tizza/.test(t)) return "dress-knee";
  if (product.category === "Kelinlik libosi") return "gown";
  return /uzun|yerga|kechki|kelinlik/.test(t) || product.category === "Kechki libos" ? "gown" : "dress";
}

function mesh(geo, mat, body, scaleDepth = true) {
  const m = new THREE.Mesh(geo, mat);
  if (scaleDepth) m.scale.z = body.depth;
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

function legs(group, body, add, from, to, mat, flare) {
  for (const side of [-1, 1]) {
    const leg = mesh(lathe(body.leg, from, to, add, body.H, { flare }), mat, body, false);
    leg.position.x = side * body.hipX * body.H;
    group.add(leg);
  }
}

function arms(group, body, add, from, to, mat) {
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.set(side * body.shoulderX * body.H, body.shoulderY * body.H, 0);
    pivot.rotation.z = side * body.armAngle;
    // the arm profile runs downward from the shoulder: mirror y
    const prof = body.arm.map(([r, t]) => [r, -t]);
    const geo = lathe(prof, -to, -from, add, body.H, { closeBottom: add === 0 });
    const m = mesh(geo, mat, body, false);
    pivot.add(m);
    group.add(pivot);
  }
}

function ring(body, y, add, mat, tube = 0.006) {
  const r = (radiusAt(body.torso, y) + add) * body.H;
  const t = new THREE.Mesh(new THREE.TorusGeometry(r, tube * body.H, 8, 48), mat);
  t.rotation.x = Math.PI / 2; t.position.y = y * body.H; t.scale.y = body.depth;
  t.castShadow = true;
  return t;
}

function torsoPiece(group, body, from, to, add, mat, flare) {
  group.add(mesh(lathe(body.torso, from, to, add, body.H, { flare }), mat, body));
}

function shade(mat, k) {
  const m = mat.clone();
  if (!m.map) m.color.multiplyScalar(k);
  return m;
}

function buildGarment(product, slot, body) {
  const g = new THREE.Group();
  const mat = garmentMaterial(product);
  const kind = kindOf(product, slot);
  const hemFlare = (top, k) => y => (y < top ? (top - y) * k : 0);
  switch (kind) {
    case "shirt": case "blouse":
      torsoPiece(g, body, 0.50, 0.838, 0.006, mat);
      arms(g, body, 0.004, 0, 0.345, mat);
      g.add(ring(body, 0.835, 0.012, shade(mat, 0.95), 0.008));
      break;
    case "sweater": case "turtleneck": case "fleece":
      torsoPiece(g, body, 0.495, 0.84, 0.014, mat);
      arms(g, body, 0.010, 0, 0.34, mat);
      g.add(ring(body, 0.50, 0.016, shade(mat, 0.85), 0.008));
      if (kind === "turtleneck") {
        const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.036 * body.H, 0.040 * body.H, 0.05 * body.H, 32, 1, true), mat);
        neck.position.y = 0.862 * body.H; neck.scale.z = 0.9; g.add(neck);
      }
      if (kind === "fleece") {
        const zip = new THREE.Mesh(new THREE.BoxGeometry(0.006 * body.H, 0.33 * body.H, 0.004 * body.H),
          new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.4 }));
        zip.position.set(0, 0.67 * body.H, (radiusAt(body.torso, 0.67) + 0.015) * body.H * body.depth); g.add(zip);
      }
      break;
    case "jacket": case "blazer": case "puffer": case "puffer-long": case "coat": {
      const puffy = kind.startsWith("puffer");
      const add = puffy ? 0.032 : kind === "blazer" ? 0.020 : 0.026;
      const hem = kind === "puffer-long" ? 0.22 : kind === "coat" ? 0.30 : kind === "blazer" ? 0.47 : 0.49;
      const sleeve = 0.35;
      torsoPiece(g, body, Math.max(hem, 0.47), 0.845, add, mat);
      if (hem < 0.47) {
        // skirt part of a long coat: a flared tube around both legs
        const base = [[radiusAt(body.torso, 0.50) + add, 0.50], [radiusAt(body.torso, 0.50) + add + 0.02, 0.35], [radiusAt(body.torso, 0.50) + add + 0.04, 0.20]];
        const prof = [];
        for (let y = 0.50; y > hem - 0.001; y -= 0.025) {
          const r = radiusAt(base, y);
          prof.push([body.skirt ? Math.max(r, body.skirt(y) + 0.014) : r, y]);  // a coat worn over a dress flares over it
        }
        prof.push([prof.at(-1)[0], hem]);
        g.add(mesh(lathe(prof, hem, 0.50, 0, body.H), mat, body));
      }
      arms(g, body, puffy ? 0.016 : 0.011, 0, sleeve, mat);
      if (puffy) {
        const dark = shade(mat, 0.82);
        for (let y = Math.max(hem, 0.48) + 0.045; y < 0.80; y += 0.055) g.add(ring(body, y, add - 0.002, dark, 0.006));
        if (hem < 0.47) for (let y = hem + 0.05; y < 0.47; y += 0.06) {
          const r = (radiusAt(body.torso, 0.50) + add + 0.03) * body.H;
          const t = new THREE.Mesh(new THREE.TorusGeometry(r, 0.006 * body.H, 8, 48), dark);
          t.rotation.x = Math.PI / 2; t.position.y = y * body.H; t.scale.y = body.depth; g.add(t);
        }
      }
      if (/kapyushon|puxovik/.test((product.description || "") + product.name.toLowerCase()) && puffy) {
        // a folded hood resting behind the neck
        const hood = new THREE.Mesh(new THREE.TorusGeometry(0.05 * body.H, 0.024 * body.H, 12, 24, Math.PI), mat);
        hood.rotation.x = Math.PI / 2; hood.rotation.z = Math.PI;
        hood.position.set(0, 0.85 * body.H, -0.008 * body.H); hood.scale.set(1, 0.85, 1);
        g.add(hood);
      }
      if (/belbogʻ|trench/.test((product.description || "").toLowerCase() + product.name.toLowerCase())) g.add(ring(body, 0.60, add + 0.004, shade(mat, 0.8), 0.009));
      // collar
      g.add(ring(body, 0.84, add + 0.01, shade(mat, 0.9), 0.012));
      break;
    }
    case "vest":
      torsoPiece(g, body, 0.52, 0.83, 0.018, mat);
      break;
    case "pants": case "wide-pants":
      torsoPiece(g, body, 0.47, 0.60, 0.008, mat);
      legs(g, body, kind === "wide-pants" ? 0.012 : 0.006, 0.04, 0.495, mat, kind === "wide-pants" ? (y => (0.45 - y) * 0.06) : null);
      break;
    case "skirt":
      torsoPiece(g, body, 0.50, 0.62, 0.008, mat);
      g.add(mesh(lathe([[radiusAt(body.torso, 0.52) + 0.008, 0.52], [radiusAt(body.torso, 0.52) + 0.03, 0.30]], 0.28, 0.52, 0, body.H), mat, body));
      break;
    case "dress": case "dress-knee": case "gown": case "robe": {
      const hem = kind === "gown" ? 0.0 : kind === "dress-knee" ? 0.30 : kind === "robe" ? 0.16 : 0.18;
      torsoPiece(g, body, 0.52, 0.83, 0.006, mat);
      const top = radiusAt(body.torso, 0.53) + 0.008;
      const spread = kind === "gown" ? 0.20 : 0.07;
      const skirt = [[top, 0.53], [top + spread * 0.35, 0.36], [top + spread, hem]];
      g.add(mesh(lathe(skirt, hem, 0.53, 0, body.H), mat, body));
      body.skirt = y => (y >= hem && y <= 0.53 ? radiusAt(skirt, y) : 0);
      if (kind === "robe") { arms(g, body, 0.022, 0, 0.36, mat); g.add(ring(body, 0.82, 0.03, shade(mat, 0.8), 0.012)); }
      else if (/yeng/.test((product.description || "").toLowerCase())) arms(g, body, 0.004, 0, 0.34, mat);
      break;
    }
    case "suit": {
      const shirt = garmentMaterial({ name: "", color: "Oq" });
      torsoPiece(g, body, 0.50, 0.838, 0.006, shirt);
      torsoPiece(g, body, 0.47, 0.60, 0.010, mat);
      legs(g, body, 0.007, 0.04, 0.495, mat);
      torsoPiece(g, body, 0.47, 0.835, 0.020, mat);
      arms(g, body, 0.015, 0, 0.345, mat);
      const tie = new THREE.Mesh(new THREE.BoxGeometry(0.018 * body.H, 0.12 * body.H, 0.004 * body.H),
        new THREE.MeshStandardMaterial({ color: 0x5c1a24, roughness: 0.5 }));
      tie.position.set(0, 0.76 * body.H, (radiusAt(body.torso, 0.76) + 0.022) * body.H * body.depth); g.add(tie);
      break;
    }
    case "sneakers": case "boots": case "tall-boots": {
      const shaft = kind === "tall-boots" ? 0.15 : kind === "boots" ? 0.08 : 0.035;
      const sole = new THREE.MeshStandardMaterial({ color: kind === "sneakers" ? 0xf2f2f2 : 0x2a2420, roughness: 0.7 });
      for (const side of [-1, 1]) {
        const x = side * body.hipX * body.H;
        const foot = new THREE.Mesh(new THREE.CapsuleGeometry(0.028 * body.H, 0.07 * body.H, 6, 16), mat);
        foot.rotation.x = Math.PI / 2; foot.position.set(x, 0.022 * body.H, 0.03 * body.H); foot.scale.set(1.05, 1, 0.75);
        foot.castShadow = true; g.add(foot);
        const s = new THREE.Mesh(new THREE.BoxGeometry(0.062 * body.H, 0.012 * body.H, 0.15 * body.H), sole);
        s.position.set(x, 0.006 * body.H, 0.03 * body.H); g.add(s);
        const leg = mesh(lathe(body.leg, 0.02, 0.02 + shaft, 0.008, body.H), mat, body, false);
        leg.position.x = x; g.add(leg);
      }
      break;
    }
    case "scarf": {
      const wrap = new THREE.Mesh(new THREE.TorusGeometry(0.042 * body.H, 0.017 * body.H, 12, 32), mat);
      wrap.rotation.x = Math.PI / 2; wrap.position.y = 0.845 * body.H; wrap.scale.y = 0.85; g.add(wrap);
      for (const [x, len, tilt] of [[-0.018, 0.13, -0.06], [0.026, 0.10, 0.1]]) {
        const tail = new THREE.Mesh(new THREE.BoxGeometry(0.042 * body.H, len * body.H, 0.014 * body.H), mat);
        tail.position.set(x * body.H, (0.83 - len / 2) * body.H, (radiusAt(body.torso, 0.78) * body.depth + 0.042) * body.H);
        tail.rotation.z = tilt; tail.rotation.x = -0.12; g.add(tail);
      }
      break;
    }
    case "backpack": {
      const bag = new THREE.Mesh(new THREE.BoxGeometry(0.17 * body.H, 0.22 * body.H, 0.07 * body.H), mat);
      bag.position.set(0, 0.68 * body.H, -(radiusAt(body.torso, 0.70) * body.depth + 0.06) * body.H); g.add(bag);
      for (const side of [-1, 1]) {
        const strap = new THREE.Mesh(new THREE.TorusGeometry(0.06 * body.H, 0.006 * body.H, 6, 24, Math.PI), mat);
        strap.rotation.y = Math.PI / 2; strap.position.set(side * 0.05 * body.H, 0.76 * body.H, -0.01 * body.H); g.add(strap);
      }
      break;
    }
  }
  g.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}

function buildMannequin(body, skinTone) {
  const g = new THREE.Group();
  const skin = new THREE.MeshStandardMaterial({ color: SKIN[skinTone] ?? SKIN.bugdoy, roughness: 0.62 });
  g.add(mesh(lathe(body.torso, 0.46, 0.85, 0, body.H, { closeBottom: true }), skin, body));
  legs(g, body, 0, 0.03, 0.50, skin);
  arms(g, body, 0, 0, 0.36, skin);
  for (const side of [-1, 1]) {
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.02 * body.H, 16, 12), skin);
    const a = body.armAngle, L = 0.375 * body.H;
    hand.position.set(side * (body.shoulderX * body.H + Math.sin(a) * L), body.shoulderY * body.H - Math.cos(a) * L, 0);
    hand.scale.set(0.8, 1.25, 0.6); g.add(hand);
    const foot = new THREE.Mesh(new THREE.CapsuleGeometry(0.022 * body.H, 0.06 * body.H, 6, 12), skin);
    foot.rotation.x = Math.PI / 2; foot.position.set(side * body.hipX * body.H, 0.018 * body.H, 0.03 * body.H);
    foot.scale.set(1, 1, 0.7); g.add(foot);
  }
  const [nr, n0, n1] = body.neck;
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(nr * body.H, nr * 1.15 * body.H, (n1 - n0) * body.H, 24), skin);
  neck.position.y = ((n0 + n1) / 2) * body.H; g.add(neck);
  const head = new THREE.Mesh(new THREE.SphereGeometry(body.head[0] * body.H, 32, 24), skin);
  head.position.y = body.head[1] * body.H; head.scale.set(0.86, 1.08, 0.94); g.add(head);
  const hairMat = new THREE.MeshStandardMaterial({ color: 0x1f1714, roughness: 0.8 });
  const hair = new THREE.Mesh(new THREE.SphereGeometry(body.head[0] * body.H * 1.03, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2.1), hairMat);
  hair.position.y = body.head[1] * body.H + 0.004 * body.H; hair.scale.set(0.88, 1.1, 0.98); hair.rotation.x = -0.25;
  g.add(hair);
  if (body.female) {
    const bun = new THREE.Mesh(new THREE.SphereGeometry(0.03 * body.H, 16, 12), hairMat);
    bun.position.set(0, (body.head[1] + 0.03) * body.H, -0.05 * body.H); g.add(bun);
  }
  g.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}

// ---------------- scene & controls ----------------
class Stage {
  constructor(host) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    host.append(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a7a70, 1.15));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(2.2, 3.5, 2.6); key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    Object.assign(key.shadow.camera, { left: -1.5, right: 1.5, top: 2.5, bottom: -0.5 });
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xd9c8ff, 0.9); rim.position.set(-2.5, 2.2, -2.5); this.scene.add(rim);
    const floor = new THREE.Mesh(new THREE.CircleGeometry(0.75, 64), new THREE.ShadowMaterial({ opacity: 0.22 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; this.scene.add(floor);
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.66, 0.025, 64),
      new THREE.MeshStandardMaterial({ color: 0xe9e2ee, roughness: 0.9 }));
    disc.position.y = -0.013; disc.receiveShadow = true; this.scene.add(disc);
    this.turntable = new THREE.Group(); this.scene.add(this.turntable);
    this.yaw = 0.5; this.pitch = 0.08; this.distance = 4.6; this.target = 0.95; this.auto = true;
    this.lastInteraction = 0;
    this._bindControls();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(host);
    this.resize();
    this.running = true;
    const tick = t => {
      if (!this.running) return;
      const dt = Math.min(0.05, (t - (this.prev || t)) / 1000); this.prev = t;
      if (this.auto && performance.now() - this.lastInteraction > 2500) this.yaw += dt * 0.55;
      this.turntable.rotation.y = this.yaw;
      const h = this.target;
      this.camera.position.set(0, h + Math.sin(this.pitch) * this.distance, Math.cos(this.pitch) * this.distance);
      this.camera.lookAt(0, h, 0);
      this.renderer.render(this.scene, this.camera);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  resize() {
    const w = this.host.clientWidth || 300, h = this.host.clientHeight || 400;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  _bindControls() {
    const el = this.renderer.domElement;
    el.style.touchAction = "none";
    const pointers = new Map();
    let pinch = 0;
    el.addEventListener("pointerdown", e => { el.setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.clientX, e.clientY]); this.lastInteraction = performance.now(); });
    el.addEventListener("pointermove", e => {
      if (!pointers.has(e.pointerId)) return;
      const [px, py] = pointers.get(e.pointerId);
      pointers.set(e.pointerId, [e.clientX, e.clientY]);
      this.lastInteraction = performance.now();
      if (pointers.size === 1) {
        this.yaw += (e.clientX - px) * 0.011;
        this.pitch = Math.max(-0.15, Math.min(0.6, this.pitch + (e.clientY - py) * 0.004));
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (pinch) this.zoom(pinch / d);
        pinch = d;
      }
    });
    const up = e => { pointers.delete(e.pointerId); if (pointers.size < 2) pinch = 0; };
    el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
    el.addEventListener("wheel", e => { e.preventDefault(); this.zoom(Math.exp(e.deltaY * 0.0012)); this.lastInteraction = performance.now(); }, { passive: false });
  }
  zoom(k) {
    const H = this.H || 1.7;
    this.distance = Math.max(H * 0.6, Math.min(H * 3, this.distance * k));
    // the closer the camera, the higher it looks (towards the chest and face)
    const t = (this.distance - H * 0.6) / (H * 1.35);
    this.target = H * (0.78 - Math.min(1, t) * 0.25);
  }
  view(name) {
    this.yaw = { front: 0, side: Math.PI / 2, back: Math.PI }[name];
    this.lastInteraction = performance.now();
  }
  setContent(objects, H) {
    for (const child of [...this.turntable.children]) {
      this.turntable.remove(child);
      child.traverse(o => { o.geometry?.dispose(); if (o.material) { o.material.map?.dispose(); o.material.dispose(); } });
    }
    objects.forEach(o => this.turntable.add(o));
    this.target = H * 0.50; this.distance = H * 2.1; this.H = H;
  }
  dispose() {
    this.running = false;
    this.resizeObserver.disconnect();
    this.setContent([], 1.7);
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

// ---------------- dialog ----------------
let stage = null, state = null;

function webglOk() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
}

/** items: [{product, slot?}] ; profile: stylist profile (height_cm, weight_kg, gender, skin_tone) */
export async function openFitting(items, profile = null) {
  const dialog = $("#fitting-dialog");
  const saved = store.get("stylist-profile", {});
  state = {
    profile: { height_cm: 172, weight_kg: 65, gender: "erkak", skin_tone: "bugdoy", ...saved, ...(profile || {}) },
    items: items.map(x => ({ product: x.product, slot: x.slot || CATEGORY_SLOT[x.product.category] || "top", on: true })),
  };
  // one product per slot: the newest wins
  const seen = new Set();
  state.items = state.items.reverse().filter(x => !seen.has(x.slot) && seen.add(x.slot)).reverse();
  openDialog(dialog);
  const host = $("#fit-stage");
  if (!webglOk()) { host.replaceChildren(el("div.empty", "Qurilmangiz 3D (WebGL) ni qoʻllamaydi.")); return; }
  host.replaceChildren(el("div.fit-loading", "3D maneken tayyorlanmoqda…"));
  try { THREE ??= await import("/vendor/three.module.min.js"); }
  catch { host.replaceChildren(el("div.empty", "3D modul yuklanmadi. Internetni tekshiring.")); return; }
  host.replaceChildren();
  stage?.dispose();
  stage = new Stage(host);
  renderProfileForm();
  rebuild();
}

const snapshot = p => ({ id: p.id, name: p.name, category: p.category, color: p.color, price: p.price,
  description: p.description || "", recommended_size: p.recommended_size || null });

/** Add one product to the saved 3D wardrobe (same slot is replaced) and open the fitting room. */
export function tryOn3d(product) {
  const slot = CATEGORY_SLOT[product.category] || "top";
  const items = store.get("fitting-items", []).filter(x => x.slot !== slot && !(slot === "full" && ["top", "bottom"].includes(x.slot)));
  openFitting([...items, { product: snapshot(product), slot }]);
}

function rebuild() {
  store.set("fitting-items", state.items.map(x => ({ product: snapshot(x.product), slot: x.slot })));
  const body = bodyModel(state.profile);
  const objects = [buildMannequin(body, state.profile.skin_tone)];
  const active = state.items.filter(x => x.on);
  const hasFull = active.some(x => x.slot === "full");
  for (const slot of ORDER) {
    const item = active.find(x => x.slot === slot);
    if (item && !(hasFull && (slot === "top" || slot === "bottom"))) objects.push(buildGarment(item.product, slot, body));
  }
  // basic neutral layers so the mannequin is never undressed
  if (!hasFull && !active.some(x => x.slot === "bottom")) objects.push(buildGarment({ name: "asos shim", color: "Kulrang", category: "Shim va yubka" }, "bottom", body));
  if (!hasFull && !active.some(x => ["top", "layer", "outer"].includes(x.slot))) objects.push(buildGarment({ name: "asos futbolka", color: "Oq", category: "Koʻylak" }, "top", body));
  stage.setContent(objects, body.H);
  renderList(body);
}

function renderList(body) {
  const total = state.items.filter(x => x.on).reduce((n, x) => n + x.product.price, 0);
  $("#fit-items").replaceChildren(
    ...state.items.map(x => el("label.fit-item",
      el("input", { type: "checkbox", checked: x.on, onchange: e => { x.on = e.target.checked; rebuild(); } }),
      el("span.fit-item-text", el("b", x.product.name), el("small.muted", `${SLOT_LABEL[x.slot]} · ${x.product.color} · ${fmtPrice(x.product.price)}`)),
      el("button.btn.sm.ghost", { type: "button", onclick: e => { e.preventDefault(); closeDialog($("#fitting-dialog"));
        window.dispatchEvent(new CustomEvent("cai:open-product", { detail: { id: x.product.id, size: x.product.recommended_size } })); } }, "Bron →"))),
    el("p.small.muted.my", `Kiyimdagilar narxi: ${fmtPrice(total)} · maneken: ${state.profile.height_cm} sm, ${state.profile.weight_kg} kg`),
  );
}

function renderProfileForm() {
  const p = state.profile;
  const input = (key, label, attrs) => el("label.field", el("span", label),
    el("input.input", { type: "number", value: String(p[key]), ...attrs,
      onchange: e => { p[key] = Number(e.target.value) || p[key]; store.set("stylist-profile", { ...store.get("stylist-profile", {}), [key]: p[key] }); rebuild(); } }));
  const select = (key, label, options) => el("label.field", el("span", label),
    el("select.select", { onchange: e => { p[key] = e.target.value; store.set("stylist-profile", { ...store.get("stylist-profile", {}), [key]: p[key] }); rebuild(); } },
      options.map(([v, t]) => el("option", { value: v, selected: p[key] === v }, t))));
  $("#fit-profile").replaceChildren(el("div.grid-2",
    input("height_cm", "Boʻy (sm)", { min: "120", max: "220" }),
    input("weight_kg", "Vazn (kg)", { min: "30", max: "200" }),
    select("gender", "Jins", [["erkak", "Erkak"], ["ayol", "Ayol"]]),
    select("skin_tone", "Tana rangi", [["oq", "Oq / och"], ["bugdoy", "Bugʻdoyrang"], ["qoracha", "Qorachadan"], ["qora", "Qora / toʻq"]])));
}

function setup() {
  const dialog = $("#fitting-dialog");
  dialog.addEventListener("close", () => { stage?.dispose(); stage = null; });
  $("#fit-rotate").addEventListener("click", e => {
    stage.auto = !stage.auto;
    e.currentTarget.setAttribute("aria-pressed", String(stage.auto));
  });
  $$("[data-view]").forEach(b => b.addEventListener("click", () => { stage.view(b.dataset.view); }));
  $("#fit-zoom-in").addEventListener("click", () => stage.zoom(0.8));
  $("#fit-zoom-out").addEventListener("click", () => stage.zoom(1.25));
  $("#fit-photo").addEventListener("click", () => {
    const url = stage.renderer.domElement.toDataURL("image/png");
    const a = el("a", { href: url, download: "clothes-ai-3d.png" });
    document.body.append(a); a.click(); a.remove();
    toast("Rasm saqlandi");
  });
}
setup();
