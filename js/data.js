/* ============================================================
   data.js — 데이터 로딩 및 필터링
   database/data.json을 로드하고 각 모듈에서 사용할 수 있도록 제공
   ============================================================ */

const KBO_GAMES_BY_YEAR = {
  1982: 80,
  1983: 100, 1984: 100,
  1985: 110,
  1986: 108, 1987: 108, 1988: 108,
  1989: 120, 1990: 120,
  1991: 126, 1992: 126, 1993: 126, 1994: 126, 1995: 126, 1996: 126, 1997: 126, 1998: 126,
  1999: 132,
  2000: 133, 2001: 133, 2002: 133, 2003: 133, 2004: 133,
  2005: 126, 2006: 126, 2007: 126, 2008: 126,
  2009: 133, 2010: 133, 2011: 133, 2012: 133,
  2013: 128, 2014: 128,
  2015: 144, 2016: 144, 2017: 144, 2018: 144, 2019: 144,
  2020: 144, 2021: 144, 2022: 144, 2023: 144, 2024: 144, 2025: 144,
};

const DataStore = {
  raw: null,
  loaded: false,
  /** 이름 → 연도별 기록 배열 (연도 오름차순), 랭킹 JSON에 나온 시즌만 포함 */
  careerByName: null,

  async load() {
    try {
      const resp = await fetch('database/data.json');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.raw = await resp.json();
      this._buildCareerIndex();
      this.loaded = true;
      console.log('[DataStore] 로드 완료:', {
        years: this.raw.league_env.length,
        eraYears: Object.keys(this.raw.era_plus).length,
        opsYears: Object.keys(this.raw.ops_plus).length,
        wrcYears: Object.keys(this.raw.wrc_plus || {}).length,
        warBatYears: Object.keys(this.raw.proxy_war_batter || {}).length,
        warPitYears: Object.keys(this.raw.proxy_war_pitcher || {}).length,
        pfYears: Object.keys(this.raw.park_factors).length,
        players: this.careerByName ? Object.keys(this.careerByName).length : 0,
      });
      return true;
    } catch (e) {
      console.error('[DataStore] 로드 실패:', e);
      return false;
    }
  },

  // --- League Environment ---
  getLeagueEnv() {
    return this.raw?.league_env || [];
  },

  getLatestEnv() {
    const env = this.getLeagueEnv();
    return env.length > 0 ? env[env.length - 1] : null;
  },

  // --- ERA+ ---
  getEraPlus(year, team = 'all') {
    const data = this.raw?.era_plus?.[String(year)] || [];
    if (team === 'all') return data;
    return data.filter(d => d.team === team);
  },

  getEraTop1(year) {
    const data = this.raw?.era_plus?.[String(year)];
    return data && data.length > 0 ? data[0] : null;
  },

  // --- OPS+ ---
  getOpsPlus(year, team = 'all') {
    const data = this.raw?.ops_plus?.[String(year)] || [];
    if (team === 'all') return data;
    return data.filter(d => d.team === team);
  },

  getOpsTop1(year) {
    const data = this.raw?.ops_plus?.[String(year)];
    return data && data.length > 0 ? data[0] : null;
  },

  // --- wRC+ ---
  getWrcPlus(year, team = 'all') {
    const data = this.raw?.wrc_plus?.[String(year)] || [];
    if (team === 'all') return data;
    return data.filter(d => d.team === team);
  },

  getWrcTop1(year) {
    const data = this.raw?.wrc_plus?.[String(year)];
    return data && data.length > 0 ? data[0] : null;
  },

  // --- 표시 전용 규정타석/규정이닝 필터 ---
  // 시즌별 팀 경기 수 기준(정확값)으로 규정타석/규정이닝을 계산
  getQualificationThreshold(year) {
    const y = Number(year);
    const games = KBO_GAMES_BY_YEAR[y] || 144;
    return {
      paMin: games * 3.1, // 규정타석
      ipMin: games * 1.0, // 규정이닝
      games,
    };
  },

  // 문자열 분수 이닝("262 2/3")까지 정확하게 숫자로 변환
  parseIp(ip) {
    if (ip == null) return 0;
    if (typeof ip === 'number') return Number.isFinite(ip) ? ip : 0;

    const s = String(ip).trim();
    if (!s) return 0;

    const asNum = Number(s);
    if (Number.isFinite(asNum)) return asNum;

    const m = s.match(/^(\d+)\s+(\d+)\s*\/\s*(\d+)$/);
    if (m) {
      const whole = Number(m[1]);
      const num = Number(m[2]);
      const den = Number(m[3]);
      if (den > 0) return whole + (num / den);
    }
    return 0;
  },

  // PA가 문자열로 들어와도 안전하게 숫자로 변환
  parsePa(pa) {
    const n = Number(pa);
    return Number.isFinite(n) ? n : 0;
  },

  getQualifiedWrcTop1(year) {
    const y = String(year);
    const data = this.raw?.wrc_plus?.[y] || [];
    const { paMin } = this.getQualificationThreshold(y);
    const qualified = data.filter(p => this.parsePa(p.pa) >= paMin);
    return (qualified.length ? qualified : data)[0] || null;
  },

  getQualifiedOpsTop1(year) {
    const y = String(year);
    const ops = this.raw?.ops_plus?.[y] || [];
    const wrc = this.raw?.wrc_plus?.[y] || [];
    const { paMin } = this.getQualificationThreshold(y);

    // ops_plus에는 PA가 없어서 같은 시즌(name+team) wrc_plus의 PA를 매핑해 규정타석을 판정
    const paByKey = new Map(wrc.map(p => [`${p.name}|${p.team}`, this.parsePa(p.pa)]));
    const qualified = ops.filter(p => {
      const pa = paByKey.get(`${p.name}|${p.team}`) || 0;
      return pa >= paMin;
    });
    return (qualified.length ? qualified : ops)[0] || null;
  },

  getQualifiedEraTop1(year) {
    const y = String(year);
    const data = this.raw?.era_plus?.[y] || [];
    const { ipMin } = this.getQualificationThreshold(y);
    const qualified = data.filter(p => this.parseIp(p.ip) >= ipMin);
    return (qualified.length ? qualified : data)[0] || null;
  },

  // --- Proxy WAR (타자/투수) ---
  getProxyWarBatter(year, team = 'all') {
    const data = this.raw?.proxy_war_batter?.[String(year)] || [];
    if (team === 'all') return data;
    return data.filter(d => d.team === team);
  },

  getProxyWarPitcher(year, team = 'all') {
    const data = this.raw?.proxy_war_pitcher?.[String(year)] || [];
    if (team === 'all') return data;
    return data.filter(d => d.team === team);
  },

  // --- Park Factors ---
  getParkFactors(year) {
    return this.raw?.park_factors?.[String(year)] || [];
  },

  // --- FA 적정가 ---
  getFaContracts(year, query = '') {
    const data = this.raw?.fa_contracts?.[String(year)] || [];
    const q = String(query || '').trim();
    if (!q) return data;
    return data.filter(d => String(d.name || '').includes(q));
  },

  getFaYears() {
    const years = Object.keys(this.raw?.fa_contracts || {});
    return years.sort((a, b) => b - a);
  },

  getFaMarketStats() {
    return this.raw?.fa_market_stats || null;
  },

  // --- Utility ---
  getAvailableYears() {
    const keys = new Set([
      ...Object.keys(this.raw?.era_plus || {}),
      ...Object.keys(this.raw?.ops_plus || {}),
      ...Object.keys(this.raw?.wrc_plus || {}),
      ...Object.keys(this.raw?.proxy_war_batter || {}),
      ...Object.keys(this.raw?.proxy_war_pitcher || {}),
      ...Object.keys(this.raw?.park_factors || {}),
    ]);
    return [...keys].sort((a, b) => b - a);
  },

  getTeamsForYear(year) {
    const era = this.raw?.era_plus?.[String(year)] || [];
    const wrc = this.raw?.wrc_plus?.[String(year)] || [];
    const warBat = this.raw?.proxy_war_batter?.[String(year)] || [];
    const warPit = this.raw?.proxy_war_pitcher?.[String(year)] || [];
    return [
      ...new Set([
        ...era.map(d => d.team),
        ...wrc.map(d => d.team),
        ...warBat.map(d => d.team),
        ...warPit.map(d => d.team),
      ]),
    ].sort();
  },

  // --- 선수 커리어 (랭킹에 포함된 시즌만) ---
  _buildCareerIndex() {
    this.careerByName = Object.create(null);
    const add = (name, yearStr, team, patch) => {
      const key = String(name).trim();
      if (!key) return;
      if (!this.careerByName[key]) this.careerByName[key] = [];
      const arr = this.careerByName[key];
      const y = Number(yearStr);
      let row = arr.find(r => r.year === y);
      if (!row) {
        row = { year: y, team: team || '' };
        arr.push(row);
      }
      if (team) row.team = team;
      Object.assign(row, patch);
    };

    const raw = this.raw;
    for (const y of Object.keys(raw.era_plus || {})) {
      for (const p of raw.era_plus[y] || []) {
        add(p.name, y, p.team, { eraPlus: p.eraPlus, era: p.era });
      }
    }
    for (const y of Object.keys(raw.ops_plus || {})) {
      for (const p of raw.ops_plus[y] || []) {
        add(p.name, y, p.team, { opsPlus: p.opsPlus, ops: p.ops });
      }
    }
    for (const y of Object.keys(raw.wrc_plus || {})) {
      for (const p of raw.wrc_plus[y] || []) {
        add(p.name, y, p.team, { wrcPlus: p.wrcPlus, woba: p.woba });
      }
    }
    for (const k of Object.keys(this.careerByName)) {
      this.careerByName[k].sort((a, b) => a.year - b.year);
    }
  },

  /** 이름이 부분 일치하는 선수명 목록 (가나다순, 최대 limit) */
  searchPlayerNames(query, limit = 40) {
    const q = String(query).trim();
    if (!q || !this.careerByName) return [];
    const keys = Object.keys(this.careerByName);
    const m = keys.filter(k => k.includes(q));
    m.sort((a, b) => a.localeCompare(b, 'ko'));
    return m.slice(0, limit);
  },

  getCareer(name) {
    const key = String(name).trim();
    if (!this.careerByName || !key) return [];
    return this.careerByName[key] ? [...this.careerByName[key]] : [];
  },
};
