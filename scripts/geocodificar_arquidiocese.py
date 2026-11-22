"""Geocodifica (Nominatim/OpenStreetMap) paróquias, comunidades e municípios da Arquidiocese, com cache.
Uso: python scripts/geocodificar_arquidiocese.py
Saída: dados/arquidiocese/geocache.json (consulta -> resultado). Respeita 1 consulta/segundo."""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
D = RAIZ / "dados" / "arquidiocese"
CACHE = D / "geocache.json"
UA = {"User-Agent": "mapa-paroquias-arquidiocese/0.2 (uso pontual)"}
VIEWBOX = "-49.45,-26.80,-48.30,-28.20"
MUNICIPIOS = ["Florianópolis","São José","Palhoça","Biguaçu","Antônio Carlos","Governador Celso Ramos","São Pedro de Alcântara",
 "Santo Amaro da Imperatriz","Águas Mornas","Anitápolis","São Bonifácio","Rancho Queimado","Angelina","Leoberto Leal","Major Gercino",
 "Nova Trento","São João Batista","Canelinha","Tijucas","Porto Belo","Bombinhas","Itapema","Balneário Camboriú","Camboriú","Itajaí",
 "Brusque","Guabiruba","Botuverá","Paulo Lopes","Garopaba","Alfredo Wagner","Navegantes","Imbituba"]
cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
ultimo = [0.0]
def nominatim(params):
    chave = json.dumps(params, sort_keys=True, ensure_ascii=False)
    if chave in cache: return cache[chave]
    espera = 1.15 - (time.time() - ultimo[0])
    if espera > 0: time.sleep(espera)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({**params, "format": "jsonv2"})
    for t in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)); break
        except Exception as e:
            print("erro", e, file=sys.stderr); time.sleep(5 * (t + 1))
    else:
        r = None
    ultimo[0] = time.time()
    if r is not None:
        cache[chave] = r
        if len(cache) % 20 == 0: CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return r

def municipio_de(txt):
    achados = [(txt.rfind(m), m) for m in MUNICIPIOS if m.lower() in txt.lower()]
    achados = [a for a in achados if a[0] >= 0]
    # "Balneário Camboriú" contém "Camboriú": prefere o nome mais longo na mesma posição final
    if not achados: return None
    achados.sort(key=lambda a: (a[0] + len(a[1]), len(a[1])))
    return achados[-1][1]

def main():
    pars = json.loads((D / "paroquias_site.json").read_text(encoding="utf-8"))
    # 1) municípios com polígono
    for m in MUNICIPIOS:
        nominatim({"q": f"{m}, Santa Catarina, Brasil", "polygon_geojson": 1, "polygon_threshold": 0.0002, "limit": 3, "addressdetails": 1})
    # 2) paróquias (endereço) e 3) comunidades (localidade, município)
    for p in pars:
        end = re.sub(r"(CEP:?\s*)?\d{5}-?\d{3}|Caixa Postal[^–|]*|Cx\. Postal[^–|]*", " ", p["endereco"])
        mun = p.get("municipio") or municipio_de(p["endereco"])
        if mun:
            rua = re.split(r"[–\-|;]", end)[0].strip()
            nominatim({"street": rua[:120], "city": mun, "state": "Santa Catarina", "country": "Brasil", "limit": 1, "addressdetails": 1})
        for c in p["comunidades"]:
            loc = (c.get("local") or "").strip()
            if not loc or not mun: continue
            nominatim({"q": f"{loc}, {mun}, Santa Catarina", "limit": 3, "addressdetails": 1, "viewbox": VIEWBOX, "bounded": 1})
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    # 4) igrejas do OSM em toda a região (grade com subdivisão quando enche)
    x0, x1, y0, y1 = -49.45, -48.30, -28.20, -26.80
    passo = 0.05
    def busca(a, b, c, d, prof=0):
        r = nominatim({"amenity": "place_of_worship", "viewbox": f"{a},{d},{c},{b}", "bounded": 1, "limit": 50, "extratags": 1, "addressdetails": 1})
        if r and len(r) >= 50 and prof < 4:
            mx, my = (a + c) / 2, (b + d) / 2
            for q in [(a, b, mx, my), (mx, b, c, my), (a, my, mx, d), (mx, my, c, d)]: busca(*q, prof + 1)
    from shapely.geometry import shape, box
    from shapely.ops import unary_union
    polis = []
    for m in MUNICIPIOS:
        for x in nominatim({"q": f"{m}, Santa Catarina, Brasil", "polygon_geojson": 1, "polygon_threshold": 0.0002, "limit": 3, "addressdetails": 1}) or []:
            if x.get("category") == "boundary" or x.get("type") == "administrative":
                polis.append(shape(x["geojson"]).buffer(0)); break
    regiao = unary_union(polis)
    x0, y0, x1, y1 = regiao.bounds
    lon = x0
    while lon < x1:
        lat = y0
        while lat < y1:
            if box(lon, lat, lon + passo, lat + passo).intersects(regiao):
                busca(lon, lat, lon + passo, lat + passo)
            lat += passo
        lon += passo
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print("ok", len(cache))
if __name__ == "__main__": main()
