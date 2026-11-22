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


def norm_seq(s):
    """Palavras do nome em ordem, sem palavras de tipo (igreja, capela...) e sem ligações."""
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(n\.?\s*sra\.?|n\.?\s*s\.?)\b", "nossa senhora", s)
    s = re.sub(r"\bsta\.?\b", "santa", s); s = re.sub(r"\bsto\.?\b", "santo", s)
    s = re.sub(r"\bluiz\b", "luis", s); s = re.sub(r"\bestevao\b", "estevao", s); s = re.sub(r"\bcassia\b", "cassia", s)
    fora = {"igreja", "capela", "paroquia", "santuario", "matriz", "comunidade", "gruta", "oratorio", "de", "da", "do", "dos", "das",
            "e", "nossa", "senhora", "catolica", "irmandade", "ir"}
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", s).split() if w not in fora]


def contido(a, b):
    """a aparece em b como sequência contígua"""
    if not a or len(a) > len(b):
        return False
    return any(b[i:i + len(a)] == a for i in range(len(b) - len(a) + 1))


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
    NAO_CATOLICA = re.compile(r"evang|assembl|batista|adventista|universal|quadrangular|presbiter|luteran|esp[ií]rit|testemunh|"
                              r"[uú]ltimos dias|congrega[cç][aã]o crist|maranata|deus [eé] amor|mundial|renascer|metodista|umbanda|"
                              r"candombl|templo|minist[eé]rio|igreja de cristo|igreja crist[aã]|pentecost|sara nossa|bola de neve|"
                              r"videira|internacional da gra[cç]a|nazareno|anglican|ortodox|kardec|budis|mesquita|sinagoga|"
                              r"wesley|apost[oó]lica renascer|cristo vive|vida nova|lagoinha|tabernáculo|tabernaculo", re.I)
    for k, v in cache.items():
        for x in v or []:
            if not isinstance(x, dict) or x.get("type") != "place_of_worship":
                continue
            t = x.get("extratags") or {}
            den = (t.get("denomination") or "").lower()
            rel = (t.get("religion") or "christian").lower()
            nome = x.get("name") or ""
            if not nome or rel != "christian":
                continue
            if den in ("roman_catholic", "catholic") or (not den and not NAO_CATOLICA.search(nome)):
                osm[x["osm_type"][0] + str(x["osm_id"])] = {"nome": nome, "lat": float(x["lat"]), "lng": float(x["lon"]), "tok": norm_tokens(nome), "seq": norm_seq(nome)}
    # igrejas do OSM já atribuídas na Ilha (conferidas à mão) não entram na busca
    ja_ilha = [(c["lat"], c["lng"]) for f in ilha["foranias"] for p in f["paroquias"] for c in p["comunidades"] if "lat" in c]
    osm = [o for o in osm.values() if not any(abs(o["lat"] - a) < 0.0003 and abs(o["lng"] - b) < 0.0003 for a, b in ja_ilha)]
    print("igrejas católicas no OSM:", len(osm))

    GENERICOS = {"rua", "r", "av", "avenida", "rod", "rodovia", "estrada", "servidao", "travessa", "praca", "bairro", "loteamento", "lot",
                 "vila", "jardim", "morro", "centro", "alto", "baixo", "rio", "sc", "br"}

    def toks(t, tirar_genericos=True):
        t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
        w = set(re.sub(r"[^a-z0-9 ]", " ", t).split()) - {"de", "da", "do", "dos", "das", "e", "a", "o"}
        w = {x for x in w if not x.isdigit()}
        return w - GENERICOS if tirar_genericos else w

    def mesmo_municipio(x, mun):
        a = x.get("address") or {}
        alvo = toks(mun, False)
        return any(a.get(k) and toks(a[k], False) == alvo for k in ("city", "town", "municipality", "village"))

    def nome_bate(a, b):
        ta, tb = toks(a), toks(b)
        if not ta:  # só palavras genéricas ("Centro", "Morro"): compara tudo
            ta, tb = toks(a, False), toks(b, False)
        return bool(ta) and bool(tb) and (ta <= tb or tb <= ta)

    TIPOS_LUGAR = {"suburb", "neighbourhood", "quarter", "hamlet", "village", "isolated_dwelling", "locality", "city_district",
                   "place", "square", "farm", "allotments", "residential", "road", "statistical", "borough"}

    def localidade_valida(loc, mun):
        if not loc or toks(loc, False) == toks(mun, False):
            return None
        r = q({"q": f"{loc}, {mun}, Santa Catarina", "limit": 3, "addressdetails": 1, "viewbox": VIEWBOX, "bounded": 1}) or []
        for x in r:
            nome_x = x.get("name") or (x.get("display_name") or "").split(",")[0]
            if x.get("addresstype") not in TIPOS_LUGAR:
                continue
            if not mesmo_municipio(x, mun) or not nome_bate(loc, nome_x):
                continue
            if x.get("addresstype") in ("road", "residential") and toks(loc) != toks(nome_x):
                continue  # rua só vale com nome igual (evita "Arruda" -> "Rua Joaquim Coelho de Arruda")
            g = mun_geom.get(mun)
            if g is not None and not g.buffer(0.01).contains(Point(float(x["lon"]), float(x["lat"]))):
                continue
            return x
        return None

    def endereco_bate(rua, x, mun):
        a = x.get("address") or {}
        return mesmo_municipio(x, mun) and bool(a.get("road")) and nome_bate(rua, a["road"])

    def casa_osm(nome, perto, raio_km, area=None):
        """Igreja do OSM com o mesmo nome: perto de um ponto de referência, ou única dentro de uma área."""
        sq = norm_seq(nome)
        if not sq:
            return None
        cands = []
        for o in osm:
            if not (contido(sq, o["seq"]) or (len(o["seq"]) >= 2 and contido(o["seq"], sq) and len(o["seq"]) >= 0.6 * len(sq))):
                continue
            if perto is not None:
                d = km((o["lat"], o["lng"]), perto)
                if d <= raio_km:
                    cands.append((d, o))
            elif area is not None and area.contains(Point(o["lng"], o["lat"])):
                cands.append((0.0, o))
        cands.sort(key=lambda t: t[0])
        if perto is None:
            return (cands[0][1], 99.0) if len(cands) == 1 else None  # dentro do município: só se for a única
        if len(cands) >= 2 and cands[1][0] - cands[0][0] < 0.3:
            return None
        return (cands[0][1], cands[0][0]) if cands else None

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

    api_cat = json.loads((D / "api_categorias.json").read_text(encoding="utf-8"))
    redes = json.loads((D / "redes.json").read_text(encoding="utf-8"))
    ilha_par = {p["id"]: p for f in ilha["foranias"] for p in f["paroquias"]}
    # quantas comunidades com o mesmo nome existem em cada município (busca por nome no município só vale se for única)
    nomes_mun = Counter()
    for p0 in site:
        m0 = p0.get("municipio") or municipio_de(p0["endereco"]) or "Florianópolis"
        for c0 in p0["comunidades"]:
            nomes_mun[(m0, frozenset(norm_tokens(re.sub(r"^Matriz:?\s*|\s*\(Matriz\)", "", limpa(c0["nome"])))))] += 1
    usados = set(ILHA_IDS.values())  # ids únicos: nenhuma paróquia nova pode repetir um id da Ilha
    todas_igrejas = []
    for p in sorted(site, key=lambda x: x["slug"]):
        # forania: maioria entre cabeçalho da página da paróquia, classificação interna do site e lista da página da forania
        # forania: cabeçalho da página da paróquia; se faltar, a classificação interna do site
        fid = forania_txt(p.get("forania_corrigida")) or forania_txt(p["forania"]) or (api_cat.get(p["slug"]) or [None])[0]
        cat = (api_cat.get(p["slug"]) or [None])[0]
        if cat and cat != fid:
            print("  ATENÇÃO forania: cabeçalho", fid, "x site", cat, p["slug"])
        nome = limpa(p["nome"])
        mun = p.get("municipio") or municipio_de(p["endereco"]) or "Florianópolis"
        sobre = p.get("sobre", [])
        if SEM_TERRITORIO.match(nome):
            fs[fid]["outras"].append({"nome": nome, "endereco": limpa(p["endereco"]), "municipio": mun, "fonte": FONTE.format(p["slug"])})
            continue
        if p["slug"] in ILHA_IDS:  # Ilha: dados já conferidos
            par = dict(ilha_par[ILHA_IDS[p["slug"]]])
            par["municipio"] = "Florianópolis"
            if not any(c["matriz"] for c in par["comunidades"]):  # site não marcou a matriz (ex.: Necessidades)
                alvo = norm_tokens(re.sub(r"^Paróquia\s+", "", par["nome"]))
                for c in par["comunidades"]:
                    if norm_tokens(c["nome"]) == alvo:
                        c["matriz"] = True; break
            par["ilha"] = True
            par.update(redes.get(p["slug"], {}))
            fs[fid]["paroquias"].append(par)
            for c in par["comunidades"]:
                todas_igrejas.append((par, c))
                if "lat" not in c and c.get("bairro"):
                    # bairro conhecido: procura a igreja com o mesmo nome dentro de 1,5 km do centro do bairro
                    pb = next(f["properties"]["ponto"] for f in ilha_geo["features"] if f["properties"]["bairro"] == c["bairro"])
                    achado = casa_osm(c["nome"], tuple(pb), 1.5)
                    if achado:
                        c.update({"lat": round(achado[0]["lat"], 6), "lng": round(achado[0]["lng"], 6), "posicao": "osm", "nome_osm": achado[0]["nome"], "_d": achado[1]})
                        print("  Ilha, achada no OSM:", par["id"], "|", c["nome"], "|", c["bairro"], "->", achado[0]["nome"], round(achado[1], 2), "km")
                if "lat" not in c and not c.get("bairro"):
                    # sem bairro identificado à mão: tenta a igreja no OSM perto da matriz, depois a localidade
                    mz = next((x for x in par["comunidades"] if x["matriz"] and "lat" in x), None)
                    if mz:
                        cz = (mz["lat"], mz["lng"])
                    else:
                        bm = next(x["bairro"] for x in par["comunidades"] if x["matriz"])
                        cz = tuple(next(f["properties"]["ponto"] for f in ilha_geo["features"] if f["properties"]["bairro"] == bm))
                    achado = None  # na Ilha há muitas igrejas com o mesmo nome: só a localidade é confiável
                    x = localidade_valida(c["local"], "Florianópolis")
                    if x and km((float(x["lat"]), float(x["lon"])), cz) > 8:
                        x = None
                    if achado:
                        c.update({"lat": round(achado[0]["lat"], 6), "lng": round(achado[0]["lng"], 6), "posicao": "osm", "nome_osm": achado[0]["nome"]})
                    elif x:
                        c.update({"lat": round(float(x["lat"]), 6), "lng": round(float(x["lon"]), 6), "posicao": "localidade", "local_osm": f'{x.get("name")} ({x.get("addresstype")})'})
                    else:
                        c["posicao"] = "aprox"
                    print("  Ilha sem bairro:", par["id"], "|", c["nome"], "|", c["local"], "->", c["posicao"], c.get("nome_osm") or c.get("local_osm") or "")
            continue
        base = re.sub(r"^paroquia-", "", p["slug"])
        pid, n = base, 2
        while pid in usados:
            pid, n = f"{base}-{n}", n + 1
        usados.add(pid)
        criada = campo(sobre, "(Criada")
        par = {"id": pid, "nome": nome, "municipio": mun, "endereco": limpa(p["endereco"]),
               "paroco": campo(sobre, "Pároco") or campo(sobre, "Administrador"),
               "criada": criada.strip("()") if criada else None, "fonte": FONTE.format(p["slug"]), "comunidades": []}
        # ----- posição da matriz pelo endereço (só se a rua e o município baterem) -----
        end = re.sub(r"(CEP:?\s*)?\d{5}-?\d{3}|Caixa Postal[^–|]*|Cx\. Postal[^–|]*", " ", p["endereco"])
        rua = re.split(r"[–\-|;]", end)[0].strip()
        r_end = q({"street": rua[:120], "city": mun, "state": "Santa Catarina", "country": "Brasil", "limit": 1, "addressdetails": 1}) or []
        pos_end = None
        if r_end and endereco_bate(rua, r_end[0], mun):
            pos_end = (float(r_end[0]["lat"]), float(r_end[0]["lon"]))
        area_mun = mun_geom.get(mun)
        coms = p["comunidades"]
        tem_matriz = any(re.search(r"^matriz|\(matriz\)", limpa(c["nome"]).lower()) for c in coms)
        if not tem_matriz:
            # o site não marca a matriz: é a comunidade com o mesmo nome da paróquia; se não houver, cria uma
            alvo = norm_tokens(re.sub(r"^Paróquia\s+|\(.*?\)", "", nome))
            iguais = [c for c in coms if norm_tokens(c["nome"]) == alvo]
            if len(iguais) >= 1:
                coms = [dict(c, nome="Matriz: " + limpa(c["nome"])) if c is iguais[0] else c for c in coms]
            else:
                coms = [{"nome": "Matriz: " + re.sub(r"^Paróquia\s+", "", nome), "local": "Centro" if p["comunidades"] else mun, "ano": None}] + coms
                print("  matriz criada:", nome)
        vistos = set()
        coms = sorted(coms, key=lambda c: not re.search(r"^matriz|\(matriz\)", limpa(c["nome"]).lower()))  # matriz primeiro
        for c in coms:
            n = limpa(c["nome"])
            chave_rep = (re.sub(r"^matriz:?\s*|\s*\(matriz\)", "", n.lower()).strip(), limpa(c.get("local")).lower())
            if chave_rep in vistos:
                print("  repetida no site:", nome, "|", n, "|", c.get("local"))
                continue
            vistos.add(chave_rep)
            matriz = bool(re.search(r"^matriz|\(matriz\)", n.lower()))
            n = re.sub(r"^Matriz:?\s*|\s*\(Matriz\)", "", n).strip()
            loc = limpa(c.get("local"))
            if not n:
                n = f"Comunidade de {loc} (nome não informado no site)"
            item = {"nome": n, "local": loc, "ano": c.get("ano") or None, "matriz": matriz}
            # referência: endereço (matriz) ou localidade validada
            ref, ref_tipo = None, None
            if matriz and pos_end:
                ref, ref_tipo = pos_end, "endereco"
            else:
                x = localidade_valida(loc, mun)
                if x:
                    ref, ref_tipo = (float(x["lat"]), float(x["lon"])), "localidade"
                    item["_achado"] = f'{x.get("name")} ({x.get("addresstype")})'
            achado = None
            if ref:
                achado = casa_osm(n, ref, 1.5 if ref_tipo == "endereco" else 3)
            if not achado and area_mun is not None and nomes_mun[(mun, frozenset(norm_tokens(n)))] <= 1:
                achado = casa_osm(n, None, None, area=area_mun.buffer(0.01))
            if ref:
                item["_ref"], item["_ref_tipo"] = ref, ref_tipo
            if achado:
                o, dist = achado
                item.update({"lat": round(o["lat"], 6), "lng": round(o["lng"], 6), "posicao": "osm", "nome_osm": o["nome"], "_d": dist})
            elif ref:
                item.update({"lat": round(ref[0], 6), "lng": round(ref[1], 6), "posicao": ref_tipo})
                if ref_tipo == "localidade":
                    item["local_osm"] = item.get("_achado")
            else:
                item["posicao"] = "aprox"
            par["comunidades"].append(item)
            todas_igrejas.append((par, item))
        if not any(c["matriz"] and "lat" in c for c in par["comunidades"]) and pos_end is None and area_mun is not None:
            c0 = area_mun.representative_point()
            pos_end = (c0.y, c0.x)
        par["_pos_end"] = pos_end
        par.update(redes.get(p["slug"], {}))
        par["comunidades"].sort(key=lambda c: (not c["matriz"], c["nome"]))
        fs[fid]["paroquias"].append(par)

    # Uma igreja do OSM serve a uma comunidade só (a mais próxima da localidade informada).
    # Exceção: o site repete a mesma comunidade (mesmo nome e localidade) na mesma paróquia.
    por_osm = defaultdict(list)
    for par, c in todas_igrejas:
        if c.get("posicao") == "osm" and "_d" in c:
            por_osm[(c["lat"], c["lng"])].append((par, c))
    for lista in por_osm.values():
        if len(lista) < 2:
            continue
        lista.sort(key=lambda t: (not t[1]["matriz"], norm_seq(t[1]["nome"]) != norm_seq(t[1].get("nome_osm")), t[1]["_d"]))
        # mesma igreja listada por duas paróquias (mesmo nome e mesma localidade): todas ficam com o ponto
        iguais = [x for x in lista[1:] if norm_seq(x[1]["nome"]) == norm_seq(lista[0][1]["nome"]) and toks(x[1]["local"], False) == toks(lista[0][1]["local"], False)]
        lista = [lista[0]] + [x for x in lista[1:] if x not in iguais]
        if len(lista) < 2:
            continue
        empate = not lista[0][1]["matriz"] and (norm_seq(lista[0][1]["nome"]) == norm_seq(lista[1][1]["nome"]) and abs(lista[1][1]["_d"] - lista[0][1]["_d"]) < 0.5
                  and lista[0][1]["_d"] < 90)
        if empate:  # duas comunidades com o mesmo nome quase à mesma distância: não dá para saber qual é
            print("  igreja do OSM ambígua, ninguém fica:", lista[0][1].get("nome_osm"), [(x[0]["id"], x[1]["nome"]) for x in lista])
        for par, c in (lista if empate else lista[1:]):
            print("  igreja do OSM disputada:", c.get("nome_osm"), "| fica com", lista[0][0]["id"], lista[0][1]["nome"], "| perde", par["id"], c["nome"])
            for k2 in ("lat", "lng", "nome_osm", "_d"):
                c.pop(k2, None)
            if "_ref" in c:
                c["lat"], c["lng"], c["posicao"] = round(c["_ref"][0], 6), round(c["_ref"][1], 6), c["_ref_tipo"]
            else:
                c["posicao"] = "aprox"
    # Posição só pela localidade, mas fora do município da paróquia: nome repetido em outra cidade -> perto da matriz
    for f in fs.values():
        for par in f["paroquias"]:
            if par.get("ilha"):
                continue
            mz = next((x for x in par["comunidades"] if x["matriz"] and "lat" in x), None)
            fora = [c for c in par["comunidades"] if c.get("posicao") == "localidade" and municipio_do_ponto(c["lat"], c["lng"]) not in (par["municipio"], None)]
            for j, c in enumerate(fora):
                print("  localidade em outro município:", par["id"], c["nome"], c["local"], municipio_do_ponto(c["lat"], c["lng"]))
                c.pop("lat", None); c.pop("lng", None); c["posicao"] = "aprox"

    # Comunidade longe demais da sua matriz: localidade homônima em outro lugar -> volta para perto da matriz
    for f in fs.values():
        for par in f["paroquias"]:
            if par.get("ilha"):
                continue
            mz = next((x for x in par["comunidades"] if x["matriz"] and "lat" in x), None)
            if not mz:
                continue
            def suspeita(c):
                if c["matriz"] or "lat" not in c or c["posicao"] == "aprox":
                    return False
                m = municipio_do_ponto(c["lat"], c["lng"])
                d = km((c["lat"], c["lng"]), (mz["lat"], mz["lng"]))
                if m == par["municipio"]:
                    return par["municipio"] == "Florianópolis" and d > 7
                return not (c["posicao"] == "osm" and d <= 12)
            soltas = [c for c in par["comunidades"] if suspeita(c)]
            for j, c in enumerate(soltas):
                print("  longe da matriz:", par["id"], c["nome"], c["local"])
                c.pop("lat", None); c.pop("lng", None); c.pop("nome_osm", None); c["posicao"] = "aprox"
    for par, c in todas_igrejas:
        if c.get("posicao") != "localidade":
            c.pop("local_osm", None)
        for k2 in ("_d", "_pid", "_ref", "_ref_tipo", "_achado"):
            c.pop(k2, None)

    # Endereços publicados nos sites das próprias paróquias (scripts/enderecos_dos_sites.py + geocodificar_enderecos_sites.py)
    arq_end = D / "enderecos_filtrados.json"
    end_sites = json.loads(arq_end.read_text(encoding="utf-8")) if arq_end.exists() else {}
    ponto_bairro = {f["properties"]["bairro"]: f["properties"]["ponto"] for f in ilha_geo["features"]}
    revisar = []
    for par, c in todas_igrejas:
        e = end_sites.get(f"{par['id']}|{c['nome']}|{c['local']}")
        if not e or not e.get("resultado"):
            continue
        x = e["resultado"]
        if not endereco_bate(e["rua"], x, par["municipio"]) and not (x.get("type") == "place_of_worship" and mesmo_municipio(x, par["municipio"])):
            continue
        pos = (float(x["lat"]), float(x["lon"]))
        if "lat" in c:
            atual = (c["lat"], c["lng"])
        elif c.get("bairro") in ponto_bairro:
            atual = tuple(ponto_bairro[c["bairro"]])
        else:
            atual = None
        mz = next((y for y in par["comunidades"] if y["matriz"] and "lat" in y), None)
        d_atual = km(pos, atual) if atual else None
        bb = [float(v) for v in x.get("boundingbox", [pos[0], pos[0], pos[1], pos[1]])]
        via_longa = km((bb[0], bb[2]), (bb[1], bb[3])) > 1.5 and x.get("type") != "place_of_worship"
        if via_longa:
            c["endereco_site"] = e["texto"]  # meio de uma via longa não serve como posição; só registra o endereço
            continue
        if atual and c.get("posicao") in ("osm", None) and d_atual > 3:
            revisar.append(f"{par['id']} | {c['nome']} | {c['local']} | site: {e['texto'][:60]} | {d_atual:.1f} km da posição atual ({c.get('posicao')})")
            continue
        if mz and not c["matriz"] and km(pos, (mz["lat"], mz["lng"])) > (8 if par["municipio"] == "Florianópolis" else 25):
            revisar.append(f"{par['id']} | {c['nome']} | longe da matriz pelo endereço do site: {e['texto'][:60]}")
            continue
        exato = x.get("type") == "place_of_worship" or (e.get("numero") and (x.get("address") or {}).get("house_number") == e["numero"])
        if c.get("posicao") in ("osm", "endereco") and "lat" in c:
            c["endereco_site"] = e["texto"]  # igreja já no ponto exato: o endereço do site só confirma
            continue
        c.update({"lat": round(pos[0], 6), "lng": round(pos[1], 6), "posicao": "endereco" if exato else "rua", "endereco_site": e["texto"]})
        c.pop("nome_osm", None)
    if revisar:
        print("  PARA REVISAR (endereço do site x posição atual):")
        for r0 in revisar:
            print("   ", r0)

    # CNEFE 2022 (IBGE): estabelecimentos religiosos com nome, localidade e coordenada (scripts/baixar_cnefe.py)
    arq_cn = D / "cnefe_religiosos.json"
    cnefe = json.loads(arq_cn.read_text(encoding="utf-8")) if arq_cn.exists() else []
    GENERICO = re.compile(r"^(IGREJA|CAPELA|ORATORIO|COMUNIDADE|IGREJA CATOLICA|CAPELA CATOLICA|COMUNIDADE CATOLICA|IGREJA MATRIZ|TEMPLO)?$")
    for r0 in cnefe:
        r0["seq"] = norm_seq(r0["nome"])
        r0["outra"] = bool(NAO_CATOLICA.search(r0["nome"])) or bool(re.search(r"SALAO|GALPAO|ANEXO|CENTRO COMUNIT|CEMITERIO|ESCOLA|CRECHE", r0["nome"].upper()))
        r0["loc"] = toks(r0["localidade"], False)
    por_mun_cn = defaultdict(list)
    for r0 in cnefe:
        por_mun_cn[r0["municipio"]].append(r0)
    usados_cn = {}
    stats_cn = Counter()
    for par, c in todas_igrejas:
        if c.get("posicao") in ("osm", "endereco"):
            continue
        mun = c.get("municipio") or par["municipio"]
        cands = [r0 for r0 in por_mun_cn.get(par["municipio"], []) + (por_mun_cn.get(mun, []) if mun != par["municipio"] else []) if not r0["outra"]]
        sq = norm_seq(c["nome"])
        loc_c = toks(c["local"], False)
        def loc_ok(r0):
            return bool(loc_c) and bool(r0["loc"]) and (loc_c <= r0["loc"] or r0["loc"] <= loc_c)
        # 1) pelo nome
        nomeados = [r0 for r0 in cands if sq and (contido(sq, r0["seq"]) or (len(r0["seq"]) >= 2 and contido(r0["seq"], sq) and len(r0["seq"]) >= 0.6 * len(sq)))]
        com_loc = [r0 for r0 in nomeados if loc_ok(r0)]
        escolha, como = None, None
        if len(com_loc) == 1:
            escolha, como = com_loc[0], "nome e localidade"
        else:
            inteiros = [r0 for r0 in nomeados if contido(sq, r0["seq"])]  # nome da comunidade inteiro no nome do CNEFE
            if len(inteiros) == 1 and len([x for x in todas_igrejas if (x[0]["municipio"] == par["municipio"]) and norm_seq(x[1]["nome"]) == sq]) == 1:
                escolha, como = inteiros[0], "nome (único no município)"
        # 1b) pelo nome, perto do centro da localidade informada (quando há várias com o mesmo nome no município)
        if not escolha and c.get("posicao") == "localidade" and "lat" in c:
            perto = [r0 for r0 in nomeados if contido(sq, r0["seq"]) and km((r0["lat"], r0["lng"]), (c["lat"], c["lng"])) <= 2]
            if len(perto) == 1:
                escolha, como = perto[0], "nome, perto da localidade"
        # 2) igreja sem nome no CNEFE, mas única na localidade
        if not escolha and loc_c and not loc_c <= toks(par["municipio"], False) and loc_c != {"centro"}:
            na_loc = [r0 for r0 in cnefe if r0["municipio"] == par["municipio"] and loc_ok(r0) and (r0["especie"] == "8" or not GENERICO.match(r0["nome"].upper()) is None)]
            catolicas = [r0 for r0 in na_loc if not r0["outra"]]
            genericas = [r0 for r0 in catolicas if GENERICO.match(r0["nome"].upper())]
            if len(catolicas) == 1 and len(genericas) == 1 and len(na_loc) == 1:
                escolha, como = genericas[0], "única igreja da localidade"
        if not escolha:
            continue
        chave_cn = (escolha["lat"], escolha["lng"])
        if chave_cn in usados_cn and usados_cn[chave_cn] is not c:
            stats_cn["disputada"] += 1
            continue
        # conferência com o que já se sabe da comunidade
        mzc = next((y for y in par["comunidades"] if y["matriz"] and "lat" in y and y is not c), None)
        if como == "nome (único no município)":
            if "lat" in c and c.get("posicao") in ("rua", "localidade") and km((c["lat"], c["lng"]), chave_cn) > 2.5:
                stats_cn["longe"] += 1
                print("  CNEFE (nome único) longe da localidade:", par["id"], "|", c["nome"], "|", c["local"], "->", escolha["nome"], escolha["localidade"])
                continue
            if mzc and km((mzc["lat"], mzc["lng"]), chave_cn) > (12 if par["municipio"] == "Florianópolis" else 15):
                stats_cn["longe"] += 1
                print("  CNEFE (nome único) longe da matriz:", par["id"], "|", c["nome"], "->", escolha["nome"], escolha["localidade"])
                continue
        mesma_rua = bool(c.get("endereco_site")) and bool(toks(escolha["logradouro"])) and toks(escolha["logradouro"]) <= toks(c["endereco_site"])
        if c.get("posicao") == "rua" and km((c["lat"], c["lng"]), chave_cn) > 1 and not mesma_rua:
            stats_cn["rua do site vence"] += 1
            print("  endereço do site x CNEFE (fica o do site):", par["id"], "|", c["nome"], "|", c.get("endereco_site"), "x", escolha["nome"], escolha["localidade"])
            continue
        if "lat" in c and c.get("posicao") in ("rua", "localidade") and km((c["lat"], c["lng"]), chave_cn) > 6:
            stats_cn["longe"] += 1
            print("  CNEFE longe da posição atual:", par["id"], "|", c["nome"], "|", c["local"], "->", escolha["nome"], escolha["localidade"])
            continue
        usados_cn[chave_cn] = c
        c.update({"lat": round(escolha["lat"], 6), "lng": round(escolha["lng"], 6), "posicao": "cnefe",
                  "cnefe": f'{escolha["nome"] or "estabelecimento religioso"} · {escolha["logradouro"]}{(", " + escolha["numero"]) if escolha["numero"] not in ("0", "", None) else ""} · {escolha["localidade"]} ({como})'})
        c.pop("nome_osm", None)
        stats_cn[como] += 1
    print("  CNEFE:", dict(stats_cn))

    # Correções manuais conferidas (dados/arquidiocese/correcoes.json)
    corr = json.loads((D / "correcoes.json").read_text(encoding="utf-8")) if (D / "correcoes.json").exists() else {}
    usadas_corr = set()
    for par, c in todas_igrejas:
        k3 = f"{par['id']}|{c['nome']}|{c['local']}"
        if k3 in corr.get("posicoes", {}):
            v = corr["posicoes"][k3]
            c.update({"lat": v["lat"], "lng": v["lng"], "posicao": v["posicao"]})
            if v["posicao"] == "cnefe":
                c["cnefe"] = v["fonte"].replace("CNEFE 2022: ", "")
            c.pop("nome_osm", None)
            if v.get("nome_osm"):
                c["nome_osm"] = v["nome_osm"]
            usadas_corr.add(k3)
    faltou = set(corr.get("posicoes", {})) - usadas_corr
    assert not faltou, f"correções sem igreja: {faltou}"

    # Sem posição confiável: em volta da matriz da paróquia
    for f in fs.values():
        for par in f["paroquias"]:
            if par.get("ilha"):
                mz = next((c for c in par["comunidades"] if c["matriz"] and "lat" in c), None)
                if mz:
                    centro = (mz["lat"], mz["lng"])
                else:  # matriz posicionada só pelo bairro
                    bm = next(c["bairro"] for c in par["comunidades"] if c["matriz"])
                    centro = tuple(next(f["properties"]["ponto"] for f in ilha_geo["features"] if f["properties"]["bairro"] == bm))
                soltas = [c for c in par["comunidades"] if "lat" not in c and not c.get("bairro")]
                for j, c in enumerate(soltas):
                    a = 2 * math.pi * j / max(len(soltas), 1) + 0.4
                    c["lat"], c["lng"], c["posicao"] = round(centro[0] + 0.004 * math.cos(a), 6), round(centro[1] + 0.004 * math.sin(a) / 0.887, 6), "aprox"
                continue
            mz = next((c for c in par["comunidades"] if c["matriz"] and "lat" in c and c["posicao"] != "aprox"), None)
            centro = (mz["lat"], mz["lng"]) if mz else par.get("_pos_end")
            soltas = [c for c in par["comunidades"] if c.get("posicao") == "aprox" or "lat" not in c]
            for j, c in enumerate(soltas):
                if not centro:
                    print("  SEM POSIÇÃO:", par["id"], c["nome"]); continue
                a = 2 * math.pi * j / max(len(soltas), 1) + 0.4
                r = 0.006 + 0.0008 * len(soltas)
                c["lat"], c["lng"], c["posicao"] = round(centro[0] + r * math.cos(a), 6), round(centro[1] + r * math.sin(a) / 0.887, 6), "aprox"
                c.pop("nome_osm", None)
            par.pop("_pos_end", None)

    # Mesma posição para várias igrejas (localidade/município): espalha em círculo pequeno
    grupos = defaultdict(list)
    for par, c in todas_igrejas:
        if par.get("ilha"):
            continue
        if c.get("posicao") in ("localidade", "endereco", "rua") and "lat" in c:
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
    ids = Counter(p["id"] for f in fs.values() for p in f["paroquias"])
    assert all(v == 1 for v in ids.values()), f"ids repetidos: {[k for k, v in ids.items() if v > 1]}"
    print(f"{(RAIZ / 'mapa' / 'dados.json').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
