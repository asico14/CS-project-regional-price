// Draws the price history chart on the product detail page.
// The data comes from the page itself (json_script "history-data"):
// [{label: "Store", data: [{x: timestampMs, y: price}, ...]}, ...]
(function () {
  const canvas = document.getElementById("history-chart");
  const dataElement = document.getElementById("history-data");
  if (!canvas || !dataElement || typeof Chart === "undefined") {
    return;
  }

  // Colour-blind-friendly palette (Okabe-Ito), repeated with dashes
  // when there are more stores than colours.
  const colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"];
  const series = JSON.parse(dataElement.textContent);

  const datasets = series.map((line, index) => ({
    label: line.label,
    data: line.data,
    borderColor: colors[index % colors.length],
    backgroundColor: colors[index % colors.length],
    borderDash: index >= colors.length ? [6, 4] : [],
    borderWidth: 2,
    pointRadius: 2,
    pointHoverRadius: 5,
    // A price stays the same until the next change, so draw steps.
    stepped: true,
  }));

  // dd.mm, the date format used everywhere else on the site.
  const formatDate = (ms) => {
    const date = new Date(ms);
    const two = (number) => String(number).padStart(2, "0");
    return two(date.getDate()) + "." + two(date.getMonth() + 1);
  };
  const formatPrice = (value) => new Intl.NumberFormat("ru-RU").format(value) + " so'm";

  new Chart(canvas, {
    type: "line",
    data: { datasets: datasets },
    options: {
      maintainAspectRatio: false,
      parsing: false,
      interaction: { mode: "nearest", intersect: false },
      scales: {
        x: {
          type: "linear",
          ticks: { callback: (value) => formatDate(value), maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: "so'm" },
          ticks: { callback: (value) => new Intl.NumberFormat("ru-RU").format(value) },
        },
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            title: (items) => formatDate(items[0].parsed.x),
            label: (item) => item.dataset.label + ": " + formatPrice(item.parsed.y),
          },
        },
      },
    },
  });
})();
