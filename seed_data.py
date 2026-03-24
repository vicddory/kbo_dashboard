"""
seed_data.py — DB 없이 대시보드 동작 확인용 database/data.json 생성
실제 수치는 kbo_data.db + generate_data.py 로 교체하면 됨 (스키마 동일)
"""
import json
import os
import random

from wrc_plus import wrc_plus_single

random.seed(42)

TEAMS = ['삼성', 'LG', 'KT', 'SSG', 'NC', '두산', '한화', '키움', '롯데', 'KIA']
FAMILY = ['김', '이', '박', '최', '정', '강', '조', '윤']
GIVEN = ['민준', '서준', '도윤', '예준', '시우', '하준', '주원', '지호', '승우', '건우']


def rand_player_name():
    return random.choice(FAMILY) + random.choice(GIVEN)


def fake_ip():
    """KBO 형식 이닝 문자열"""
    whole = random.randint(100, 220)
    frac = random.choice([0, 1, 2])
    if frac == 0:
        return str(whole)
    return f"{whole} {frac}/3"


def build_era_row(year, rank, lg_era):
    team = random.choice(TEAMS)
    era = round(lg_era * random.uniform(0.55, 0.95) - rank * 0.08, 2)
    era = max(0.8, era)
    pf = round(random.uniform(88, 112), 1)
    era_plus = round(100 * (lg_era / era) * (pf / 100), 1)
    return {
        'name': rand_player_name(),
        'team': team,
        'era': era,
        'ip': fake_ip(),
        'w': random.randint(8, 18),
        'l': random.randint(0, 12),
        'lgERA': lg_era,
        'pf': pf,
        'eraPlus': era_plus,
    }


def build_ops_row(year, rank, lg_obp, lg_slg):
    team = random.choice(TEAMS)
    obp = round(lg_obp * random.uniform(1.05, 1.25) - rank * 0.004, 3)
    slg = round(lg_slg * random.uniform(1.08, 1.35) - rank * 0.008, 3)
    ops = round(obp + slg, 3)
    avg = round(obp * random.uniform(0.78, 0.92), 3)
    pf = round(random.uniform(88, 112), 1)
    ops_plus = round(100 * (obp / lg_obp + slg / lg_slg - 1) / (pf / 100), 1)
    return {
        'name': rand_player_name(),
        'team': team,
        'avg': avg,
        'obp': obp,
        'slg': slg,
        'ops': ops,
        'hr': random.randint(12, 42),
        'rbi': random.randint(45, 110),
        'lgOBP': lg_obp,
        'lgSLG': lg_slg,
        'pf': pf,
        'opsPlus': ops_plus,
    }


def build_wrc_row(rank, lg_woba: float, lg_r_per_pa: float, pf_by_team: dict[str, float]):
    """Basic wOBA·wRC+ 공식으로 시드 랭킹 (타자 카운팅은 생략하고 wOBA 직접 샘플)."""
    team = random.choice(TEAMS)
    pf = pf_by_team[team]
    pa = random.randint(480, 600)
    woba = lg_woba + random.uniform(0.015, 0.11) - rank * 0.004
    woba = max(0.26, min(0.48, woba))
    wrc_p = wrc_plus_single(woba, float(pa), lg_woba, lg_r_per_pa, pf)
    return {
        'name': rand_player_name(),
        'team': team,
        'pa': pa,
        'woba': round(woba, 3),
        'lgWOBA': round(lg_woba, 3),
        'lgRperPA': round(lg_r_per_pa, 4),
        'pf': pf,
        'wrcPlus': round(wrc_p, 1),
    }


def main():
    out = {
        'league_env': [],
        'era_plus': {},
        'ops_plus': {},
        'wrc_plus': {},
        'park_factors': {},
    }

    for year in range(1982, 2026):
        t = (year - 1982) / 43
        lg_era = round(3.85 + 0.9 * (0.5 - abs(t - 0.35)) + random.uniform(-0.15, 0.15), 2)
        lg_obp = round(0.325 + 0.02 * t + random.uniform(-0.008, 0.008), 3)
        lg_slg = round(0.385 + 0.035 * t + random.uniform(-0.01, 0.01), 3)
        lg_ops = round(lg_obp + lg_slg, 3)
        lg_woba = round(0.308 + 0.018 * t + random.uniform(-0.006, 0.006), 3)
        lg_r_per_pa = round(0.112 + 0.012 * t + random.uniform(-0.004, 0.004), 4)

        out['league_env'].append({
            'year': year,
            'lgERA': lg_era,
            'lgOBP': lg_obp,
            'lgSLG': lg_slg,
            'lgOPS': lg_ops,
            'lgWOBA': lg_woba,
            'lgRperPA': lg_r_per_pa,
        })

        era_list = [build_era_row(year, r, lg_era) for r in range(20)]
        era_list.sort(key=lambda x: -x['eraPlus'])
        ops_list = [build_ops_row(year, r, lg_obp, lg_slg) for r in range(20)]
        ops_list.sort(key=lambda x: -x['opsPlus'])

        pf_by_team = {team: round(random.uniform(86, 118), 1) for team in TEAMS}
        out['park_factors'][str(year)] = [
            {'team': tm, 'pf': pf_by_team[tm]}
            for tm in sorted(pf_by_team.keys(), key=lambda x: -pf_by_team[x])
        ]

        wrc_list = [build_wrc_row(r, lg_woba, lg_r_per_pa, pf_by_team) for r in range(20)]
        wrc_list.sort(key=lambda x: -x['wrcPlus'])

        # 데모: 동일 선수명으로 연도별 커리어 곡선(선수 검색) 확인용 — 1위 자리에 고정 이름
        era_list[0]['name'] = '커리어샘플투수'
        ops_list[0]['name'] = '커리어샘플'
        wrc_list[0]['name'] = '커리어샘플'

        out['era_plus'][str(year)] = era_list
        out['ops_plus'][str(year)] = ops_list
        out['wrc_plus'][str(year)] = wrc_list

    os.makedirs('database', exist_ok=True)
    path = os.path.join('database', 'data.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    kb = os.path.getsize(path) / 1024
    print(f'생성 완료: {path} ({kb:.1f} KB)')
    print('※ 실제 KBO 수치가 필요하면 kbo_data.db와 엑셀을 두고 python generate_data.py 실행')


if __name__ == '__main__':
    main()
