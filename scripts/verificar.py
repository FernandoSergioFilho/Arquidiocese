"""Confere mapa/dados.json e gera um relatório de tudo que pode estar errado.
Uso: python scripts/verificar.py  (escreve dados/arquidiocese/relatorio_verificacao.txt)"""
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import Point, shape

RAIZ = Path(__file__).resolve().parents[1]
D = json.loads((RAIZ / "mapa" / "dados.json").read_text(encoding="utf-8"))
H = D["hierarquia"]
SITE = json.loads((RAIZ / "dados" / "arquidiocese" / "paroquias_site.json").read_text(encoding="utf-8"))
saida = []


def out(*a):
    saida.append(" ".join(str(x) for x in a))


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 98.6)


def toks(t):
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
    return set(re.sub(r"[^a-z0-9 ]", " ", t).split()) - {"de", "da", "do", "dos", "das", "e", "capela", "igreja", "paroquia",
                                                         "comunidade", "nossa", "senhora", "n", "sra", "matriz", "santuario"}


muns = {f["properties"]["nome"]: shape(f["geometry"]).convex_hull for f in D["municipios"]["features"]}  # só para conferência grossa
pars = [(f, p) for f in H["foranias"] for p in f["paroquias"]]

out("== 1. Identificadores únicos")
ids = Counter(p["id"] for _, p in pars)
out("  paróquias repetidas:", [k for k, v in ids.items() if v > 1] or "nenhuma")

out("\n== 2. Contagem de comunidades: site x mapa")
por_slug = {x["slug"]: x for x in SITE}
for f, p in pars:
    slug = p["fonte"].rstrip("/").rsplit("/", 1)[1]
    s = por_slug.get(slug)
    if not s:
        out("  sem página de origem:", p["id"]); continue
    n_site, n_mapa = len(s["comunidades"]), len(p["comunidades"])
    if n_site != n_mapa and not (n_site + 1 == n_mapa):  # +1 = matriz criada quando o site não lista
        out(f"  {p['id']}: site {n_site}, mapa {n_mapa}")

out("\n== 3. Forania: página da forania x cabeçalho da paróquia")
links = {}
for linha in (RAIZ / "dados" / "arquidiocese" / "foranias_links.txt").read_text(encoding="utf-8").split("\n"):
    if linha.strip():
        fo, url = linha.split(); links[url.rstrip("/").rsplit("/", 1)[1]] = fo
for f, p in pars:
    slug = p["fonte"].rstrip("/").rsplit("/", 1)[1]
    cab = por_slug.get(slug, {}).get("forania", "")
    out(f"  {f['id']:12} | link: {links.get(slug, '-'):26} | cabeçalho: {cab[:40]:40} | {p['nome'][:50]}") if not links.get(slug) else None

out("\n== 4. Matrizes: como foram posicionadas")
for f, p in pars:
    mz = [c for c in p["comunidades"] if c["matriz"]]
    if len(mz) != 1:
        out(f"  {p['id']}: {len(mz)} matrizes")
    for c in mz:
        if c.get("posicao") not in ("osm", "endereco") and not p.get("ilha"):
            out(f"  {p['id']:40} matriz '{c['nome']}' posição={c.get('posicao')} local={c['local']}")

out("\n== 5. Igrejas do OSM: nome no site x nome no mapa (para revisão)")
for f, p in pars:
    for c in p["comunidades"]:
        if c.get("posicao") == "osm" and not p.get("ilha"):
            a, b = toks(c["nome"]), toks(c.get("nome_osm"))
            marca = "" if a == b else "  ≠"
            out(f"  {p['id'][:28]:28} | {c['nome'][:38]:38} | {c['local'][:22]:22} | {c.get('nome_osm','')[:45]}{marca}")

out("\n== 6. Mesma coordenada para igrejas diferentes")
pos = defaultdict(list)
for f, p in pars:
    for c in p["comunidades"]:
        if "lat" in c:
            pos[(round(c["lat"], 5), round(c["lng"], 5))].append(f"{p['id']}:{c['nome']}")
for k, v in pos.items():
    if len(v) > 1:
        out("  ", k, v)

out("\n== 7. Distância de cada igreja até a matriz (> 15 km)")
for f, p in pars:
    mz = next((c for c in p["comunidades"] if c["matriz"] and "lat" in c), None)
    if not mz:
        continue
    for c in p["comunidades"]:
        if "lat" in c and not c["matriz"]:
            d = km((c["lat"], c["lng"]), (mz["lat"], mz["lng"]))
            if d > 15:
                out(f"  {p['id'][:30]:30} {c['nome'][:35]:35} {c['local'][:20]:20} {d:5.1f} km ({c.get('posicao')})")

out("\n== 8. Resumo das posições")
out("  ", Counter(c.get("posicao", "bairro (Ilha)") for _, p in pars for c in p["comunidades"]))

txt = "\n".join(saida)
(RAIZ / "dados" / "arquidiocese" / "relatorio_verificacao.txt").write_text(txt, encoding="utf-8")
print(txt)
