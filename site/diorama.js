// Header art: a small four-tribe island drawn with polyMapSVG, with a unit sprite standing in each territory.
// Sprites are game art (img/, not in git); if they are missing the island is drawn on its own.
// polyDiorama() -> HTML. Needs polymap.js.
(function () {
  const N = 6, TW = 48, TH = TW / 2, PAD = 6, LAND_H = 7;  // must match polyMapSVG's layout
  const TRIBES = { 1: "Imperius", 2: "Bardur", 3: "Xinxi", 4: "Oumaji" };
  // owner by quadrant: Xin-xi top, Oumaji right, Bardur left, Imperius front; a lake in the middle
  const owner = (x, y) => (y < 3 ? (x < 3 ? 3 : 4) : (x < 3 ? 2 : 1));
  const lake = new Set(["2,2", "3,2", "2,3", "3,3"]);
  const ter = { "0,2": "M", "3,0": "M", "2,5": "M", "2,0": "F", "5,2": "F", "0,3": "F", "3,5": "F", "5,4": "F" };
  const imp = { "1,0": "Farm", "4,2": "Port", "1,5": "LumberHut", "4,5": "Market" };
  const cities = [[0, 0, 3, 3, 1, ""], [5, 0, 4, 3, 1, ""], [0, 5, 2, 3, 1, ""], [5, 5, 1, 4, 1, ""]];
  const units = [  // x, y, sprite, scale; drawn back to front. The rider is shrunk a little so it doesn't dominate.
    [1, 1, "archer", 1], [4, 1, "defender", 1], [1, 4, "rider", 0.845], [4, 4, "warrior", 1],
  ];
  const FRAME = 250 / 311, FOOT = [0.448, 0.842];  // sprite frame aspect, foot point inside the frame
  const SIZE = 2.1;                                // sprite frame width in tiles

  function polyDiorama() {
    const tiles = [];
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const k = x + "," + y;
      tiles.push(lake.has(k) ? [x, y, "w", 0, "", 0, ""] : [x, y, ter[k] || "f", owner(x, y), imp[k] || "", 0, ""]);
    }
    const svg = polyMapSVG({ w: N, h: N, tiles, cities, units: [] }, TRIBES, { tile: TW });
    const W = 2 * N * TW / 2 + PAD * 2, H = 2 * N * TH / 2 + TW * 0.75 + 9 + LAND_H + PAD;
    const imgs = units.map(([x, y, n, k]) => {
      const fw = SIZE * TW * k, fh = fw / FRAME;
      const cx = N * TW / 2 + PAD + (x - y) * TW / 2, cy = TW * 0.75 + (x + y + 1) * TH / 2 - LAND_H;
      const left = (cx - fw * FOOT[0]) / W * 100, top = (cy - fh * FOOT[1]) / H * 100;
      return `<img src="img/${n}.png" onerror="this.remove()" alt="" style="position:absolute;left:${left.toFixed(2)}%;top:${top.toFixed(2)}%;width:${(fw / W * 100).toFixed(2)}%">`;
    }).join("");
    return `<div class="diorama" style="position:relative">${svg}${imgs}</div>`;
  }
  window.polyDiorama = polyDiorama;
})();
