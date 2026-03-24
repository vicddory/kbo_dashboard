"""
generate_data.py — DB + 파크팩터 엑셀 → database/data.json 생성
ERA+, OPS+, wRC+, Proxy WAR 전 지표 포함

사용법:
    python generate_data.py

필요 파일 (같은 폴더에):
    - kbo_data.db
    - kbo_statiz_data_1982_1998_.xlsx ~ 2022_2024_.xlsx
    - era_plus.py, ops_plus.py, wrc_plus.py, proxy_war.py

출력:
    database/data.json
"""

import json
import os
import sys

from era_plus import load_park_factors, calculate_era_plus
from ops_plus import calculate_ops_plus
from wrc_plus import calculate_wrc_plus_all
from proxy_war import calculate_proxy_war_all

PF_FILES = [
    'kbo_statiz_data_1982_1998_.xlsx',
    'kbo_statiz_data_1999_2009_.xlsx',
    'kbo_statiz_data_2010_2021_.xlsx',
    'kbo_statiz_data_2022_2024_.xlsx',
]

DB_PATH = 'kbo_data.db'
OUTPUT_PATH = 'database/data.json'


def main():
    print('[1/5] 파크팩터 로드...')
    pf_data = load_park_factors(PF_FILES)

    print('[2/5] ERA+ 계산...')
    era_results = calculate_era_plus(DB_PATH, pf_data)

    print('[3/5] OPS+ 계산...')
    ops_results = calculate_ops_plus(DB_PATH, pf_data)

    print('[4/5] wRC+ 계산...')
    wrc_results = calculate_wrc_plus_all(DB_PATH, pf_data)

    print('[5/5] Proxy WAR 계산...')
    war_results = calculate_proxy_war_all(DB_PATH, pf_data)

    output = {
        'league_env': [],
        'era_plus': {},
        'ops_plus': {},
        'wrc_plus': {},
        'proxy_war_batter': {},
        'proxy_war_pitcher': {},
        'park_factors': {},
    }

    for year in range(1982, 2030):
        has_era = year in era_results and era_results[year]
        has_ops = year in ops_results and ops_results[year]
        has_wrc = year in wrc_results and wrc_results[year]

        if has_era and has_ops:
            lg_era = era_results[year][0]['lgERA']
            lg_obp = ops_results[year][0]['lgOBP']
            lg_slg = ops_results[year][0]['lgSLG']
            env = {
                'year': year, 'lgERA': lg_era,
                'lgOBP': lg_obp, 'lgSLG': lg_slg,
                'lgOPS': round(lg_obp + lg_slg, 3),
            }
            if has_wrc:
                env['lgwOBA'] = wrc_results[year][0]['lgwOBA']
                env['lgRperPA'] = wrc_results[year][0]['lgR/PA']
            output['league_env'].append(env)

        if has_era:
            output['era_plus'][str(year)] = [
                {'name': p['선수명'], 'team': p['팀명'], 'era': p['ERA'],
                 'ip': p['IP'], 'w': p['W'], 'l': p['L'],
                 'lgERA': p['lgERA'], 'pf': p['PF'], 'eraPlus': p['ERA+']}
                for p in era_results[year][:20]
            ]

        if has_ops:
            output['ops_plus'][str(year)] = [
                {'name': p['선수명'], 'team': p['팀명'], 'avg': p['AVG'],
                 'obp': p['OBP'], 'slg': p['SLG'], 'ops': p['OPS'],
                 'hr': p['HR'], 'rbi': p['RBI'], 'lgOBP': p['lgOBP'],
                 'lgSLG': p['lgSLG'], 'pf': p['PF'], 'opsPlus': p['OPS+']}
                for p in ops_results[year][:20]
            ]

        if has_wrc:
            output['wrc_plus'][str(year)] = [
                {'name': p['선수명'], 'team': p['팀명'], 'avg': p['AVG'],
                 'obp': p['OBP'], 'slg': p['SLG'], 'ops': p['OPS'],
                 'pa': p['PA'], 'hr': p['HR'], 'rbi': p['RBI'],
                 'woba': p['wOBA'], 'wraa': p['wRAA'],
                 'pf': p['PF'], 'wrcPlus': p['wRC+']}
                for p in wrc_results[year][:20]
            ]

        if year in war_results['batter']:
            output['proxy_war_batter'][str(year)] = [
                {'name': p['선수명'], 'team': p['팀명'],
                 'pa': p['PA'], 'avg': p['AVG'], 'ops': p['OPS'],
                 'woba': p['wOBA'], 'wraa': p['wRAA'],
                 'battingRuns': p['BattingRuns'], 'wsb': p['wSB'],
                 'posAdj': p['PosAdj'], 'pf': p['PF'],
                 'proxyWar': p['ProxyWAR']}
                for p in war_results['batter'][year][:20]
            ]

        if year in war_results['pitcher']:
            output['proxy_war_pitcher'][str(year)] = [
                {'name': p['선수명'], 'team': p['팀명'],
                 'role': p['Role'], 'ip': p['IP'], 'era': p['ERA'],
                 'ra9': p['RA9'], 'w': p['W'], 'l': p['L'],
                 'sv': p['SV'], 'hld': p['HLD'], 'so': p['SO'],
                 'pf': p['PF'], 'proxyWar': p['ProxyWAR']}
                for p in war_results['pitcher'][year][:20]
            ]

        if year in pf_data:
            output['park_factors'][str(year)] = [
                {'team': t, 'pf': round(v, 1)}
                for t, v in sorted(pf_data[year].items(), key=lambda x: -x[1])
            ]

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f'\n완료: {OUTPUT_PATH} ({size_kb:.1f} KB)')
    print(f'  league_env: {len(output["league_env"])}시즌')
    print(f'  era_plus: {len(output["era_plus"])}시즌')
    print(f'  ops_plus: {len(output["ops_plus"])}시즌')
    print(f'  wrc_plus: {len(output["wrc_plus"])}시즌')
    print(f'  proxy_war_batter: {len(output["proxy_war_batter"])}시즌')
    print(f'  proxy_war_pitcher: {len(output["proxy_war_pitcher"])}시즌')
    print(f'  park_factors: {len(output["park_factors"])}시즌')


if __name__ == '__main__':
    main()
