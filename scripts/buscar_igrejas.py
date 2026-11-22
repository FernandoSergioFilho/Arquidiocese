"""Busca no Nominatim cada igreja que ainda não tem posição exata: "nome, localidade, município" e "nome, município".
Uso: python scripts/buscar_igrejas.py  (lê mapa/dados.json, grava no mesmo cache do geocodificar_arquidiocese.py)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import geocodificar_arquidiocese as g

RAIZ = Path(__file__).resolve().parents[1]
dados = json.loads((RAIZ / "mapa" / "dados.json").read_text(encoding="utf-8"))
n = 0
for f in dados["hierarquia"]["foranias"]:
    for p in f["paroquias"]:
        mun = p["municipio"]
        for c in p["comunidades"]:
            if c.get("posicao") == "osm":
                continue
            nome, loc = c["nome"], c["local"]
            for q in (f"{nome}, {loc}, {mun}, Santa Catarina", f"{nome}, {mun}, Santa Catarina"):
                g.nominatim({"q": q, "limit": 5, "addressdetails": 1, "extratags": 1, "viewbox": g.VIEWBOX, "bounded": 1})
                n += 1
g.CACHE.write_text(json.dumps(g.cache, ensure_ascii=False), encoding="utf-8")
print("ok", n)
