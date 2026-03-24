/* ============================================================
   tables.js — 테이블 렌더링 + 등급 배지
   ERA+ / OPS+ 테이블을 생성하고 등급 색상을 적용
   ============================================================ */

const Tables = {
  fmt(value, digits = 1) {
    return Number.isFinite(value) ? value.toFixed(digits) : '-';
  },

  // --- 등급 배지 생성 ---
  gradeBadge(value) {
    let cls = 'g-av';
    if (value >= 200) cls = 'g-el';
    else if (value >= 150) cls = 'g-gr';
    else if (value >= 120) cls = 'g-ab';
    else if (value < 100) cls = 'g-bl';
    return `<span class="badge ${cls}">${value.toFixed(1)}</span>`;
  },

  // --- 팀 필터 업데이트 ---
  updateTeamFilter(selectId, data) {
    const sel = document.getElementById(selectId);
    const cur = sel.value;
    const teams = [...new Set(data.map(d => d.team))].sort();
    sel.innerHTML = '<option value="all">전체</option>';
    teams.forEach(t => {
      const o = document.createElement('option');
      o.value = t; o.textContent = t;
      sel.appendChild(o);
    });
    sel.value = teams.includes(cur) ? cur : 'all';
  },

  // --- 연도 셀렉트 채우기 ---
  fillYearSelect(selectId, years) {
    const sel = document.getElementById(selectId);
    sel.innerHTML = '';
    years.forEach(y => {
      const o = document.createElement('option');
      o.value = y; o.textContent = y;
      sel.appendChild(o);
    });
  },

  // --- ERA+ 테이블 렌더링 ---
  renderEra() {
    const year = document.getElementById('eraYear').value;
    const team = document.getElementById('eraTeam').value;
    const allData = DataStore.getEraPlus(year);
    this.updateTeamFilter('eraTeam', allData);
    const data = team === 'all' ? allData : allData.filter(d => d.team === team);

    document.getElementById('eraTbody').innerHTML = data.map((p, i) =>
      `<tr>
        <td>${i + 1}</td>
        <td>${p.name}</td>
        <td>${p.team}</td>
        <td>${p.era.toFixed(2)}</td>
        <td>${p.ip}</td>
        <td>${p.w}-${p.l}</td>
        <td>${p.lgERA}</td>
        <td>${p.pf}</td>
        <td>${this.gradeBadge(p.eraPlus)}</td>
      </tr>`
    ).join('');
  },

  // --- wRC+ 테이블 렌더링 ---
  renderWrc() {
    const year = document.getElementById('wrcYear').value;
    const team = document.getElementById('wrcTeam').value;
    const allData = DataStore.getWrcPlus(year);
    this.updateTeamFilter('wrcTeam', allData);
    const data = team === 'all' ? allData : allData.filter(d => d.team === team);

    document.getElementById('wrcTbody').innerHTML = data.map((p, i) =>
      `<tr>
        <td>${i + 1}</td>
        <td>${p.name}</td>
        <td>${p.team}</td>
        <td>${this.fmt(p.avg, 3)}</td>
        <td>${this.fmt(p.obp, 3)}</td>
        <td>${this.fmt(p.slg, 3)}</td>
        <td>${this.fmt(p.ops, 3)}</td>
        <td>${p.pa ?? '-'}</td>
        <td>${p.hr ?? '-'}</td>
        <td>${p.rbi ?? '-'}</td>
        <td>${this.fmt(p.woba, 3)}</td>
        <td>${this.fmt(p.wraa, 1)}</td>
        <td>${p.pf}</td>
        <td>${this.gradeBadge(p.wrcPlus)}</td>
      </tr>`
    ).join('');
  },

  // --- 선수 커리어 표 (검색 상세) ---
  renderPlayerCareerTable(name) {
    const tbody = document.getElementById('playerCareerTbody');
    if (!tbody) return;
    const rows = DataStore.getCareer(name);
    const dash = v => (v != null && v !== '' ? v : '—');
    tbody.innerHTML = rows.map(r =>
      `<tr>
        <td>${r.year}</td>
        <td>${r.team || '—'}</td>
        <td>${dash(r.eraPlus)}</td>
        <td>${dash(r.opsPlus)}</td>
        <td>${dash(r.wrcPlus)}</td>
      </tr>`
    ).join('');
  },

  // --- OPS+ 테이블 렌더링 ---
  renderOps() {
    const year = document.getElementById('opsYear').value;
    const team = document.getElementById('opsTeam').value;
    const allData = DataStore.getOpsPlus(year);
    this.updateTeamFilter('opsTeam', allData);
    const data = team === 'all' ? allData : allData.filter(d => d.team === team);

    document.getElementById('opsTbody').innerHTML = data.map((p, i) =>
      `<tr>
        <td>${i + 1}</td>
        <td>${p.name}</td>
        <td>${p.team}</td>
        <td>${p.avg.toFixed(3)}</td>
        <td>${p.obp.toFixed(3)}</td>
        <td>${p.slg.toFixed(3)}</td>
        <td>${p.ops.toFixed(3)}</td>
        <td>${p.hr}</td>
        <td>${p.rbi}</td>
        <td>${p.pf}</td>
        <td>${this.gradeBadge(p.opsPlus)}</td>
      </tr>`
    ).join('');
  },

  // --- Proxy WAR(타자) 테이블 렌더링 ---
  renderProxyWarBatter() {
    const year = document.getElementById('warBatYear').value;
    const team = document.getElementById('warBatTeam').value;
    const allData = DataStore.getProxyWarBatter(year);
    this.updateTeamFilter('warBatTeam', allData);
    const data = team === 'all' ? allData : allData.filter(d => d.team === team);

    document.getElementById('warBatTbody').innerHTML = data.map((p, i) =>
      `<tr>
        <td>${i + 1}</td>
        <td>${p.name}</td>
        <td>${p.team}</td>
        <td>${this.fmt(p.proxyWar, 1)}</td>
        <td>${this.fmt(p.woba, 3)}</td>
        <td>${this.fmt(p.battingRuns, 1)}</td>
        <td>${this.fmt(p.wsb, 1)}</td>
        <td>${this.fmt(p.posAdj, 1)}</td>
        <td>${this.fmt(p.ops, 3)}</td>
      </tr>`
    ).join('');
  },

  // --- Proxy WAR(투수) 테이블 렌더링 ---
  renderProxyWarPitcher() {
    const year = document.getElementById('warPitYear').value;
    const team = document.getElementById('warPitTeam').value;
    const allData = DataStore.getProxyWarPitcher(year);
    this.updateTeamFilter('warPitTeam', allData);
    const data = team === 'all' ? allData : allData.filter(d => d.team === team);

    document.getElementById('warPitTbody').innerHTML = data.map((p, i) =>
      `<tr>
        <td>${i + 1}</td>
        <td>${p.name}</td>
        <td>${p.team}</td>
        <td>${p.role ?? '-'}</td>
        <td>${this.fmt(p.proxyWar, 1)}</td>
        <td>${this.fmt(p.era, 2)}</td>
        <td>${this.fmt(p.ra9, 2)}</td>
        <td>${this.fmt(p.ip, 1)}</td>
        <td>${(p.w ?? '-')}-${(p.l ?? '-')}</td>
      </tr>`
    ).join('');
  },

  // --- 파크팩터 바 렌더링 ---
  renderParkFactor() {
    const year = document.getElementById('pfYear').value;
    const data = DataStore.getParkFactors(year);

    if (!data.length) {
      document.getElementById('pfBars').innerHTML =
        '<div style="color:var(--text-sub);font-size:13px;padding:1rem;">해당 연도 파크팩터 데이터 없음</div>';
      return;
    }

    const maxDev = Math.max(...data.map(d => Math.abs(d.pf - 100)), 20);

    document.getElementById('pfBars').innerHTML = data.map(d => {
      const dev = d.pf - 100;
      const pct = Math.abs(dev) / maxDev * 40;
      let clr;
      if (d.pf >= 115) clr = '#B2182B';
      else if (d.pf >= 105) clr = '#EF8A62';
      else if (d.pf > 95) clr = '#999';
      else if (d.pf >= 85) clr = '#67A9CF';
      else clr = '#2166AC';

      const bar = `<div class="pf-bar" style="width:${pct}%;background:${clr};"></div>`;
      const val = `<div class="pf-val" style="color:${clr};">${d.pf}</div>`;

      if (dev >= 0) {
        return `<div class="pf-row">
          <div class="pf-name">${d.team}</div>
          <div style="width:40%;"></div>
          <div class="pf-center" style="height:18px;"></div>
          <div style="width:40%;display:flex;">${bar}</div>
          ${val}
        </div>`;
      } else {
        return `<div class="pf-row">
          <div class="pf-name">${d.team}</div>
          <div style="width:40%;display:flex;justify-content:flex-end;">${bar}</div>
          <div class="pf-center" style="height:18px;"></div>
          <div style="width:40%;"></div>
          ${val}
        </div>`;
      }
    }).join('');
  },
};
