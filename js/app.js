/* ============================================================
   app.js — 메인 앱 로직
   네비게이션, 테마 토글, 초기화, 이벤트 바인딩
   ============================================================ */

const App = {
  currentPage: 'dashboard',
  /** 선수 검색에서 선택된 이름 (테마·차트 갱신용) */
  selectedPlayerName: null,
  glossaryLoaded: false,
  glossaryPendingTarget: null,

  // --- 초기화 ---
  async init() {
    const success = await DataStore.load();
    if (!success) {
      document.getElementById('summaryCards').innerHTML =
        `<div class="card c1">
          <div class="lb">오류</div>
          <div class="val">데이터 로드 실패</div>
          <div class="sub">database/data.json 파일을 확인하세요</div>
        </div>`;
      return;
    }

    this.setupNav();
    this.setupFilters();
    this.buildSummary();
    Charts.buildEnvChart();
    Charts.buildTopChart();
    Tables.renderEra();
    Tables.renderOps();
    Tables.renderWrc();
    Tables.renderProxyWarBatter();
    Tables.renderProxyWarPitcher();
    Tables.renderParkFactor();
    this.setupPlayerSearch();
    this.setupGlossaryLinks();
    this.setupHeaderHelpLinks();
    await this.setupGlossaryPage();
  },

  // --- 컬럼 헤더 도움말(hover + 클릭 이동) ---
  setupHeaderHelpLinks() {
    const heads = document.querySelectorAll('th.th-help');
    heads.forEach(th => {
      const link = th.getAttribute('data-link');
      if (!link) return;
      th.tabIndex = 0;
      th.setAttribute('role', 'link');
      th.setAttribute('aria-label', `${th.textContent.trim()} 설명 열기`);
      const openGlossary = () => this.openGlossary(link);
      th.addEventListener('click', openGlossary);
      th.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openGlossary();
        }
      });
    });
  },

  // --- 테마 토글 ---
  toggleTheme() {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    document.querySelector('.theme-btn').textContent =
      next === 'dark' ? '☀️ 라이트모드' : '🌙 다크모드';
    Charts.refreshAll();
  },

  // --- 네비게이션 ---
  setupNav() {
    const pages = {
      dashboard: '리그 환경 추이 (1982~2025)',
      era: 'ERA+ 투수 랭킹',
      'war-pit': 'Proxy WAR 투수 랭킹 (수비 제외)',
      ops: 'OPS+ 타자 랭킹',
      wrc: 'wRC+ 타자 랭킹',
      'war-bat': 'Proxy WAR 타자 랭킹 (수비 제외)',
      player: '선수 검색 · 커리어',
      glossary: '지표 설명 가이드',
      pf: '파크팩터 분석',
    };

    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => {
        const pg = item.getAttribute('data-page');
        this.navigateTo(pg, pages[pg]);
      });
    });
  },

  async setupGlossaryPage() {
    const mount = document.getElementById('glossaryMount');
    const status = document.getElementById('filterStatus');
    if (!mount || !status) return;
    try {
      const resp = await fetch('stat_glossary.html');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const html = await resp.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const sections = Array.from(doc.querySelectorAll('.stat-glossary-section'));
      mount.innerHTML = '';
      sections.forEach(sec => mount.appendChild(sec));
      this.glossaryLoaded = true;
      this.setupGlossaryFilters();
      if (this.glossaryPendingTarget) {
        this.scrollToGlossary(this.glossaryPendingTarget);
        this.glossaryPendingTarget = null;
      }
    } catch (e) {
      status.textContent = '지표 설명 데이터를 불러오지 못했습니다.';
      console.error('[Glossary] 로드 실패:', e);
    }
  },

  setupGlossaryFilters() {
    const category = document.getElementById('categoryFilter');
    const keyword = document.getElementById('keywordFilter');
    const reset = document.getElementById('resetFilterBtn');
    const status = document.getElementById('filterStatus');
    const sections = Array.from(document.querySelectorAll('#glossaryMount .stat-glossary-section'));
    if (!category || !keyword || !reset || !status || !sections.length) return;

    const apply = () => {
      const selected = category.value;
      const q = keyword.value.trim().toLowerCase();
      let visibleSectionCount = 0;
      let visibleItemCount = 0;

      sections.forEach(section => {
        const byCategory = selected === 'all' || section.id === selected;
        const items = Array.from(section.querySelectorAll('.stat-glossary-item'));
        let visibleInSection = 0;

        items.forEach(item => {
          const byKeyword = !q || item.textContent.toLowerCase().includes(q);
          const visible = byCategory && byKeyword;
          item.style.display = visible ? '' : 'none';
          if (visible) {
            visibleInSection += 1;
            visibleItemCount += 1;
          }
        });

        section.style.display = visibleInSection > 0 ? '' : 'none';
        if (visibleInSection > 0) visibleSectionCount += 1;
      });

      status.textContent = visibleItemCount === 0
        ? '조건에 맞는 항목이 없습니다. 다른 키워드나 분류를 선택해 주세요.'
        : `${visibleSectionCount}개 분류 · ${visibleItemCount}개 항목을 표시 중입니다.`;
    };

    category.addEventListener('change', apply);
    keyword.addEventListener('input', apply);
    reset.addEventListener('click', () => {
      category.value = 'all';
      keyword.value = '';
      apply();
    });
    apply();
  },

  setupGlossaryLinks() {
    document.querySelectorAll('.js-glossary-link').forEach(el => {
      el.addEventListener('click', () => {
        const target = el.getAttribute('data-glossary-target');
        this.openGlossary(target);
      });
    });
  },

  openGlossary(targetId) {
    this.navigateTo('glossary', '지표 설명 가이드');
    if (!targetId) return;
    if (!this.glossaryLoaded) {
      this.glossaryPendingTarget = targetId;
      return;
    }
    // 외부에서 용어로 이동할 때는 필터를 초기화해 대상이 숨겨지지 않게 한다.
    this.resetGlossaryFilters();
    this.scrollToGlossary(targetId);
  },

  resetGlossaryFilters() {
    const category = document.getElementById('categoryFilter');
    const keyword = document.getElementById('keywordFilter');
    if (!category || !keyword) return;
    let changed = false;
    if (category.value !== 'all') {
      category.value = 'all';
      changed = true;
    }
    if (keyword.value !== '') {
      keyword.value = '';
      changed = true;
    }
    if (!changed) return;
    category.dispatchEvent(new Event('change', { bubbles: true }));
  },

  scrollToGlossary(targetId) {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  navigateTo(page, title) {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelector(`[data-page="${page}"]`).classList.add('active');
    document.querySelectorAll('[id^="pg-"]').forEach(p => p.style.display = 'none');
    document.getElementById('pg-' + page).style.display = '';
    document.getElementById('pageTitle').textContent = title || '';
    this.currentPage = page;
    // 숨겨졌다가 다시 보일 때 캔버스 크기 보정
    if (page === 'player' && this.selectedPlayerName) {
      requestAnimationFrame(() => Charts.buildPlayerCareerChart(this.selectedPlayerName));
    }
  },

  // --- 필터 이벤트 바인딩 ---
  setupFilters() {
    const years = DataStore.getAvailableYears();

    Tables.fillYearSelect('eraYear', years);
    Tables.fillYearSelect('opsYear', years);
    Tables.fillYearSelect('wrcYear', years);
    Tables.fillYearSelect('warBatYear', years);
    Tables.fillYearSelect('warPitYear', years);
    Tables.fillYearSelect('pfYear', years);

    document.getElementById('eraYear').addEventListener('change', () => Tables.renderEra());
    document.getElementById('eraTeam').addEventListener('change', () => Tables.renderEra());
    document.getElementById('opsYear').addEventListener('change', () => Tables.renderOps());
    document.getElementById('opsTeam').addEventListener('change', () => Tables.renderOps());
    document.getElementById('wrcYear').addEventListener('change', () => Tables.renderWrc());
    document.getElementById('wrcTeam').addEventListener('change', () => Tables.renderWrc());
    document.getElementById('warBatYear').addEventListener('change', () => Tables.renderProxyWarBatter());
    document.getElementById('warBatTeam').addEventListener('change', () => Tables.renderProxyWarBatter());
    document.getElementById('warPitYear').addEventListener('change', () => Tables.renderProxyWarPitcher());
    document.getElementById('warPitTeam').addEventListener('change', () => Tables.renderProxyWarPitcher());
    document.getElementById('pfYear').addEventListener('change', () => Tables.renderParkFactor());
  },

  // --- 선수 검색 (부분 일치, 랭킹에 포함된 시즌만) ---
  setupPlayerSearch() {
    const input = document.getElementById('playerSearchInput');
    const ul = document.getElementById('playerSearchResults');
    if (!input || !ul) return;

    ul.addEventListener('click', (e) => {
      const b = e.target.closest('.player-hit');
      if (b) this.selectPlayer(b.textContent.trim());
    });

    let t = null;
    const run = () => {
      const q = input.value;
      const names = DataStore.searchPlayerNames(q, 40);
      ul.innerHTML = names.map(n =>
        `<li><button type="button" class="player-hit">${n}</button></li>`
      ).join('');
    };

    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(run, 180);
    });
    input.addEventListener('focus', run);
  },

  selectPlayer(name) {
    if (!name) return;
    this.selectedPlayerName = name;
    const detail = document.getElementById('playerDetail');
    const title = document.getElementById('playerDetailTitle');
    const input = document.getElementById('playerSearchInput');
    if (title) title.textContent = name;
    if (input) input.value = name;
    if (detail) detail.style.display = '';

    Tables.renderPlayerCareerTable(name);

    const ul = document.getElementById('playerSearchResults');
    if (ul) ul.innerHTML = '';

    this.navigateTo('player', '선수 검색 · 커리어');
  },

  // --- 요약 카드 ---
  buildSummary() {
    const env = DataStore.getLeagueEnv();
    const latest = DataStore.getLatestEnv();
    if (!latest) return;

    const y = latest.year;
    const eraTop = DataStore.getEraTop1(y);
    const opsTop = DataStore.getOpsTop1(y);
    const wrcTop = DataStore.getWrcTop1(y);
    const pfData = DataStore.getParkFactors(y);
    const pfTop = pfData.length > 0 ? pfData[0] : null;

    document.getElementById('summaryCards').innerHTML = `
      <div class="card c4">
        <div class="lb">분석 기간</div>
        <div class="val">${env.length}시즌</div>
        <div class="sub">1982 ~ ${y}</div>
      </div>
      <div class="card c1">
        <div class="lb">${y} 리그 ERA</div>
        <div class="val">${latest.lgERA}</div>
        <div class="sub">ERA+ 1위: ${eraTop ? eraTop.name + ' (' + eraTop.eraPlus + ')' : '-'}</div>
      </div>
      <div class="card c2">
        <div class="lb">${y} 리그 OPS</div>
        <div class="val">${latest.lgOPS}</div>
        <div class="sub">OPS+ 1위: ${opsTop ? opsTop.name + ' (' + opsTop.opsPlus + ')' : '-'}</div>
      </div>
      <div class="card c5">
        <div class="lb">${y} 리그 wOBA</div>
        <div class="val">${latest.lgwOBA != null ? latest.lgwOBA : '-'}</div>
        <div class="sub">wRC+ 1위: ${wrcTop ? wrcTop.name + ' (' + wrcTop.wrcPlus + ')' : '-'}</div>
      </div>
      <div class="card c3">
        <div class="lb">${y} 최고 파크팩터</div>
        <div class="val">${pfTop ? pfTop.pf : '-'}</div>
        <div class="sub">${pfTop ? pfTop.team : '-'}</div>
      </div>
    `;
  },
};

// --- 글로벌 함수 (HTML onclick용) ---
function toggleTheme() { App.toggleTheme(); }

// --- 페이지 로드 시 실행 ---
document.addEventListener('DOMContentLoaded', () => App.init());
