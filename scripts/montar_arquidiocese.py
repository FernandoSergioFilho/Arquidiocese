"""Monta mapa/dados.json para a Arquidiocese inteira (13 foranias).

Uso: python scripts/montar_arquidiocese.py <bairros_fln.gpkg> <municipios_sc.geojson>

Entradas:
  dados/arquidiocese/paroquias_site.json  paróquias e comunidades do site arquifln.org.br (83 páginas)
  dados/arquidiocese/geocache.json        respostas do Nominatim (scripts/geocodificar_arquidiocese.py)
  dados/paroquias.json                    Ilha de Santa Catarina já tratada à mão (scripts/montar_dados.py)
  dados/bairros_ilha.geojson              bairros da Ilha com paróquia (scripts/montar_dados.py)

Regiões do mapa:
  Ilha: bairros do IBGE, como antes (matriz / comunidade / estimado).
  Continente de Florianópolis: bairros do IBGE, pela comunidade que cai dentro de cada um.
  Demais municípios: área estimada de cada paróquia = união das células de Voronoi das suas
  igrejas, recortada pelo limite do município (OpenStreetMap).
"""
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path

import geopandas as gpd
import sys as _s; _s.path.insert(0, __import__("os").path.dirname(__file__))
from bairros_util import ler_bairros  # noqa: E402
from shapely.geometry import MultiPoint, Point, mapping, shape
from shapely.ops import unary_union, voronoi_diagram

RAIZ = Path(__file__).resolve().parents[1]
D = RAIZ / "dados" / "arquidiocese"
sys.path.insert(0, str(RAIZ / "scripts"))
from geocodificar_arquidiocese import MUNICIPIOS, VIEWBOX, municipio_de  # noqa: E402

FONTE = "https://arquifln.org.br/igrejas/{}/"
ORDEM_FORANIAS = [
    ("centro-sul", "Forania Florianópolis Centro-Sul", "florianopolis-centro-sul"),
    ("norte", "Forania Florianópolis Norte", "florianopolis-norte"),
    ("continente", "Forania Florianópolis Continente", "florianopolis-continente"),
    ("sao-jose", "Forania São José", "sao-jose"),
    ("barreiros", "Forania São José – Barreiros", "barreiros-sao-jose"),
    ("biguacu", "Forania Biguaçu", "biguacu"),
    ("palhoca", "Forania Palhoça", "palhoca"),
    ("santo-amaro", "Forania Santo Amaro", "santo-amaro"),
    ("tijucas", "Forania Tijucas", "tijucas-2"),
    ("itapema", "Forania Itapema", "itapema"),
    ("camboriu", "Forania Camboriú", "camboriu"),
    ("itajai", "Forania Itajaí", "itajai"),
    ("brusque", "Forania Brusque", "brusque"),
]
ILHA_IDS = {  # paróquias da Ilha: mantêm os ids e cores já usados
    "paroquia-nossa-senhora-do-desterro-e-santa-catarina": "desterro", "paroquia-santo-antonio": "santo-antonio",
    "paroquia-santa-teresinha-do-menino-jesus": "santa-teresinha", "paroquia-nossa-senhora-de-lourdes-e-sao-luis-gonzaga": "lourdes",
    "paroquia-nossa-senhora-da-boa-viagem": "boa-viagem", "paroquia-nossa-senhora-da-lapa": "lapa",
    "paroquia-nossa-senhora-do-sagrado-coracao": "sagrado-coracao", "paroquia-nossa-senhora-da-imaculada-conceicao-da-lagoa": "lagoa",
    "paroquia-nossa-senhora-das-necessidades": "necessidades", "paroquia-nossa-senhora-de-guadalupe": "guadalupe",
    "paroquia-sagrado-coracao-de-jesus": "ingleses", "paroquia-santissima-trindade": "trindade",
    "paroquia-sao-francisco-xavier": "sao-francisco-xavier",
}
SEM_TERRITORIO = re.compile(r"^(Capelania|Paróquia Militar|Reitoria|Santuário Santa Paulina)")


def limpa(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def norm_tokens(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(igreja|capela|paroquia|santuario|matriz|comunidade|gruta|de|da|do|dos|das|e|n|sra|senhora|nossa|s)\b", " ", s)
    return set(re.sub(r"[^a-z ]", " ", s).split())


def arred(geom, casas=5):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], casas), round(c[1], casas)]
        return [r(x) for x in c]
    m = mapping(geom)
    return {"type": m["type"], "coordinates": r(m["coordinates"])}


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians(27.5)))


def campo(linhas, prefixo):
    for s in linhas:
        if s.startswith(prefixo):
            return limpa(s.split(":", 1)[1]) if ":" in s else limpa(s)
    return None


def main(arq_bairros, arq_municipios):
    site = json.loads((D / "paroquias_site.json").read_text(encoding="utf-8"))
    cache = json.loads((D / "geocache.json").read_text(encoding="utf-8"))
    ilha = json.loads((RAIZ / "dados" / "paroquias.json").read_text(encoding="utf-8"))
    ilha_geo = json.loads((RAIZ / "dados" / "bairros_ilha.geojson").read_text(encoding="utf-8"))

    def q(params):
        return cache.get(json.dumps(params, sort_keys=True, ensure_ascii=False))

    # ---------- Municípios (OSM) ----------
    mun_geom = {}
    for m in MUNICIPIOS:
        r = q({"q": f"{m}, Santa Catarina, Brasil", "polygon_geojson": 1, "polygon_threshold": 0.0002, "limit": 3, "addressdetails": 1}) or []
        for x in r:
            if x.get("category") == "boundary" or x.get("type") == "administrative":
                g = shape(x["geojson"])
                if g.geom_type in ("Polygon", "MultiPolygon"):
                    mun_geom[m] = g.buffer(0)
                    break
    print("municípios com limite:", len(mun_geom), "faltando:", [m for m in MUNICIPIOS if m not in mun_geom])

    def municipio_do_ponto(lat, lng):
        p = Point(lng, lat)
        for m, g in mun_geom.items():
            if g.contains(p):
                return m
        return None

    # ---------- Igrejas católicas do OSM (todas as respostas de place_of_worship no cache) ----------
    osm = {}
    for k, v in cache.items():
        if '"amenity": "place_of_worship"' not in k or not v:
            continue
        for x in v:
            t = x.get("extratags") or {}
            den = t.get("denomination")
            nome = x.get("name") or ""
            if den in ("roman_catholic", "catholic") or (den is None and re.search(r"capela|par[oó]quia|santu|igreja (matriz|de )?(nossa|s[aã]o|santa|santo|sagrad|bom jesus|divino)", nome.lower())):
                osm[x["osm_type"][0] + str(x["osm_id"])] = {"nome": nome, "lat": float(x["lat"]), "lng": float(x["lon"]), "tok": norm_tokens(nome)}
    osm = list(osm.values())
    print("igrejas católicas no OSM:", len(osm))

    def casa_osm(nome, perto, raio_km):
        tk = norm_tokens(nome)
        if not tk:
            return None
        melhores = []
        for o in osm:
            if not (tk <= o["tok"]) and not (o["tok"] and o["tok"] <= tk and len(o["tok"]) >= 2):
                continue
            d = km((o["lat"], o["lng"]), perto)
            if d <= raio_km:
                melhores.append((d, o))
        melhores.sort(key=lambda t: t[0])
        # ambíguo: duas candidatas igualmente perto -> não aceita
        if len(melhores) >= 2 and melhores[1][0] - melhores[0][0] < 0.3:
            return None
        return melhores[0][1] if melhores else None

    # ---------- Hierarquia ----------
    fs = {fid: {"id": fid, "nome": nome, "fonte": f"https://arquifln.org.br/organizacao/1070-2/{slug}/", "paroquias": [], "outras": []}
          for fid, nome, slug in ORDEM_FORANIAS}
    links = {}
    for linha in (D / "foranias_links.txt").read_text(encoding="utf-8").split("\n"):
        if linha.strip():
            f, url = linha.split()
            links[url.rstrip("/").rsplit("/", 1)[1]] = {s: fid for fid, _, s in ORDEM_FORANIAS}[f]

    def forania_txt(t):
        t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
        for fid, chave in [("barreiros", "barreiros"), ("centro-sul", "centro"), ("norte", "norte"), ("continente", "continente"),
                           ("sao-jose", "sao jose"), ("biguacu", "biguacu"), ("palhoca", "palhoca"), ("santo-amaro", "santo amaro"),
                           ("tijucas", "tijucas"), ("itapema", "itapema"), ("camboriu", "camboriu"), ("itajai", "itajai"), ("brusque", "brusque")]:
            if chave in t:
                return fid
        return None

    ilha_par = {p["id"]: p for f in ilha["foranias"] for p in f["paroquias"]}
    usados = set()
    todas_igrejas = []
    for p in sorted(site, key=lambda x: x["slug"]):
        fid = links.get(p["slug"]) or forania_txt(p.get("forania_corrigida")) or forania_txt(p["forania"])
        nome = limpa(p["nome"])
        mun = p.get("municipio") or municipio_de(p["endereco"]) or "Florianópolis"
        sobre = p.get("sobre", [])
        if SEM_TERRITORIO.match(nome):
            fs[fid]["outras"].append({"nome": nome, "endereco": limpa(p["endereco"]), "municipio": mun, "fonte": FONTE.format(p["slug"])})
            continue
        if p["slug"] in ILHA_IDS:  # Ilha: dados já conferidos
            par = dict(ilha_par[ILHA_IDS[p["slug"]]])
            par["municipio"] = "Florianópolis"
            par["ilha"] = True
            fs[fid]["paroquias"].append(par)
            for c in par["comunidades"]:
                todas_igrejas.append((par, c))
            continue
        base = re.sub(r"^paroquia-", "", p["slug"])
        pid = base if base not in usados else base + "-2"
        usados.add(pid)
        criada = campo(sobre, "(Criada")
        par = {"id": pid, "nome": nome, "municipio": mun, "endereco": limpa(p["endereco"]),
               "paroco": campo(sobre, "Pároco") or campo(sobre, "Administrador"),
               "criada": criada.strip("()") if criada else None, "fonte": FONTE.format(p["slug"]), "comunidades": []}
        # posição do endereço da matriz
        end = re.sub(r"(CEP:?\s*)?\d{5}-?\d{3}|Caixa Postal[^–|]*|Cx\. Postal[^–|]*", " ", p["endereco"])
        rua = re.split(r"[–\-|;]", end)[0].strip()
        r_end = q({"street": rua[:120], "city": mun, "state": "Santa Catarina", "country": "Brasil", "limit": 1, "addressdetails": 1}) or []
        pos_end = (float(r_end[0]["lat"]), float(r_end[0]["lon"])) if r_end else None
        if pos_end is None and mun in mun_geom:
            c0 = mun_geom[mun].representative_point()
            pos_end = (c0.y, c0.x)
        coms = p["comunidades"] or [{"nome": "Matriz: " + re.sub(r"^Paróquia\s+", "", nome), "local": mun, "ano": None}]
        if not any(limpa(c["nome"]).lower().startswith("matriz") for c in coms):
            pass
        for c in coms:
            n = limpa(c["nome"])
            matriz = n.lower().startswith("matriz")
            n = re.sub(r"^Matriz:?\s*", "", n)
            loc = limpa(c.get("local"))
            item = {"nome": n, "local": loc, "ano": c.get("ano") or None, "matriz": matriz}
            # ponto de referência: matriz -> endereço; demais -> localidade geocodificada
            ref, ref_tipo = None, None
            if matriz and pos_end:
                ref, ref_tipo = pos_end, "endereco"
            else:
                r = q({"q": f"{loc}, {mun}, Santa Catarina", "limit": 3, "addressdetails": 1, "viewbox": VIEWBOX, "bounded": 1}) or []
                r = [x for x in r if x.get("addresstype") not in ("state", "region", "country")]
                if r:
                    x = r[0]
                    ref = (float(x["lat"]), float(x["lon"]))
                    ref_tipo = "municipio" if x.get("addresstype") in ("municipality", "city", "town") else "localidade"
            if ref is None and pos_end:
                ref, ref_tipo = pos_end, "municipio"
            if ref_tipo == "municipio":
                ref = None  # localidade não encontrada: fica perto da matriz (abaixo)
            o = casa_osm(n, ref, 1.5 if matriz else (4 if ref_tipo == "localidade" else 6)) if ref else None
            if o:
                item.update({"lat": round(o["lat"], 6), "lng": round(o["lng"], 6), "posicao": "osm", "nome_osm": o["nome"]})
            elif ref and ref_tipo in ("endereco", "localidade"):
                item.update({"lat": round(ref[0], 6), "lng": round(ref[1], 6), "posicao": ref_tipo})
            else:
                item["posicao"] = "aprox"
            par["comunidades"].append(item)
            todas_igrejas.append((par, item))
        # sem localização: em volta da matriz (ou do endereço da paróquia)
        mz = next((c for c in par["comunidades"] if c["matriz"] and "lat" in c), None)
        centro = (mz["lat"], mz["lng"]) if mz else pos_end
        soltas = [c for c in par["comunidades"] if "lat" not in c]
        for j, c in enumerate(soltas):
            if not centro:
                break
            a = 2 * math.pi * j / max(len(soltas), 1) + 0.4
            r = 0.006 + 0.0008 * len(soltas)
            c["lat"], c["lng"] = round(centro[0] + r * math.cos(a), 6), round(centro[1] + r * math.sin(a) / 0.887, 6)
            c["posicao"] = "aprox"
        par["comunidades"].sort(key=lambda c: (not c["matriz"], c["nome"]))
        fs[fid]["paroquias"].append(par)

    # Mesma posição para várias igrejas (localidade/município): espalha em círculo pequeno
    grupos = defaultdict(list)
    for par, c in todas_igrejas:
        if par.get("ilha"):
            continue
        if c.get("posicao") in ("localidade", "endereco") and "lat" in c:
            pos = (c["lat"], c["lng"])
            grupos[(round(pos[0], 4), round(pos[1], 4))].append(c)
    for (la, lo), cs in grupos.items():
        n = len(cs)
        for k, c in enumerate(cs):
            r = 0 if n == 1 else 0.0012 + 0.0004 * n
            a = 2 * math.pi * k / max(n, 1)
            c["lat"], c["lng"] = round(la + r * math.cos(a), 6), round(lo + r * math.sin(a) / 0.887, 6)

    # ---------- Regiões ----------
    feats, vazios = [], []
    # Ilha (já pronta). Bairros sem nenhuma igreja ficam sem paróquia (só o contorno).
    for f in ilha_geo["features"]:
        p = dict(f["properties"])
        p["nome"] = p.pop("bairro")
        if p["situacao"] == "estimado":
            vazios.append({"type": "Feature", "properties": {"nome": p["nome"], "ponto": p["ponto"]}, "geometry": f["geometry"]})
            continue
        p["municipio"] = "Florianópolis"
        p["tipo"] = "bairro"
        feats.append({"type": "Feature", "properties": p, "geometry": f["geometry"]})

    # Continente de Florianópolis: bairros IBGE
    g = ler_bairros(arq_bairros)
    cont = g[g.REGIAO_FUNCIONAL == "Continente"].reset_index(drop=True)
    cont4326 = cont.to_crs(4326)
    forania_de = {p["id"]: f["id"] for f in fs.values() for p in f["paroquias"]}
    pres = defaultdict(Counter)
    matriz_em = {}
    for par, c in todas_igrejas:
        if par.get("ilha") or "lat" not in c:
            continue
        dentro = cont4326[cont4326.contains(Point(c["lng"], c["lat"]))]
        if len(dentro):
            b = dentro.NM_BAIRRO.iloc[0]
            c["regiao"] = b
            pres[b][par["id"]] += 1
            if c["matriz"]:
                matriz_em.setdefault(b, par["id"])
    buf = cont.geometry.buffer(30)
    viz = {i: [j for j in buf.sindex.query(buf.iloc[i], predicate="intersects") if j != i] for i in range(len(cont))}
    nomes = list(cont.NM_BAIRRO)
    atrib, fila = {}, deque()
    for i, n in enumerate(nomes):
        if n in pres:
            atrib[i] = (0, i); fila.append(i)
    while fila:
        i = fila.popleft()
        for j in viz[i]:
            if j not in atrib:
                atrib[j] = (atrib[i][0] + 1, atrib[i][1]); fila.append(j)
    simpl = cont.geometry.simplify(12).to_crs(4326)
    for i, n in enumerate(nomes):
        rp = simpl.iloc[i].representative_point()
        props = {"nome": n, "municipio": "Florianópolis", "tipo": "bairro", "distrito": "Continente",
                 "pop": int(round(cont.POP.iloc[i] or 0)), "ponto": [round(rp.y, 5), round(rp.x, 5)]}
        if n in pres:
            pr = matriz_em.get(n) or pres[n].most_common(1)[0][0]
            props.update({"principal": pr, "paroquias": [pr] + [x for x in pres[n] if x != pr],
                          "situacao": "matriz" if n in matriz_em else "comunidade"})
        else:
            vazios.append({"type": "Feature", "properties": {"nome": n, "ponto": props["ponto"]}, "geometry": arred(simpl.iloc[i])})
            continue
        props["forania"] = forania_de[props["principal"]]
        feats.append({"type": "Feature", "properties": props, "geometry": arred(simpl.iloc[i])})

    # Demais municípios: Voronoi das igrejas recortado pelo município
    por_mun = defaultdict(list)
    for par, c in todas_igrejas:
        if par.get("ilha") or "lat" not in c:
            continue
        m = municipio_do_ponto(c["lat"], c["lng"])
        if m:
            c["municipio"] = m
        if m and m != "Florianópolis" and c["posicao"] != "aprox":
            por_mun[m].append((par, c))
    for m, itens in por_mun.items():
        area = mun_geom[m]
        pts = {}
        for par, c in itens:
            pts.setdefault((round(c["lng"], 5), round(c["lat"], 5)), (par, c))
        if len(pts) == 1:
            celulas = [(area, list(pts.values())[0][0])]
        else:
            vd = voronoi_diagram(MultiPoint([Point(*k) for k in pts]), envelope=area.envelope.buffer(0.2))
            celulas = []
            for cel in vd.geoms:
                for k, (par, c) in pts.items():
                    if cel.contains(Point(*k)):
                        celulas.append((cel.intersection(area), par))
                        break
        por_par = defaultdict(list)
        for geom, par in celulas:
            por_par[par["id"]].append(geom)
        for pid, gs in por_par.items():
            u = unary_union(gs).simplify(0.0003, preserve_topology=True)
            if u.is_empty:
                continue
            rp = u.representative_point()
            nome_par = next(p["nome"] for f in fs.values() for p in f["paroquias"] if p["id"] == pid)
            feats.append({"type": "Feature", "properties": {
                "nome": f"{m} · {re.sub(r'^Paróquia ', '', nome_par)}", "municipio": m, "tipo": "area",
                "principal": pid, "paroquias": [pid], "situacao": "area", "forania": forania_de[pid],
                "ponto": [round(rp.y, 5), round(rp.x, 5)]}, "geometry": arred(u, 4)})
    print("regiões:", Counter(f["properties"]["tipo"] for f in feats))

    # ---------- Fundo ----------
    fundo = []
    mun_sc = json.loads(Path(arq_municipios).read_text(encoding="utf-8"))
    nossos = set(por_mun) | {"Florianópolis"}
    arq_uniao = unary_union([mun_geom[m] for m in nossos if m in mun_geom])
    caixa = arq_uniao.envelope.buffer(0.5)
    for f in mun_sc["features"]:
        geom = shape(f["geometry"])
        if geom.intersects(caixa) and f["properties"]["name"] not in nossos:
            fundo.append({"type": "Feature", "properties": {"nome": f["properties"]["name"], "fora": True}, "geometry": arred(geom.simplify(0.002), 3)})
    limites = [{"type": "Feature", "properties": {"nome": m, "ponto": [round(mun_geom[m].representative_point().y, 4), round(mun_geom[m].representative_point().x, 4)]},
                "geometry": arred(mun_geom[m].boundary.simplify(0.0004), 4)} for m in sorted(nossos) if m in mun_geom]

    contagem = Counter(c.get("posicao", "sem") for _, c in todas_igrejas)
    print("posição das igrejas:", contagem, "total", len(todas_igrejas))
    hier = {"arquidiocese": "Arquidiocese de Florianópolis", "lido_em": "2026-11-21",
            "foranias": [fs[fid] for fid, _, _ in ORDEM_FORANIAS]}
    dados = {"hierarquia": hier, "regioes": {"type": "FeatureCollection", "features": feats},
             "fundo": {"type": "FeatureCollection", "features": fundo},
             "vazios": {"type": "FeatureCollection", "features": vazios},
             "municipios": {"type": "FeatureCollection", "features": limites}}
    (RAIZ / "mapa" / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (D / "hierarquia.json").write_text(json.dumps(hier, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{(RAIZ / 'mapa' / 'dados.json').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
