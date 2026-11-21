"""Monta mapa/dados.json a partir da malha de bairros (IBGE, Censo 2022) e de dados/paroquias.json.

Uso: python scripts/montar_dados.py <bairros.gpkg> <municipios_sc.geojson>

- bairros.gpkg: malha de bairros de Florianópolis derivada do IBGE (camada "bairros",
  campos NM_BAIRRO, NM_DIST, REGIAO_FUNCIONAL, POP).
- municipios_sc.geojson: municípios de SC (tbrugz/geodata-br), usado só como fundo.

Cada bairro da Ilha recebe uma situação:
  sede        a igreja matriz de uma paróquia confirmada fica nesse bairro
  comunidade  uma comunidade confirmada da paróquia fica nesse bairro
  estimado    nenhuma paróquia confirmada; herda a do bairro-semente mais próximo
              por vizinhança (busca em largura pelos bairros que se tocam)
"""
import json
import sys
from collections import deque
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping, shape

RAIZ = Path(__file__).resolve().parents[1]
ARQ_PAROQUIAS = RAIZ / "dados" / "paroquias.json"
ARQ_SAIDA = RAIZ / "mapa" / "dados.json"
ARQ_GEOJSON = RAIZ / "dados" / "bairros_ilha.geojson"

VIZINHOS_FUNDO = ["São José", "Palhoça", "Biguaçu", "Governador Celso Ramos", "Santo Amaro da Imperatriz"]
TOLERANCIA_M = 12  # simplificação das bordas, em metros


def arred(geom, casas=5):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], casas), round(c[1], casas)]
        return [r(x) for x in c]
    m = mapping(geom)
    return {"type": m["type"], "coordinates": r(m["coordinates"])}


def main(arq_bairros, arq_municipios):
    hier = json.loads(ARQ_PAROQUIAS.read_text(encoding="utf-8"))
    g = gpd.read_file(arq_bairros)  # EPSG:31982, em metros
    ilha = g[g.REGIAO_FUNCIONAL != "Continente"].reset_index(drop=True)
    continente = g[g.REGIAO_FUNCIONAL == "Continente"]
    nomes = list(ilha.NM_BAIRRO)

    # Sementes: bairro -> (paróquias, forania, situação)
    sementes = {}
    for f in hier["foranias"]:
        for p in f["paroquias"]:
            if p["sede"] not in nomes:
                sys.exit(f"Bairro-sede não encontrado na malha: {p['sede']}")
            s = sementes.setdefault(p["sede"], {"paroquias": [], "forania": f["id"], "situacao": "sede"})
            s["paroquias"].append(p["id"])
            for c in p.get("comunidades", []):
                b = c.get("bairro")
                if b and b not in sementes:
                    sementes[b] = {"paroquias": [p["id"]], "forania": f["id"], "situacao": "comunidade",
                                   "comunidade": c["nome"]}

    # Vizinhança entre bairros (tocam com folga de 30 m)
    buf = ilha.geometry.buffer(30)
    viz = {i: [j for j in buf.sindex.query(buf.iloc[i], predicate="intersects") if j != i] for i in range(len(ilha))}
    cent = ilha.geometry.centroid

    # Busca em largura a partir de todas as sementes; desempate pela distância até a semente
    atrib = {}
    fila = deque()
    for i, n in enumerate(nomes):
        if n in sementes:
            atrib[i] = (0, i)
            fila.append(i)
    while fila:
        i = fila.popleft()
        saltos, origem = atrib[i]
        for j in viz[i]:
            cand = (saltos + 1, origem)
            atual = atrib.get(j)
            if atual is None or (cand[0] == atual[0] and cent.iloc[j].distance(cent.iloc[origem]) < cent.iloc[j].distance(cent.iloc[atual[1]])):
                if atual is None:
                    fila.append(j)
                atrib[j] = cand

    simpl = ilha.geometry.simplify(TOLERANCIA_M).to_crs(4326)
    feats = []
    for i, n in enumerate(nomes):
        props = {"bairro": n, "distrito": ilha.NM_DIST.iloc[i], "pop": int(round(ilha.POP.iloc[i] or 0))}
        if n in sementes:
            props.update(sementes[n])
        elif i in atrib:
            saltos, origem = atrib[i]
            s = sementes[nomes[origem]]
            props.update({"paroquias": s["paroquias"], "forania": s["forania"], "situacao": "estimado",
                          "referencia": nomes[origem], "saltos": saltos})
        else:
            props.update({"paroquias": [], "forania": None, "situacao": "sem-dado"})
        feats.append({"type": "Feature", "properties": props, "geometry": arred(simpl.iloc[i])})

    geo_ilha = {"type": "FeatureCollection", "features": feats}

    # Fundo: continente de Florianópolis (bairros unidos) + municípios vizinhos
    fundo = []
    cont = continente.geometry.union_all().simplify(TOLERANCIA_M)
    fundo.append({"type": "Feature", "properties": {"nome": "Florianópolis (Continente)"},
                  "geometry": arred(gpd.GeoSeries([cont], crs=g.crs).to_crs(4326).iloc[0])})
    mun = json.loads(Path(arq_municipios).read_text(encoding="utf-8"))
    for f in mun["features"]:
        if f["properties"].get("name") in VIZINHOS_FUNDO:
            fundo.append({"type": "Feature", "properties": {"nome": f["properties"]["name"]},
                          "geometry": arred(shape(f["geometry"]), 4)})

    ARQ_GEOJSON.write_text(json.dumps(geo_ilha, ensure_ascii=False), encoding="utf-8")
    dados = {"hierarquia": hier, "bairros": geo_ilha, "fundo": {"type": "FeatureCollection", "features": fundo}}
    ARQ_SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")

    from collections import Counter
    print(Counter(f["properties"]["situacao"] for f in feats), f"{ARQ_SAIDA.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
