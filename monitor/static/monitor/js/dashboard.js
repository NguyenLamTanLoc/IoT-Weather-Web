(() => {
  const API = document.body.dataset.api;
  const EXPORT = document.body.dataset.export;
  const REFRESH_MS = 10000;
  const COLORS = { temp: "#cf5a1f", hum: "#1d6fa5" };
  let range = 180;
  let chart = null;

  const $ = (sel) => document.querySelector(sel);
  const num = (v, d = 1) => (v == null ? "–" : Number(v).toFixed(d).replace(".", ","));
  const hhmm = (ms) => new Date(ms).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });

  /* ---------- Biểu đồ ---------- */
  // Tô nền vùng dự báo và vẽ đường "Bây giờ"
  const forecastZone = {
    id: "forecastZone",
    beforeDatasetsDraw(c) {
      const now = c.options.plugins.forecastZone && c.options.plugins.forecastZone.now;
      if (!now) return;
      const { ctx, chartArea: a, scales } = c;
      const x = scales.x.getPixelForValue(now);
      if (x >= a.right) return;
      ctx.save();
      ctx.fillStyle = "rgba(40, 140, 120, 0.10)";
      ctx.fillRect(x, a.top, a.right - x, a.bottom - a.top);
      ctx.strokeStyle = "rgba(18, 48, 42, 0.45)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(x, a.top); ctx.lineTo(x, a.bottom); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#12302a";
      ctx.font = "600 11px 'Be Vietnam Pro', sans-serif";
      ctx.fillText("Bây giờ", x + 6, a.top + 14);
      ctx.restore();
    },
  };

  const line = (label, color, axis, extra = {}) => ({
    label, data: [], yAxisID: axis, borderColor: color, backgroundColor: color,
    borderWidth: 2.2, pointRadius: 0, pointHoverRadius: 4, tension: 0.3, ...extra,
  });
  function buildChart() {
    chart = new Chart($("#chart"), {
      type: "line",
      data: {
        datasets: [
          line("Nhiệt độ (°C)", COLORS.temp, "yT"),
          line("Dự báo nhiệt độ", COLORS.temp, "yT", { borderDash: [6, 5] }),
          line("Độ ẩm (%)", COLORS.hum, "yH"),
          line("Dự báo độ ẩm", COLORS.hum, "yH", { borderDash: [6, 5] }),
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        parsing: false, normalized: true,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: {
          x: {
            type: "linear",
            ticks: { maxTicksLimit: 8, callback: (v) => hhmm(v), color: "#4d655f" },
            grid: { color: "rgba(18,48,42,0.07)" },
          },
          yT: {
            position: "left", title: { display: true, text: "Nhiệt độ (°C)", color: COLORS.temp },
            ticks: { color: COLORS.temp }, grid: { color: "rgba(18,48,42,0.07)" },
          },
          yH: {
            position: "right", title: { display: true, text: "Độ ẩm (%)", color: COLORS.hum },
            ticks: { color: COLORS.hum }, grid: { drawOnChartArea: false },
          },
        },
        plugins: {
          forecastZone: { now: null },
          legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
          tooltip: {
            callbacks: {
              title: (items) => hhmm(items[0].parsed.x),
              label: (i) => `${i.dataset.label}: ${num(i.parsed.y)}`,
            },
          },
        },
      },
      plugins: [forecastZone],
    });
  }

  function updateChart(d) {
    const now = d.now;
    const pts = (key) => d.history.map((p) => ({ x: p.t, y: p[key] }));
    const anchor = d.latest ? { t: d.latest.t, temperature: d.latest.temperature, humidity: d.latest.humidity } : null;
    const fc = d.forecast.points;
    const fcLine = (key) => (!fc.length || !anchor ? [] : [
      { x: anchor.t, y: anchor[key] },
      ...fc.map((p) => ({ x: p.t, y: p[key] })),
    ]);
    const ds = chart.data.datasets;
    ds[0].data = pts("temperature"); ds[1].data = fcLine("temperature");
    ds[2].data = pts("humidity");    ds[3].data = fcLine("humidity");
    chart.options.scales.x.min = now - range * 60000;
    chart.options.scales.x.max = now + d.forecast.horizon * 60000;
    chart.options.plugins.forecastZone.now = now;
    chart.update("none");
  }

  /* ---------- Thẻ số đo, bảng, gợi ý ---------- */
  function outlook(el, unit, current, end, digits, minutesAhead) {
    if (end == null) { el.textContent = "Chưa có dự báo"; return; }
    const diff = end - current;
    const dir = Math.abs(diff) < 0.05 * (unit === "%" ? 10 : 1) ? "gần như không đổi"
      : diff > 0 ? `tăng ${num(Math.abs(diff), digits)}${unit === "%" ? " điểm %" : "°C"}`
      : `giảm ${num(Math.abs(diff), digits)}${unit === "%" ? " điểm %" : "°C"}`;
    el.innerHTML = `Sau ${minutesAhead} phút: <strong>${num(end, digits)}${unit === "%" ? "%" : "°C"}</strong>, ${dir}`;
  }

  function renderReadings(d) {
    const next = d.forecast.points[0];
    $("#tNow").textContent = d.latest ? num(d.latest.temperature, d.decimals) : "–";
    $("#hNow").textContent = d.latest ? num(d.latest.humidity, d.decimals) : "–";
    if (d.latest && next) {
      outlook($("#tOutlook"), "°C", d.latest.temperature, next.temperature, 1, next.minutes_ahead);
      outlook($("#hOutlook"), "%", d.latest.humidity, next.humidity, 0, next.minutes_ahead);
    } else {
      $("#tOutlook").textContent = $("#hOutlook").textContent = d.latest ? "Chưa có dự báo" : "Chưa có số liệu";
    }
  }

  function renderTable(d) {
    const body = $("#forecastRows");
    if (!d.forecast.points.length) {
      body.innerHTML = '<tr><td colspan="3" class="empty">Chưa có dự báo</td></tr>';
      body.querySelector(".empty").textContent = d.forecast.error || "Chưa có dự báo";
      $("#modelName").textContent = "";
      return;
    }
    body.innerHTML = d.forecast.points.map((p) => `
      <tr>
        <th scope="row">Sau ${p.hours_ahead} giờ</th>
        <td>${num(p.temperature)}°C</td>
        <td>${num(p.humidity, 0)}%</td>
      </tr>`).join("");
    $("#modelName").textContent = "Mô hình: " + d.forecast.model;
  }

  function renderAdvice(d) {
    $("#adviceList").innerHTML = d.advice.map((a) => `
      <li class="advice-item" data-level="${a.level}">
        <p class="title">${a.title}</p>
        <p class="detail">${a.detail}</p>
      </li>`).join("");
  }

  function renderStatus(d) {
    const el = $("#status");
    if (!d.latest) { el.dataset.state = "offline"; $("#statusText").textContent = "Chưa có số liệu"; return; }
    el.dataset.state = d.online ? "online" : "offline";
    $("#statusText").textContent = d.online
      ? `Đang hoạt động · cập nhật lúc ${hhmm(d.latest.t)}`
      : `Mất kết nối · số liệu cuối lúc ${hhmm(d.latest.t)}`;
  }

  function updateExportLinks() {
    $("#exportCsv").href = `${EXPORT}?minutes=${range}&format=csv`;
    $("#exportJson").href = `${EXPORT}?minutes=${range}&format=json`;
  }

  /* ---------- Tải dữ liệu ---------- */
  async function load() {
    try {
      const res = await fetch(`${API}?minutes=${range}`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      const d = await res.json();
      renderStatus(d); renderReadings(d); renderTable(d); renderAdvice(d); updateChart(d);
    } catch (err) {
      const el = $("#status");
      el.dataset.state = "offline";
      $("#statusText").textContent = "Không tải được số liệu từ máy chủ";
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      range = Number(btn.dataset.range);
      document.querySelectorAll(".tab").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      updateExportLinks();
      load();
    });
  });

  buildChart();
  updateExportLinks();
  load();
  setInterval(load, REFRESH_MS);
})();
