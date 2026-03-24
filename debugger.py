import requests
from bs4 import BeautifulSoup

s = requests.Session()
ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://www.koreabaseball.com/Record/Player/Defense/Basic.aspx"
sm = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$smData"
season = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason"

def get_fields(sp):
    f = {}
    for h in sp.find_all("input", {"type": "hidden"}):
        n = h.get("name", "")
        if n: f[n] = h.get("value", "")
    for sel in sp.find_all("select"):
        n = sel.get("name", "")
        if not n: continue
        o = sel.find("option", selected=True)
        if o: f[n] = o.get("value", "")
    return f

def do_post(session, url, soup, target, extra=None):
    fields = get_fields(soup)
    fields["__EVENTTARGET"] = target
    fields["__EVENTARGUMENT"] = ""
    fields["__ASYNCPOST"] = "true"
    fields[sm] = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$udpContent|" + target
    if extra: fields.update(extra)
    return session.post(url, data=fields, headers={**ua, "X-Requested-With":"XMLHttpRequest", "X-MicrosoftAjax":"Delta=true", "Referer":url}, timeout=15).text

def parse_ajax(text):
    marker = "|updatePanel|"
    idx = text.find(marker)
    if idx < 0: return None
    pre = text[:idx]; lp = pre.rfind("|"); length = int(pre[lp+1:])
    after = text[idx+len(marker):]; pp = after.find("|")
    start = idx+len(marker)+pp+1
    html = text[start:start+length]
    hfs = []
    pos = 0
    while True:
        hi = text.find("|hiddenField|", pos)
        if hi < 0: break
        p2 = text[:hi]; lp2 = p2.rfind("|")
        try: vl = int(p2[lp2+1:])
        except: pos = hi+13; continue
        a2 = text[hi+13:]; p3 = a2.find("|"); fn = a2[:p3]
        vs = hi+13+p3+1; fv = text[vs:vs+vl]
        hfs.append((fn, fv)); pos = vs+vl
    hfh = "\n".join(f'<input type="hidden" name="{n}" value="{v}" />' for n,v in hfs)
    return BeautifulSoup(f"<html><body>{html}\n{hfh}</body></html>", "html.parser")

# GET + 연도 2025
r = s.get(url, headers=ua, timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
t = do_post(s, url, soup, season, {season: "2025"})
soup = parse_ajax(t)

# 페이저 확인 함수
def show_pager(sp):
    pager = sp.find("div", class_="paging")
    if not pager: print("  페이저 없음"); return
    for a in pager.find_all("a"):
        aid = a.get("id", "")
        href = a.get("href", "")
        txt = a.text.strip()
        print(f"  id={aid}  text={txt}  href=...{href[-30:] if href else ''}")
    for span in pager.find_all("span"):
        print(f"  [현재페이지] {span.text.strip()}")

print("=== 1페이지 ===")
show_pager(soup)

# 5페이지로 이동
for p in range(2, 6):
    btn = f"ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNo{p}"
    t = do_post(s, url, soup, btn)
    soup = parse_ajax(t)
    
print(f"\n=== 5페이지 ===")
show_pager(soup)

# > 버튼 클릭
btn_next = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNext"
t = do_post(s, url, soup, btn_next)
soup = parse_ajax(t)
print(f"\n=== > 클릭 후 ===")
show_pager(soup)