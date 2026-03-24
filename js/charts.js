/* ============================================================
   charts.js — Chart.js 차트 렌더링
   리그 환경 추이, ERA+/OPS+ 1위 바차트
   ============================================================ */

const Charts = {
  envChart: null,
  topChart: null,
  playerCareerChart: null,

  // --- 테마별 공통 옵션 ---
  themeOpts() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
      isDark,
      grid: isDark ? 'rgba(255,255,255,.06)' : 'rgba(0,0,0,.06)',
      tick: isDark ? 'rgba(255,255,255,.5)' : 'rgba(0,0,0,.45)',
    };
  },

  // --- 리그 환경 추이 (ERA + OPS 이중 축) ---
  buildEnvChart() {
    const ctx = document.getElementById('envChart');
    const t = this.themeOpts();
    const env = DataStore.getLeagueEnv();

    if (this.envChart) this.envChart.destroy();

    this.envChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: env.map(d => d.year),
        datasets: [
          {
            label: '리그 ERA',
            data: env.map(d => d.lgERA),
            borderColor: '#2166AC',
            backgroundColor: 'rgba(33,102,172,.08)',
            fill: true,
            tension: .3,
            pointRadius: 2,
            pointHoverRadius: 5,
            borderWidth: 2,
            yAxisID: 'y',
          },
          {
            label: '리그 OPS',
            data: env.map(d => d.lgOPS),
            borderColor: '#D6604D',
            backgroundColor: 'rgba(214,96,77,.08)',
            fill: true,
            tension: .3,
            pointRadius: 2,
            pointHoverRadius: 5,
            borderWidth: 2,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: ctx => ctx[0].label + '시즌',
            },
          },
        },
        scales: {
          x: {
            ticks: { color: t.tick, maxRotation: 45, autoSkip: true, maxTicksLimit: 15 },
            grid: { display: false },
          },
          y: {
            position: 'left',
            title: { display: true, text: 'ERA', color: '#2166AC', font: { size: 11 } },
            ticks: { color: '#2166AC' },
            grid: { color: t.grid },
            min: 2.5, max: 5.5,
          },
          y1: {
            position: 'right',
            title: { display: true, text: 'OPS', color: '#D6604D', font: { size: 11 } },
            ticks: { color: '#D6604D' },
            grid: { drawOnChartArea: false },
            min: .65, max: .85,
          },
        },
      },
    });
  },

  // --- 연도별 ERA+/OPS+/wRC+ 1위 바차트 ---
  buildTopChart() {
    const ctx = document.getElementById('topChart');
    const t = this.themeOpts();
    const years = DataStore.getLeagueEnv().map(d => d.year);

    const eraVals = years.map(y => {
      const top = DataStore.getQualifiedEraTop1(y);
      return top ? top.eraPlus : 0;
    });
    const opsVals = years.map(y => {
      const top = DataStore.getQualifiedOpsTop1(y);
      return top ? top.opsPlus : 0;
    });
    const wrcVals = years.map(y => {
      const top = DataStore.getQualifiedWrcTop1(y);
      return top ? top.wrcPlus : 0;
    });

    if (this.topChart) this.topChart.destroy();

    this.topChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: years,
        datasets: [
          {
            label: 'ERA+ 1위',
            data: eraVals,
            backgroundColor: 'rgba(67,147,195,.7)',
            borderRadius: 2,
          },
          {
            label: 'OPS+ 1위',
            data: opsVals,
            backgroundColor: 'rgba(244,165,130,.7)',
            borderRadius: 2,
          },
          {
            label: 'wRC+ 1위',
            data: wrcVals,
            backgroundColor: 'rgba(77,175,74,.75)',
            borderRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { color: t.tick, boxWidth: 12, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              title: ctx => ctx[0].label + '시즌',
              label: ctx => {
                const y = years[ctx.dataIndex];
                if (ctx.datasetIndex === 0) {
                  const d = DataStore.getQualifiedEraTop1(y);
                  return d ? `ERA+ ${Math.round(d.eraPlus)} ${d.name}(${d.team}) ERA ${d.era}` : '';
                }
                if (ctx.datasetIndex === 1) {
                  const d = DataStore.getQualifiedOpsTop1(y);
                  return d ? `OPS+ ${Math.round(d.opsPlus)} ${d.name}(${d.team}) OPS ${d.ops}` : '';
                }
                const d = DataStore.getQualifiedWrcTop1(y);
                return d ? `wRC+ ${Math.round(d.wrcPlus)} ${d.name}(${d.team}) wOBA ${d.woba}` : '';
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { color: t.tick, maxRotation: 45, autoSkip: true, maxTicksLimit: 15 },
            grid: { display: false },
          },
          y: {
            ticks: { color: t.tick },
            grid: { color: t.grid },
          },
        },
      },
    });
  },

  // --- 선수 커리어 (ERA+ / OPS+ / wRC+ 라인, 이중 축) ---
  buildPlayerCareerChart(name) {
    const canvas = document.getElementById('playerCareerChart');
    if (!canvas) return;

    if (this.playerCareerChart) {
      this.playerCareerChart.destroy();
      this.playerCareerChart = null;
    }

    const career = DataStore.getCareer(name);
    if (!career.length) return;

    const t = this.themeOpts();
    const years = career.map(c => c.year);
    const eraData = career.map(c => (c.eraPlus != null ? c.eraPlus : null));
    const opsData = career.map(c => (c.opsPlus != null ? c.opsPlus : null));
    const wrcData = career.map(c => (c.wrcPlus != null ? c.wrcPlus : null));
    const hasEra = eraData.some(v => v != null);
    const hasBat = opsData.some(v => v != null) || wrcData.some(v => v != null);

    const batAxis = hasEra ? 'y1' : 'y';
    const datasets = [];
    if (hasEra) {
      datasets.push({
        label: 'ERA+',
        data: eraData,
        borderColor: '#4393C3',
        backgroundColor: 'rgba(67,147,195,.12)',
        tension: 0.25,
        pointRadius: 3,
        spanGaps: true,
        yAxisID: 'y',
        borderWidth: 2,
      });
    }
    if (hasBat) {
      datasets.push({
        label: 'OPS+',
        data: opsData,
        borderColor: '#D6604D',
        backgroundColor: 'rgba(214,96,77,.08)',
        tension: 0.25,
        pointRadius: 3,
        spanGaps: true,
        yAxisID: batAxis,
        borderWidth: 2,
      });
      datasets.push({
        label: 'wRC+',
        data: wrcData,
        borderColor: '#4DAF4A',
        backgroundColor: 'rgba(77,175,74,.08)',
        tension: 0.25,
        pointRadius: 3,
        spanGaps: true,
        yAxisID: batAxis,
        borderWidth: 2,
      });
    }

    if (!datasets.length) return;

    const scales = {
      x: {
        ticks: { color: t.tick, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 },
        grid: { color: t.grid },
      },
    };

    if (hasEra && hasBat) {
      scales.y = {
        position: 'left',
        title: { display: true, text: 'ERA+', color: '#4393C3', font: { size: 11 } },
        ticks: { color: '#4393C3' },
        grid: { color: t.grid },
      };
      scales.y1 = {
        position: 'right',
        title: { display: true, text: 'OPS+ / wRC+', color: '#D6604D', font: { size: 11 } },
        ticks: { color: t.tick },
        grid: { drawOnChartArea: false },
      };
    } else {
      scales.y = {
        title: {
          display: true,
          text: hasEra ? 'ERA+' : 'OPS+ / wRC+',
          color: hasEra ? '#4393C3' : '#D6604D',
          font: { size: 11 },
        },
        ticks: { color: t.tick },
        grid: { color: t.grid },
      };
    }

    this.playerCareerChart = new Chart(canvas, {
      type: 'line',
      data: { labels: years, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { color: t.tick, boxWidth: 12, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              title: ctx => ctx[0].label + '시즌',
            },
          },
        },
        scales,
      },
    });
  },

  // --- 테마 변경 시 차트 재생성 ---
  refreshAll() {
    this.buildEnvChart();
    this.buildTopChart();
    if (typeof App !== 'undefined' && App.selectedPlayerName) {
      this.buildPlayerCareerChart(App.selectedPlayerName);
    }
  },
};
