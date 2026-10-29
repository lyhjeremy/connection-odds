/* Connection Odds lookup tool. Reads assets/tool.json from this site and nothing else. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var D, hubIdx = {}, haIdx = {};
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December"];
  var TARGETS = [0.10, 0.05, 0.01];
  var GREY_BELOW = 35;

  function hourLabel(h) {
    var s = h % 12 === 0 ? 12 : h % 12;
    return s + ":00 to " + s + ":59 " + (h < 12 ? "am" : "pm");
  }
  function pct(x, d) {
    if (x == null || isNaN(x)) return "n/a";
    var v = 100 * x;
    if (d == null) d = v < 10 ? 1 : 0;
    return v.toFixed(d) + "%";
  }
  function fmtInt(n) { return n.toLocaleString("en-US"); }

  function wilson(k, n) {
    var z = 1.959964, p = k / n, den = 1 + z * z / n;
    var mid = (p + z * z / (2 * n)) / den;
    var half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den;
    return [mid - half, mid + half];
  }

  function modelP(W, hub, air, hour, month, layover) {
    var m = D.model[String(W)];
    var i = haIdx[hub + "|" + air];
    var b = Math.max(0, Math.min(29, Math.floor((layover - 30) / 5)));
    var base = m.b0 + (m.ha[i] || 0) + m.lay[b] + m.hr[hour] + m.mo[month - 1] +
      (m.lay_ha[i] ? m.lay_ha[i][b] : 0) + (m.mo_hub[hub] ? m.mo_hub[hub][month - 1] : 0) +
      (m.hr_hub[hub] ? m.hr_hub[hub][hour] : 0);
    var s = 0;
    for (var d = 0; d < 7; d++) s += 1 / (1 + Math.exp(-(base + m.dw[d])));
    return s / 7;
  }

  var cellCache = {};
  function cellMap(hub, air) {
    var key = hub + "|" + air;
    if (cellCache[key]) return cellCache[key];
    // seven numbers a cell: key step, n, k at the default W, then |k_W - k_default|
    // for the other W values in order (see scripts/export_web.py)
    var out = {}, f = D.cells[key] || [], others = D.W_values.filter(function (w) { return w !== D.W_default; });
    var stride = 3 + others.length, k = -1;
    for (var i = 0; i + stride <= f.length; i += stride) {
      k += f[i];
      var hour = Math.floor(k / 120), month = Math.floor((k % 120) / 10) + 1, bucket = k % 10;
      var ks = {}, k0 = f[i + 2];
      ks[D.W_default] = k0;
      others.forEach(function (w, j) { ks[w] = w < D.W_default ? k0 - f[i + 3 + j] : k0 + f[i + 3 + j]; });
      out[hour + ":" + month + ":" + bucket] = { n: f[i + 1], ks: ks };
    }
    cellCache[key] = out;
    return out;
  }
  function cell(hub, air, hour, month, layover, W) {
    var bucket = Math.min(9, Math.floor((layover - 30) / 15));
    var c = cellMap(hub, air)[hour + ":" + month + ":" + bucket];
    if (!c) return { bucket: bucket, n: 0 };
    return { bucket: bucket, n: c.n, k: c.ks[W] };
  }

  function estimate(sel, layover) {
    var c = cell(sel.hub, sel.air, sel.hour, sel.month, layover, sel.W);
    var mp = modelP(sel.W, sel.hub, sel.air, sel.hour, sel.month, layover);
    if (D.shipped === "lookup" && c.n >= D.min_cell) return { p: c.k / c.n, src: "cell", cell: c, model: mp };
    return { p: mp, src: "model", cell: c, model: mp };
  }

  function needed(sel) {
    var xs = [], ps = [];
    for (var L = 30; L <= 180; L += 5) { xs.push(L); ps.push(estimate(sel, L).p); }
    return TARGETS.map(function (t) {
      var best = null;
      for (var j = xs.length - 1; j >= 0; j--) { if (ps[j] > t) break; best = xs[j]; }
      return best;
    });
  }

  function current() {
    return {
      hub: $("hub").value, air: $("air").value, hour: +$("hour").value,
      month: +$("month").value, layover: +$("lay").value, W: +$("w").value
    };
  }

  function fillAirlines() {
    var h = D.hubs[hubIdx[$("hub").value]], sel = $("air"), prev = sel.value;
    sel.innerHTML = "";
    h.airlines.forEach(function (a, i) {
      var o = document.createElement("option");
      o.value = a;
      o.textContent = (D.airlines[a] || a) + " (" + fmtInt(h.pairs[i]) + " pairs)";
      sel.appendChild(o);
    });
    if (h.airlines.indexOf(prev) >= 0) sel.value = prev;
  }

  function drawChart(sel) {
    var W = Math.max(320, Math.min(640, $("chart").clientWidth || 640)), H = W < 480 ? 240 : 260, L = 42, R = 10, T = 14, B = 36;
    var pts = [], obs = [];
    for (var x = 30; x <= 180; x += 5) pts.push([x, estimate(sel, x).model]);
    for (var b = 0; b < 10; b++) {
      var c = cell(sel.hub, sel.air, sel.hour, sel.month, 30 + 15 * b, sel.W);
      if (c.n >= D.min_cell) { var ci = wilson(c.k, c.n); obs.push([30 + 15 * b, c.k / c.n, ci[0], ci[1], c.n]); }
    }
    var ymax = 0.1;
    pts.forEach(function (p) { ymax = Math.max(ymax, p[1]); });
    obs.forEach(function (o) { ymax = Math.max(ymax, o[3]); });
    ymax = Math.ceil(ymax * 10) / 10;
    var sx = function (v) { return L + (v - 30) / 150 * (W - L - R); };
    var sy = function (v) { return H - B - v / ymax * (H - T - B); };
    var s = [];
    s.push('<rect class="grey" x="' + sx(30) + '" y="' + T + '" width="' + (sx(GREY_BELOW) - sx(30)) + '" height="' + (H - T - B) + '"/>');
    for (var g = 0; g <= ymax + 1e-9; g += (ymax > 0.3 ? 0.1 : 0.05)) {
      s.push('<line class="gl" x1="' + L + '" x2="' + (W - R) + '" y1="' + sy(g) + '" y2="' + sy(g) + '"/>');
      s.push('<text class="tk" x="' + (L - 6) + '" y="' + (sy(g) + 4) + '" text-anchor="end">' + Math.round(g * 100) + '%</text>');
    }
    (W < 480 ? [30, 60, 90, 120, 150, 180] : [30, 45, 60, 90, 120, 150, 180]).forEach(function (v) {
      s.push('<text class="tk" x="' + sx(v) + '" y="' + (H - B + 17) + '" text-anchor="middle">' + v + '</text>');
    });
    s.push('<line class="ax" x1="' + L + '" x2="' + (W - R) + '" y1="' + (H - B) + '" y2="' + (H - B) + '"/>');
    s.push('<text class="tk lab" x="' + ((W + L) / 2) + '" y="' + (H - 3) + '" text-anchor="middle">Scheduled layover, minutes</text>');
    obs.forEach(function (o) {
      var x0 = sx(o[0]), x1 = sx(Math.min(o[0] + 15, 180));
      s.push('<rect class="ob" x="' + x0 + '" y="' + sy(o[3]) + '" width="' + (x1 - x0 - 1) + '" height="' + Math.max(1, sy(o[2]) - sy(o[3])) + '"/>');
      s.push('<line class="obm" x1="' + x0 + '" x2="' + (x1 - 1) + '" y1="' + sy(o[1]) + '" y2="' + sy(o[1]) + '"/>');
    });
    s.push('<polyline class="ml" points="' + pts.map(function (p) { return sx(p[0]) + "," + sy(p[1]); }).join(" ") + '"/>');
    var e = estimate(sel, sel.layover);
    s.push('<line class="cur" x1="' + sx(sel.layover) + '" x2="' + sx(sel.layover) + '" y1="' + T + '" y2="' + (H - B) + '"/>');
    s.push('<circle class="dot" cx="' + sx(sel.layover) + '" cy="' + sy(e.p) + '" r="4.5"/>');
    $("chart").innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Estimated chance of missing the connection at each layover from 30 to 180 minutes for the chosen hub, airline, hour and month">' + s.join("") + "</svg>";
  }

  function render() {
    var sel = current();
    $("lay-val").textContent = sel.layover + " min";
    $("w-val").textContent = sel.W + " min";
    var e = estimate(sel, sel.layover);
    var big = $("big");
    big.textContent = pct(e.p);
    big.className = "gauge" + (sel.layover < GREY_BELOW ? " greyed" : "");
    $("big-sub").textContent = "chance of missing a " + sel.layover + "-minute connection on " +
      (D.airlines[sel.air] || sel.air) + " at " + sel.hub + ", arriving " + hourLabel(sel.hour) + " in " + MONTHS[sel.month - 1] + ".";
    var c = e.cell, lo = 30 + 15 * c.bucket, hi = Math.min(lo + 14, 180);
    var src;
    if (c.n >= D.min_cell) {
      var ci = wilson(c.k, c.n);
      src = "Observed in this cell (layovers " + lo + " to " + hi + " min): " + fmtInt(c.n) + " pairs, " + pct(c.k / c.n) +
        " missed, 95% interval " + pct(ci[0]) + " to " + pct(ci[1]) + ". ";
      src += e.src === "model" ? "The headline figure is the model's, which tested better calibrated." : "The headline figure is this cell's observed rate.";
    } else {
      src = "This cell (layovers " + lo + " to " + hi + " min) has " + "fewer than " + D.min_cell +
        " pairs, so the figure comes from the model alone.";
    }
    $("src").textContent = src;
    $("grey-note").hidden = sel.layover >= GREY_BELOW;
    var nd = needed(sel);
    ["n90", "n95", "n99"].forEach(function (id, i) {
      $(id).textContent = nd[i] == null ? "over 180" : nd[i] + " min";
    });
    drawChart(sel);
  }

  function init(data) {
    D = data;
    D.hubs.forEach(function (h, i) { hubIdx[h.code] = i; });
    D.ha_order.forEach(function (k, i) { haIdx[k] = i; });
    var hs = $("hub");
    D.hubs.forEach(function (h) {
      var o = document.createElement("option"); o.value = h.code; o.textContent = h.code + " " + h.name; hs.appendChild(o);
    });
    var hr = $("hour");
    for (var h = 0; h < 24; h++) { var o = document.createElement("option"); o.value = h; o.textContent = hourLabel(h); hr.appendChild(o); }
    hr.value = 17;
    var mo = $("month");
    MONTHS.forEach(function (m, i) { var o = document.createElement("option"); o.value = i + 1; o.textContent = m; mo.appendChild(o); });
    mo.value = 7;
    var w = $("w");
    w.min = D.W_values[0]; w.max = D.W_values[D.W_values.length - 1]; w.step = 5; w.value = D.W_default;
    fillAirlines();
    hs.addEventListener("change", function () { fillAirlines(); render(); });
    ["air", "hour", "month"].forEach(function (id) { $(id).addEventListener("change", render); });
    ["lay", "w"].forEach(function (id) { $(id).addEventListener("input", render); });
    var lastW = 0;
    window.addEventListener("resize", function () {
      var w = $("chart").clientWidth;
      if (Math.abs(w - lastW) > 40) { lastW = w; render(); }
    });
    document.querySelectorAll(".skeleton").forEach(function (el) { el.classList.remove("skeleton"); });
    $("tool").removeAttribute("aria-busy");
    render();
  }

  fetch("assets/tool.json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(init).catch(function (err) {
    $("tool").removeAttribute("aria-busy");
    $("src").textContent = "The data file did not load (" + err.message + "). Reload the page to try again.";
  });
})();
