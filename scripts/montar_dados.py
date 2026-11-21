"""Monta mapa/dados.json: hierarquia Arquidiocese -> forania -> paróquia -> comunidade, e os bairros da Ilha.

Uso: python scripts/montar_dados.py <bairros.gpkg> <municipios_sc.geojson>

Entradas do repositório:
  dados/paroquias_site.json        paróquias e comunidades lidas do site arquifln.org.br (21/11/2026)
  dados/localidades_bairros.json   localidade de cada comunidade -> bairro oficial do IBGE

Situação de cada bairro da Ilha:
  matriz      a igreja matriz de uma paróquia fica no bairro
  comunidade  pelo menos uma comunidade fica no bairro
  estimado    nenhuma comunidade localizada; herda a paróquia do bairro confirmado mais
              próximo por vizinhança (busca em largura pelos bairros que se tocam)
"""
import json
import re
import sys
from collections import Counter, deque
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping, shape

RAIZ = Path(__file__).resolve().parents[1]
ARQ_SITE = RAIZ / "dados" / "paroquias_site.json"
ARQ_LOCAIS = RAIZ / "dados" / "localidades_bairros.json"
ARQ_SAIDA = RAIZ / "mapa" / "dados.json"
ARQ_GEOJSON = RAIZ / "dados" / "bairros_ilha.geojson"
FONTE = "https://arquifln.org.br/igrejas/{}/"

IDS = {
    "paroquia-nossa-senhora-do-desterro-e-santa-catarina": "desterro",
    "paroquia-santo-antonio": "santo-antonio",
    "paroquia-santa-teresinha-do-menino-jesus": "santa-teresinha",
    "paroquia-nossa-senhora-de-lourdes-e-sao-luis-gonzaga": "lourdes",
    "paroquia-nossa-senhora-da-boa-viagem": "boa-viagem",
    "paroquia-nossa-senhora-da-lapa": "lapa",
    "paroquia-nossa-senhora-do-sagrado-coracao": "sagrado-coracao",
    "paroquia-nossa-senhora-da-imaculada-conceicao-da-lagoa": "lagoa",
    "paroquia-nossa-senhora-das-necessidades": "necessidades",
    "paroquia-nossa-senhora-de-guadalupe": "guadalupe",
    "paroquia-sagrado-coracao-de-jesus": "ingleses",
    "paroquia-santissima-trindade": "trindade",
    "paroquia-sao-francisco-xavier": "sao-francisco-xavier",
}
FORANIAS = {
    "centro-sul": ("Forania Florianópolis Centro-Sul", "https://arquifln.org.br/organizacao/1070-2/florianopolis-centro-sul/"),
    "norte": ("Forania Florianópolis Norte", "https://arquifln.org.br/organizacao/1070-2/florianopolis-norte/"),
}
VIZINHOS_FUNDO = ["São José", "Palhoça", "Biguaçu", "Governador Celso Ramos", "Santo Amaro da Imperatriz"]
TOLERANCIA_M = 12


def arred(geom, casas=5):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], casas), round(c[1], casas)]
        return [r(x) for x in c]
    m = mapping(geom)
    return {"type": m["type"], "coordinates": r(m["coordinates"])}


def limpa(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def forania_id(txt):
    return "centro-sul" if "Centro" in txt else "norte"


def campo(sobre, prefixo):
    for s in sobre:
        if s.startswith(prefixo):
            return limpa(s.split(":", 1)[1]) if ":" in s else limpa(s)
    return None


def hierarquia():
    site = json.loads(ARQ_SITE.read_text(encoding="utf-8"))
    locais = json.loads(ARQ_LOCAIS.read_text(encoding="utf-8"))
    fs = {k: {"id": k, "nome": v[0], "fonte": v[1], "paroquias": [], "outras": []} for k, v in FORANIAS.items()}
    for p in site:
        f = fs[forania_id(p["forania"])]
        nome = limpa(p["nome"])
        if p["slug"] not in IDS:  # capelanias militares e reitoria: sem território
            f["outras"].append({"nome": nome, "endereco": limpa(p["endereco"]), "fonte": FONTE.format(p["slug"])})
            continue
        coms = []
        for c in p["comunidades"]:
            n = limpa(c["nome"])
            matriz = n.lower().startswith("matriz")
            n = re.sub(r"^Matriz:?\s*", "", n)
            coms.append({"nome": n, "local": limpa(c.get("local", "")), "ano": c.get("ano") or None,
                         "bairro": locais.get(c.get("local")), "matriz": matriz})
        coms.sort(key=lambda c: (not c["matriz"], c["nome"]))
        criada = campo(p["sobre"], "(Criada")
        f["paroquias"].append({
            "id": IDS[p["slug"]], "nome": nome, "endereco": limpa(p["endereco"]),
            "paroco": campo(p["sobre"], "Pároco"), "criada": criada.strip("()") if criada else None,
            "fonte": FONTE.format(p["slug"]), "comunidades": coms,
        })
    return {"arquidiocese": "Arquidiocese de Florianópolis", "lido_em": "2026-11-21",
            "foranias": [fs["centro-sul"], fs["norte"]]}


def main(arq_bairros, arq_municipios):
    hier = hierarquia()
    g = gpd.read_file(arq_bairros)
    ilha = g[g.REGIAO_FUNCIONAL != "Continente"].reset_index(drop=True)
    continente = g[g.REGIAO_FUNCIONAL == "Continente"]
    nomes = list(ilha.NM_BAIRRO)

    # Paróquias presentes em cada bairro, a partir das comunidades localizadas
    presenca, matriz_em, forania_de = {}, {}, {}
    for f in hier["foranias"]:
        for p in f["paroquias"]:
            forania_de[p["id"]] = f["id"]
            for c in p["comunidades"]:
                b = c["bairro"]
                if not b:
                    continue
                assert b in nomes, b
                presenca.setdefault(b, Counter())[p["id"]] += 1
                if c["matriz"]:
                    matriz_em.setdefault(b, []).append(p["id"])

    def principal(b):
        if b in matriz_em:
            return matriz_em[b][0]
        return presenca[b].most_common(1)[0][0]

    buf = ilha.geometry.buffer(30)
    viz = {i: [j for j in buf.sindex.query(buf.iloc[i], predicate="intersects") if j != i] for i in range(len(ilha))}
    cent = ilha.geometry.centroid
    atrib, fila = {}, deque()
    for i, n in enumerate(nomes):
        if n in presenca:
            atrib[i] = (0, i)
            fila.append(i)
    while fila:
        i = fila.popleft()
        saltos, origem = atrib[i]
        for j in viz[i]:
            atual = atrib.get(j)
            if atual is None:
                atrib[j] = (saltos + 1, origem)
                fila.append(j)
            elif atual[0] == saltos + 1 and cent.iloc[j].distance(cent.iloc[origem]) < cent.iloc[j].distance(cent.iloc[atual[1]]):
                atrib[j] = (saltos + 1, origem)

    simpl = ilha.geometry.simplify(TOLERANCIA_M).to_crs(4326)
    feats = []
    for i, n in enumerate(nomes):
        rp = simpl.iloc[i].representative_point()
        props = {"bairro": n, "distrito": ilha.NM_DIST.iloc[i], "pop": int(round(ilha.POP.iloc[i] or 0)),
                 "ponto": [round(rp.y, 5), round(rp.x, 5)]}
        if n in presenca:
            pr = principal(n)
            props.update({"principal": pr, "paroquias": [pr] + [x for x in presenca[n] if x != pr],
                          "situacao": "matriz" if n in matriz_em else "comunidade"})
        else:
            saltos, origem = atrib[i]
            pr = principal(nomes[origem])
            props.update({"principal": pr, "paroquias": [pr], "situacao": "estimado",
                          "referencia": nomes[origem], "saltos": saltos})
        props["forania"] = forania_de[props["principal"]]
        feats.append({"type": "Feature", "properties": props, "geometry": arred(simpl.iloc[i])})
    geo_ilha = {"type": "FeatureCollection", "features": feats}

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
    (RAIZ / "dados" / "paroquias.json").write_text(json.dumps(hier, ensure_ascii=False, indent=1), encoding="utf-8")
    dados = {"hierarquia": hier, "bairros": geo_ilha, "fundo": {"type": "FeatureCollection", "features": fundo}}
    ARQ_SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(Counter(f["properties"]["situacao"] for f in feats), f"{ARQ_SAIDA.stat().st_size/1024:.0f} KB")
    for f in feats:
        p = f["properties"]
        print(f"{p['bairro']:28} {p['situacao']:11} {','.join(p['paroquias']):40} {p.get('referencia','')}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
