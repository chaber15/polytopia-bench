// Draws a logged game's map as low-poly isometric tiles, in the spirit of Polytopia but with no game art.
// polyMapSVG(map, tribes, opts) -> SVG markup. map: {w, h, tiles, cities, units} from site/data.js;
// tribes: {playerId: tribeName}. opts: {tile: px width of a tile (default 48), id: unique prefix}.
(function () {
  const TRIBE = {
    Imperius: { line: "#2f62d8", roof: "#3d6fe0", ground: ["#97d46d", "#79b955", "#5f9a40"], tree: ["#3f9a45", "#2c7a34"] },
    Bardur:   { line: "#3b3633", roof: "#5a524c", ground: ["#e4e8de", "#c6ccbd", "#a2a995"], tree: ["#4f7f5e", "#3a6449"] },
    Xinxi:    { line: "#d23a32", roof: "#d8433b", ground: ["#b0c98a", "#93ad6f", "#768f55"], tree: ["#5f9145", "#467536"] },
    Oumaji:   { line: "#e0a91a", roof: "#efbf2a", ground: ["#efd994", "#d9bf74", "#b89c53"], tree: ["#8aa543", "#6d8a31"] },
  };
  const NEUTRAL = { ground: ["#a9d382", "#8dbb67", "#70994e"], tree: ["#479c4a", "#327c37"] };
  const WATER = { w: ["#63c3ec", "#3f9fcf", "#2f89b8"], o: ["#3a8fd0", "#2a6ea8", "#215c8f"] };
  const LAND_H = 7, SLAB = 9;

  function polyMapSVG(map, tribes, opts = {}) {
    const TW = opts.tile || 48, TH = TW / 2;
    const w = map.w, h = map.h, top = TW * 0.75, pad = 6;
    const W = (w + h) * TW / 2 + pad * 2, H = (w + h) * TH / 2 + top + SLAB + LAND_H + pad;
    const ox = h * TW / 2 + pad, oy = top;
    const P = (x, y, lift = 0) => [ox + (x - y) * TW / 2, oy + (x + y) * TH / 2 - lift];
    const tile = new Map(map.tiles.map(t => [t[0] + "," + t[1], t]));
    const city = new Map(map.cities.map(c => [c[0] + "," + c[1], c]));
    const units = new Map(map.units.map(u => [u[0] + "," + u[1], u]));
    const owner = (x, y) => (tile.get(x + "," + y) || [])[3] || 0;
    const style = o => TRIBE[tribes[o]] || null;
    const pts = a => a.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
    const poly = (a, fill, extra = "") => `<polygon points="${pts(a)}" fill="${fill}"${extra}/>`;
    const s = TW / 48;  // feature scale
    let out = "";

    for (let sum = 0; sum <= w + h - 2; sum++) {
      for (let x = Math.max(0, sum - h + 1); x <= Math.min(w - 1, sum); x++) {
        const y = sum - x, t = tile.get(x + "," + y);
        if (!t) { out += cloud(x, y); continue; }
        const [, , ter, own, imp, road] = t;
        const water = ter === "w" || ter === "o";
        const lift = water ? 0 : LAND_H;
        const st = style(own);
        const col = water ? WATER[ter] : (st || NEUTRAL).ground;
        const T = P(x, y, lift), R = P(x + 1, y, lift), B = P(x + 1, y + 1, lift), L = P(x, y + 1, lift);
        const d = lift + SLAB;
        out += poly([L, B, [B[0], B[1] + d], [L[0], L[1] + d]], col[1]);
        out += poly([B, R, [R[0], R[1] + d], [B[0], B[1] + d]], col[2]);
        out += poly([T, R, B, L], col[0], ` stroke="${col[1]}" stroke-width="0.6"`);
        const C = [(T[0] + B[0]) / 2, (T[1] + B[1]) / 2];
        // territory border: edges where the neighbour has another owner
        if (own && st) {
          const edges = [[T, R, x, y - 1], [R, B, x + 1, y], [B, L, x, y + 1], [L, T, x - 1, y]];
          for (const [a, b, nx, ny] of edges) {
            const n = tile.get(nx + "," + ny);
            if (owner(nx, ny) === own || (n && !n[3] && (n[2] === "w" || n[2] === "o"))) continue;
            const ia = [a[0] + (C[0] - a[0]) * 0.1, a[1] + (C[1] - a[1]) * 0.1], ib = [b[0] + (C[0] - b[0]) * 0.1, b[1] + (C[1] - b[1]) * 0.1];
            out += `<line x1="${ia[0].toFixed(1)}" y1="${ia[1].toFixed(1)}" x2="${ib[0].toFixed(1)}" y2="${ib[1].toFixed(1)}" stroke="${st.line}" stroke-width="${2.4 * s}" stroke-linecap="round"/>`;
          }
        }
        if (road) out += roads(x, y, C, lift);
        const c = city.get(x + "," + y);
        if (c) out += cityMark(C, c);
        else if (ter === "M") out += mountain(C, imp);
        else if (ter === "F" && !/Temple|Hut/.test(imp)) out += forest(C, st || NEUTRAL, x * 7 + y * 3);
        if (!c && imp) out += building(C, imp, ter, st);
        const u = units.get(x + "," + y);
        if (u) {
          const us = style(u[2]);
          out += `<circle cx="${(C[0] + 7 * s).toFixed(1)}" cy="${(C[1] + 2 * s).toFixed(1)}" r="${4.2 * s}" fill="${us ? us.line : "#888"}" stroke="#fff" stroke-width="${1.4 * s}"/>`;
        }
      }
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W.toFixed(0)} ${H.toFixed(0)}" role="img">${out}</svg>`;

    function cloud(x, y) {
      const T = P(x, y, 2), R = P(x + 1, y, 2), B = P(x + 1, y + 1, 2), L = P(x, y + 1, 2);
      const C = [(T[0] + B[0]) / 2, (T[1] + B[1]) / 2];
      return poly([T, R, B, L], "#dfe6ee") +
        [[-8, 0, 7], [0, -4, 9], [8, 0, 7], [0, 3, 7]].map(([dx, dy, r]) =>
          `<circle cx="${(C[0] + dx * s).toFixed(1)}" cy="${(C[1] + dy * s - 6 * s).toFixed(1)}" r="${(r * s).toFixed(1)}" fill="#f4f7fa"/>`).join("");
    }
    function roads(x, y, C, lift) {
      let r = "";
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]) {
        const n = tile.get((x + dx) + "," + (y + dy));
        if (!n || !(n[5] || city.has((x + dx) + "," + (y + dy)))) continue;
        const m = P(x + 0.5 + dx / 2, y + 0.5 + dy / 2, lift);
        r += `<line x1="${C[0].toFixed(1)}" y1="${C[1].toFixed(1)}" x2="${m[0].toFixed(1)}" y2="${m[1].toFixed(1)}" stroke="#c9a46a" stroke-width="${2.6 * s}" stroke-linecap="round"/>`;
      }
      return r;
    }
    function tree(cx, by, ht, col) {
      return poly([[cx, by - ht], [cx - ht * 0.38, by], [cx, by]], col[0]) + poly([[cx, by - ht], [cx + ht * 0.38, by], [cx, by]], col[1]);
    }
    function forest(C, st, seed) {
      const k = s;
      return tree(C[0] - 8 * k, C[1] + 1 * k, 15 * k, st.tree) + tree(C[0] + 7 * k, C[1] - 1 * k, 13 * k, st.tree) +
        (seed % 2 ? tree(C[0] - 1 * k, C[1] + 5 * k, 14 * k, st.tree) : "");
    }
    function mountain(C, imp) {
      const k = s, peak = [C[0] + 1 * k, C[1] - 20 * k], l = [C[0] - 15 * k, C[1] + 4 * k], r = [C[0] + 15 * k, C[1] + 4 * k], m = [C[0] + 3 * k, C[1] + 6 * k];
      const cap = t => [peak[0] + (t[0] - peak[0]) * 0.3, peak[1] + (t[1] - peak[1]) * 0.3];
      return poly([peak, l, m], "#a9b0b8") + poly([peak, m, r], "#868e98") + poly([peak, cap(l), cap(m)], "#f4f6f8") + poly([peak, cap(m), cap(r)], "#d9dee4") +
        (imp === "Mine" ? poly([[C[0] - 2 * k, C[1] + 5 * k], [C[0] + 2 * k, C[1] - 1 * k], [C[0] + 6 * k, C[1] + 5 * k]], "#3a2f28") : "");
    }
    function house(cx, by, k, roof) {
      const w = 7 * k, ht = 6 * k, rh = 5 * k;
      return poly([[cx - w, by - ht], [cx, by - ht + 3 * k], [cx, by + 3 * k], [cx - w, by]], "#f2e5c6") +
        poly([[cx, by - ht + 3 * k], [cx + w, by - ht], [cx + w, by], [cx, by + 3 * k]], "#d4bf95") +
        poly([[cx - w - k, by - ht], [cx - k * 0.5, by - ht - rh], [cx + k * 0.5, by - ht - rh], [cx + w + k, by - ht], [cx, by - ht + 3.5 * k]], roof);
    }
    function cityMark(C, c) {
      const [, , own, lvl, cap] = c, st = style(own), roof = st ? st.roof : "#a0522d", k = s;
      let r = "";
      const spots = lvl >= 4 ? [[-9, 0], [8, -1], [0, 6], [-1, -6]] : lvl >= 2 ? [[-7, 1], [7, 0], [0, 6]] : [[0, 3]];
      for (const [dx, dy] of spots.sort((a, b) => a[1] - b[1])) r += house(C[0] + dx * k, C[1] + dy * k, k, roof);
      if (cap) {
        const fx = C[0] + 1 * k, fy = C[1] - 16 * k;
        r += `<line x1="${fx}" y1="${fy}" x2="${fx}" y2="${fy + 12 * k}" stroke="#5b4636" stroke-width="${1.2 * k}"/>` +
          poly([[fx, fy], [fx + 9 * k, fy + 2.5 * k], [fx, fy + 5 * k]], st ? st.line : "#888");
      }
      return r;
    }
    function building(C, imp, ter, st) {
      const k = s;
      if (/^Monument/.test(imp)) return poly([[C[0] - 3 * k, C[1] + 2 * k], [C[0], C[1] - 18 * k], [C[0] + 3 * k, C[1] + 2 * k]], "#f2c14e") + poly([[C[0], C[1] - 18 * k], [C[0] + 3 * k, C[1] + 2 * k], [C[0], C[1] + 3 * k]], "#d49a22");
      if (/Temple/.test(imp)) return poly([[C[0] - 8 * k, C[1] + 2 * k], [C[0] + 8 * k, C[1] + 2 * k], [C[0] + 5 * k, C[1] - 3 * k], [C[0] - 5 * k, C[1] - 3 * k]], "#eef0f2") + poly([[C[0] - 4 * k, C[1] - 3 * k], [C[0] + 4 * k, C[1] - 3 * k], [C[0] + 2 * k, C[1] - 8 * k], [C[0] - 2 * k, C[1] - 8 * k]], "#d7dbe0");
      if (imp === "LightHouse") return `<rect x="${C[0] - 2.5 * k}" y="${C[1] - 16 * k}" width="${5 * k}" height="${16 * k}" fill="#f4f4f4"/><rect x="${C[0] - 2.5 * k}" y="${C[1] - 19 * k}" width="${5 * k}" height="${4 * k}" fill="#e2483d"/>`;
      if (imp === "Port") return poly([[C[0] - 9 * k, C[1]], [C[0], C[1] - 4.5 * k], [C[0] + 9 * k, C[1]], [C[0], C[1] + 4.5 * k]], "#a87a4a", ` stroke="#7a5532" stroke-width="${k}"`);
      if (imp === "Farm") return [-4, 0, 4].map(d => `<line x1="${C[0] - 9 * k + d * k}" y1="${C[1] + d * 0.5 * k}" x2="${C[0] + 1 * k + d * k}" y2="${C[1] - 5 * k + d * 0.5 * k}" stroke="#e8c34a" stroke-width="${2.2 * k}" stroke-linecap="round"/>`).join("");
      if (imp === "Mine" || ter === "w" || ter === "o") return "";
      return house(C[0], C[1] + 2 * k, k * 0.85, "#8a5a3c");
    }
  }
  window.polyMapSVG = polyMapSVG;
  // A game's final map: the in-game screenshot (img/game-<log>.png, made with the plugin's /stage endpoint) when it
  // exists, otherwise the drawn map. img/ is game art and not in git, so the drawn map is the fallback.
  window.polyMapArt = (g, opts) => `<img class="shot" src="img/game-${g.log}.png" alt="" ` +
    `onload="this.nextElementSibling && this.nextElementSibling.remove()" onerror="this.remove()">` + polyMapSVG(g.map, g.tribes, opts);
  window.POLY_TRIBE = TRIBE;
})();
