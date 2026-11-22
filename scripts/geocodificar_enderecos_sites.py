"""Filtra os endereços achados nos sites e consulta o Nominatim para cada um (cache em geocache.json).
Uso: python scripts/geocodificar_enderecos_sites.py -> dados/arquidiocese/enderecos_filtrados.json"""
import json, re, sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
import geocodificar_arquidiocese as g
D = RAIZ / "dados" / "arquidiocese"
cand = json.loads((D / "enderecos_sites.json").read_text(encoding="utf-8"))
hier = json.loads((D / "hierarquia.json").read_text(encoding="utf-8"))
par = {p["id"]: p for f in hier["foranias"] for p in f["paroquias"]}
INICIO = re.compile(r"^(Rua|R\.|Avenida|Av\.?|Rodovia|Rod\.|SC[- ]?\d{3}|BR[- ]?\d{3}|Estrada|Servid[aã]o|Travessa|Tv\.|Pra[cç]a|Alameda|Largo|Caminho|Loteamento)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9“\"(]|d[aeo]s?\s+[A-ZÁÉÍÓÚ])")
def rua_de(e):
    e = re.sub(r"\(.*?\)", " ", e)
    e = re.split(r"\s[–-]\s|,\s*(?=[A-ZÁÉÍÓÚ][a-záéíóú]+\s*[–-])|\||CEP|\d{5}-?\d{3}", e)[0]
    m = re.match(r"(.+?),?\s*(n[º°o]?\.?\s*)?(\d[\d.]*|s/?n[º°o]?)\b", e, re.I)
    rua, num = (m.group(1), m.group(3)) if m else (e, None)
    num = None if not num or re.match(r"s/?n", num, re.I) else num.replace(".", "")
    return re.sub(r"\s+", " ", rua).strip(" ,.;"), num
saida = {}
for k, lista in cand.items():
    pid, nome, local = k.split("|")
    p = par[pid]
    c = next(x for x in p["comunidades"] if x["nome"] == nome and x["local"] == local)
    rua_par = rua_de(p["endereco"])[0].lower()
    bons = []
    for x in lista:
        e = x["endereco"]
        if not INICIO.match(e):
            continue
        rua, num = rua_de(e)
        if len(rua) < 6:
            continue
        if not c["matriz"] and rua.lower() == rua_par:
            continue  # endereço da secretaria repetido na lista de comunidades
        bons.append({"rua": rua, "numero": num, "texto": e, "url": x["url"]})
    if not bons:
        continue
    b = bons[0]
    mun = p["municipio"]
    r = g.nominatim({"street": (f"{b['numero']} " if b["numero"] else "") + b["rua"], "city": mun, "state": "Santa Catarina", "country": "Brasil", "limit": 1, "addressdetails": 1})
    if not r and b["numero"]:
        r = g.nominatim({"street": b["rua"], "city": mun, "state": "Santa Catarina", "country": "Brasil", "limit": 1, "addressdetails": 1})
    saida[k] = {**b, "municipio": mun, "resultado": (r or [None])[0]}
    print(k[:60], "|", b["rua"], b["numero"] or "", "->", (r[0]["display_name"][:70] if r else "não encontrado"), flush=True)
g.CACHE.write_text(json.dumps(g.cache, ensure_ascii=False), encoding="utf-8")
(D / "enderecos_filtrados.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
print("fim", len(saida))
