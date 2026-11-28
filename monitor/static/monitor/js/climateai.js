(() => {
  const B = document.body, API = B.dataset.api, PAGE = B.dataset.page;
  const $ = (s) => document.querySelector(s), $$ = (s) => document.querySelectorAll(s);
  const num = (v, d = 1) => (v == null ? "–" : Number(v).toFixed(d).replace(".", ","));
  const hhmm = (ms) => new Date(ms).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
  const hhmmss = (ms) => new Date(ms).toLocaleTimeString("vi-VN", { hour12: false });
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const C = { temp: "#F97316", hum: "#0EA5E9" }, tick = { color: "#64748B" }, grid = { color: "#E2E8F0" };
  const LEVEL = { alert: ["Khẩn cấp", "bad"], warn: ["Khuyến nghị", "warn"], ok: ["Ổn định", "ok"] };
  let range = PAGE === "overview" ? 1440 : 180, metric = "temperature", chart = null, last = null;

  /* ---- khung chung: giờ cập nhật, trạng thái thiết bị ---- */
  function renderShell(d) {
    const on = d.online, pill = $("#pill");
    pill.className = "pill " + (on ? "ok" : "off");
    pill.textContent = d.latest ? (on ? "ESP32 trực tuyến" : "ESP32 mất kết nối") : "Chưa có số liệu";
    $("#updated").textContent = d.latest ? `${on ? "Cập nhật" : "Số liệu cuối"} lúc ${hhmmss(d.latest.t)}` : "Chưa có số liệu";
    $("#sideStatus").innerHTML = on
      ? `Kết nối ổn định<b>1 thiết bị trực tuyến</b>${esc(d.latest.device)} · Cảm biến`
      : `Chưa có kết nối<b style="color:var(--bad)">Thiết bị ngoại tuyến</b>Kiểm tra nguồn và Wi-Fi của ESP32`;
    if (PAGE.startsWith("csv_")) { $("#updated").textContent = "Nhập dữ liệu thô từ tệp CSV"; pill.className = "pill ok"; pill.textContent = "Nhập dữ liệu CSV"; }
    const dp = $("#devPill"); if (dp) { dp.className = pill.className; dp.textContent = on ? "Trực tuyến" : "Ngoại tuyến"; }
  }

  /* ---- biểu đồ ---- */
  const nowLine = { id: "nowLine", afterDatasetsDraw(c) {
    const now = c.options.plugins.nowLine && c.options.plugins.nowLine.now; if (!now) return;
    const { ctx, chartArea: a, scales } = c, x = scales.x.getPixelForValue(now); if (x >= a.right || x <= a.left) return;
    ctx.save(); ctx.strokeStyle = "#2563EB"; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x, a.top); ctx.lineTo(x, a.bottom); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = "#2563EB"; ctx.font = "600 12px Inter, sans-serif"; ctx.fillText("Bây giờ", x + 6, a.top + 14); ctx.restore(); } };
  const ln = (label, color, extra = {}) => ({ label, data: [], borderColor: color, backgroundColor: color, borderWidth: 2.2, pointRadius: 0, tension: 0.3, ...extra });
  const xAxis = { type: "linear", ticks: { maxTicksLimit: 8, callback: (v) => hhmm(v), ...tick }, grid: { display: false } };
  const tip = { callbacks: { title: (i) => hhmm(i[0].parsed.x), label: (i) => `${i.dataset.label}: ${num(i.parsed.y)}` } };
  function build() {
    const cv = $("#chart"); if (!cv) return;
    const base = { responsive: true, maintainAspectRatio: false, animation: false, parsing: false, interaction: { mode: "nearest", axis: "x", intersect: false } };
    if (PAGE === "overview") {
      chart = new Chart(cv, { type: "line", plugins: [nowLine], data: { datasets: [ln("Nhiệt độ (°C)", C.temp, { yAxisID: "y" }), ln("Dự báo nhiệt độ", C.temp, { yAxisID: "y", borderDash: [6, 5] }), ln("Độ ẩm (%)", C.hum, { yAxisID: "y1" }), ln("Dự báo độ ẩm", C.hum, { yAxisID: "y1", borderDash: [6, 5] })] },
        options: { ...base, scales: { x: xAxis, y: { position: "left", grid, ticks: tick }, y1: { position: "right", grid: { drawOnChartArea: false }, ticks: tick } }, plugins: { nowLine: {}, tooltip: tip, legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } } } });
    } else {
      chart = new Chart(cv, { type: "line", plugins: [nowLine], data: { datasets: [] },
        options: { ...base, scales: { x: xAxis, y: { grid, ticks: tick } }, plugins: { nowLine: {}, tooltip: tip, legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, filter: (i) => i.text !== "lo" } } } } });
    }
  }
  const series = (d, key) => d.history.map((p) => ({ x: p.t, y: p[key] }));
  const fcLine = (d, key) => (!d.forecast.points.length || !d.latest ? [] : [{ x: d.latest.t, y: d.latest[key] }, ...d.forecast.points.map((p) => ({ x: p.t, y: p[key] }))]);

  /* ---- Tổng quan ---- */
  function delta(d, key, unit, digits) {
    const el = $(key === "temperature" ? "#tDelta" : "#hDelta"); if (!d.latest) return;
    const ref = d.history.find((p) => p.t >= d.now - 3600000);
    if (!ref || d.now - d.history[0].t < 3000000) { el.textContent = "Chưa đủ dữ liệu 1 giờ"; return; }
    const diff = d.latest[key] - ref[key];
    el.textContent = `${diff >= 0 ? "Tăng" : "Giảm"} ${num(Math.abs(diff), digits)}${unit} so với 1 giờ trước`;
  }
  function overview(d) {
    $("#tNow").textContent = d.latest ? num(d.latest.temperature, d.decimals) : "–";
    $("#hNow").textContent = d.latest ? num(d.latest.humidity, d.decimals) : "–";
    if (range >= 60) { delta(d, "temperature", "°C", 1); delta(d, "humidity", " điểm %", 0); }
    const worst = d.advice.find((a) => a.level === "alert") || d.advice.find((a) => a.level === "warn");
    const st = $("#state"); st.textContent = !d.latest ? "–" : worst ? (worst.level === "alert" ? "Cần xử lý" : "Cần chú ý") : "Bình thường";
    st.style.color = worst ? (worst.level === "alert" ? "var(--bad)" : "var(--warn)") : "var(--ok)";
    $("#stateNote").textContent = !d.latest ? "" : worst ? worst.title : "Các chỉ số trong ngưỡng";
    const n = d.forecast.points[0];
    $("#next").textContent = n ? `${num(n.temperature)}°C / ${num(n.humidity, 0)}%` : "–";
    $("#nextNote").textContent = n ? `Lúc ${hhmm(n.t)}` : (d.forecast.error || "Chưa có dự báo");
    const ds = chart.data.datasets;
    ds[0].data = series(d, "temperature"); ds[1].data = fcLine(d, "temperature");
    ds[2].data = series(d, "humidity"); ds[3].data = fcLine(d, "humidity");
    chart.options.scales.x.min = d.now - range * 60000; chart.options.scales.x.max = d.now + d.forecast.horizon * 60000;
    chart.options.plugins.nowLine.now = d.now; chart.update("none");
    const cls = { alert: "q-warn", warn: "q-info", ok: "q-ok" };
    $("#quick").innerHTML = d.advice.slice(0, 3).map((a) => `<div class="${cls[a.level] || "q-ok"}"><b>${esc(a.title)}</b>${esc(a.detail)}</div>`).join("");
  }

  /* ---- Dự báo ---- */
  function forecast(d) {
    const pts = d.forecast.points, t = metric === "temperature", c = t ? C.temp : C.hum, u = t ? "°C" : "%", dg = t ? 1 : 0, lo = t ? "t_lo" : "h_lo", hi = t ? "t_hi" : "h_hi";
    const csvBanner = d.source === "csv" ? `Nguồn: tệp CSV · ${d.count} bản ghi · Dữ liệu kết thúc lúc ${hhmm(d.now)} · Không ảnh hưởng dữ liệu trực tiếp` : null;
    $("#fcBanner").textContent = csvBanner || pts.length ? `Dự báo AI (${d.forecast.model}) · Cập nhật lúc ${hhmm(d.now)} · Từ ${hhmm(pts[0].t)} đến ${hhmm(pts[pts.length - 1].t)}`
      : `${d.forecast.error || "Chưa có dự báo. Cần có số liệu từ cảm biến ESP32."}`;
    $("#fcTitle").textContent = `${t ? "Nhiệt độ" : "Độ ẩm"} trong 6 giờ tới`;
    const band = (k) => (pts.length && d.latest ? [{ x: d.latest.t, y: d.latest[metric] }, ...pts.map((p) => ({ x: p.t, y: p[k] }))] : []);
    chart.data.datasets = [ln("lo", c, { data: band(lo), borderWidth: 0, fill: false }), ln("Vùng dao động giữa 3 mô hình", c, { data: band(hi), borderWidth: 0, fill: "-1", backgroundColor: c + "33" }),
      ln("Thực tế", c, { data: series(d, metric) }), ln("Dự báo", c, { data: fcLine(d, metric), borderDash: [6, 5] })];
    chart.options.scales.x.min = d.now - range * 60000; chart.options.scales.x.max = d.now + d.forecast.horizon * 60000;
    chart.options.plugins.nowLine.now = d.now; chart.update("none");
    const v = pts.map((p) => p[metric]), T = pts.map((p) => p.temperature), H = pts.map((p) => p.humidity);
    $("#fcRange").textContent = pts.length ? `${hhmm(pts[0].t)} – ${hhmm(pts[pts.length - 1].t)} · ${d.location}` : "\u00a0";
    $("#kMin").textContent = v.length ? num(Math.min(...v), dg) + u : "–"; $("#kMax").textContent = v.length ? num(Math.max(...v), dg) + u : "–";
    $("#kAvg").textContent = v.length ? num(v.reduce((a, b) => a + b, 0) / v.length, dg) + u : "–";
    $("#kHum").textContent = H.length ? num(H[H.length - 1], 0) + "%" : "–";
    $("#kSpread").textContent = pts.length ? "±" + num(Math.max(...pts.map((p) => (p[hi] - p[lo]) / 2)), dg) + u : "–";
    const a = d.advice[0], box = $("#fcAlert"), bad = a && a.level !== "ok";
    box.className = "alert" + (bad ? "" : " ok");
    box.querySelector("h3").textContent = a ? a.title : "Chưa có phân tích"; box.querySelector("p").textContent = a ? a.detail : "";
  }

  /* ---- Gợi ý ---- */
  let filter = "all";
  function suggestions(d) {
    const A = d.advice, urgent = A.filter((a) => a.level === "alert").length, warn = A.filter((a) => a.level === "warn").length;
    $("#sgBanner").textContent = `${urgent} việc cần ưu tiên · ${warn} khuyến nghị đang chờ bạn · Phân tích lúc ${hhmm(d.now)}`;
    $$("#chips button").forEach((b) => { const n = b.dataset.level === "all" ? A.length : b.dataset.level === "alert" ? urgent : warn; b.textContent = b.textContent.replace(/ \(\d+\)$/, "") + ` (${n})`; });
    const list = A.filter((a) => filter === "all" || a.level === filter);
    $("#sgList").innerHTML = list.length ? list.map((a) => `<div class="card sg"><div class="body"><h3>${esc(a.title)}</h3><p>${esc(a.detail)}</p></div><span class="pill ${LEVEL[a.level][1]}">${LEVEL[a.level][0]}</span></div>`).join("")
      : '<div class="card empty">Không có gợi ý nào ở mức này.</div>';
  }

  /* ---- tải dữ liệu ---- */
  async function load() {
    try {
      const res = await fetch(`${API}?minutes=${range}${PAGE === "history" || PAGE === "settings" ? "&light=1" : ""}`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      last = await res.json(); renderShell(last);
      if (PAGE === "overview") overview(last); else if (PAGE === "forecast") forecast(last); else if (PAGE === "suggestions") suggestions(last);
    } catch (e) { $("#pill").className = "pill off"; $("#pill").textContent = "Không tải được số liệu"; }
  }
  $$("[data-range]").forEach((b) => b.addEventListener("click", () => { range = +b.dataset.range; $$("[data-range]").forEach((x) => x.classList.toggle("on", x === b)); load(); }));
  $$("[data-metric]").forEach((b) => b.addEventListener("click", () => { metric = b.dataset.metric; $$("[data-metric]").forEach((x) => x.classList.toggle("on", x === b)); if (last) forecast(last); }));
  $$("[data-level]").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.level; $$("[data-level]").forEach((x) => x.classList.toggle("on", x === b)); if (last) suggestions(last); }));
  $$(".thr").forEach((t) => { const [lo, hi] = t.querySelectorAll(".num"), bar = t.querySelector(".range i"), max = +t.dataset.max;
    const up = () => { bar.style.marginLeft = Math.max(0, lo.value / max * 100) + "%"; bar.style.width = Math.max(0, (hi.value - lo.value) / max * 100) + "%"; };
    lo.addEventListener("input", up); hi.addEventListener("input", up); up(); });
  async function loadCsv(d) {
    last = d;
    try { const r = await fetch(`${API}?minutes=60&light=1`, { cache: "no-store" }); renderShell(await r.json()); } catch (e) {}
    $("#updated").textContent = `Dữ liệu đến ${new Date(d.now).toLocaleString("vi-VN", { hour12: false, hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", year: "numeric" })}`;
    $("#pill").className = "pill ok"; $("#pill").textContent = "Nguồn tệp CSV";
    forecast(d);
  }
  const csvEl = document.getElementById("csv-data");
  const form = $("#csvForm"), file = $("#csvFile"), drop = $("#drop");
  if (file) {
    file.addEventListener("change", () => file.files.length && form.submit());
    ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));
    drop.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files.length) { file.files = e.dataTransfer.files; form.submit(); } });
  }
  build();
  if (csvEl) loadCsv(JSON.parse(csvEl.textContent));
  else { load(); setInterval(load, 10000); }
})();
