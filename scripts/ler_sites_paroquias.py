"""Baixa as páginas relevantes (comunidades, capelas, horários, contato) do site de cada paróquia.
Uso: python scripts/ler_sites_paroquias.py  -> dados/arquidiocese/sites/<paróquia>.json (url -> texto)"""
import html, json, re, sys, time, urllib.parse, urllib.request
from collections import deque
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
D = RAIZ / "dados" / "arquidiocese"
OUT = D / "sites"; OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; mapa-paroquias/0.3)"}
CHAVES = re.compile(r"comunidad|capela|igreja|horari|missa|contato|endere|localiza|paroquia|par[oó]quia|sobre|nossa|santuario|matriz|celebra", re.I)
EVITA = re.compile(r"\.(jpg|jpeg|png|gif|pdf|zip|mp3|mp4|webp|svg|ico|css|js)(\?|$)|wp-json|/feed|/tag/|/author/|/page/\d|\?replytocom|#|/noticia|/blog|/evento|/categoria|/category/|/20\d\d/", re.I)

def baixa(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25)
        if "text/html" not in r.headers.get("Content-Type", ""): return None, url
        return r.read(3_000_000).decode("utf-8", "replace"), r.geturl()
    except Exception as e:
        return None, url

def texto(s):
    s = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>|</tr>|</td>", "\n", s, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return "\n".join(re.sub(r"[ \t\xa0]+", " ", l).strip() for l in t.splitlines() if l.strip())

redes = json.loads((D / "redes.json").read_text(encoding="utf-8"))
for slug, r in redes.items():
    if not r.get("sites"): continue
    arq = OUT / f"{slug}.json"
    if arq.exists(): continue
    vistos, paginas, fila = set(), {}, deque((u if u.startswith("http") else "https://" + u, 0) for u in r["sites"])
    dominios = {urllib.parse.urlparse(u if u.startswith("http") else "https://" + u).netloc.replace("www.", "") for u in r["sites"]}
    while fila and len(paginas) < 40:
        url, prof = fila.popleft()
        if url in vistos: continue
        vistos.add(url)
        s, final = baixa(url.replace("http://", "https://", 1)); time.sleep(0.4)
        if not s: continue
        paginas[final] = texto(s)
        if prof >= 2: continue
        for href, anc in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', s, flags=re.S | re.I):
            u = urllib.parse.urljoin(final, html.unescape(href)).split("#")[0]
            if urllib.parse.urlparse(u).netloc.replace("www.", "") not in dominios or EVITA.search(u): continue
            if CHAVES.search(u) or CHAVES.search(re.sub("<[^>]+>", "", anc)):
                fila.append((u, prof + 1))
    arq.write_text(json.dumps(paginas, ensure_ascii=False), encoding="utf-8")
    print(slug, len(paginas), "páginas", flush=True)
print("fim")
