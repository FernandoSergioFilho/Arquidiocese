"""Ajustes na malha de bairros do IBGE usados pelos scripts de montagem."""
import geopandas as gpd
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

# Nomes do IBGE que confundem: o bairro "Tapera" do IBGE é a Tapera da Barra do Sul, no extremo sul da Ilha
RENOMEAR = {"Tapera": "Tapera da Barra do Sul"}


def ler_bairros(arq):
    g = gpd.read_file(arq)
    g["NM_BAIRRO"] = g["NM_BAIRRO"].replace(RENOMEAR)
    return junta_pedacos_soltos(g)


def junta_pedacos_soltos(g, fracao=0.25):
    """Pedaços pequenos e soltos de um bairro (menos de 25% da maior parte) passam para o vizinho
    com quem dividem a maior fronteira. Ilhotas sem vizinho ficam onde estão."""
    g = g.copy()
    geoms = list(g.geometry)
    for i, geom in enumerate(list(geoms)):
        if geom.geom_type != "MultiPolygon":
            continue
        partes = sorted(geom.geoms, key=lambda p: -p.area)
        fica = [partes[0]]
        for p in partes[1:]:
            if p.area >= fracao * partes[0].area:
                fica.append(p); continue
            melhor, comp = None, 0.0
            for j, outra in enumerate(geoms):
                if j == i:
                    continue
                c = p.buffer(1).intersection(outra.buffer(1)).length if p.buffer(1).intersects(outra) else 0
                if c > comp:
                    melhor, comp = j, c
            if melhor is None or comp < 5:
                fica.append(p)
            else:
                geoms[melhor] = unary_union([geoms[melhor], p.buffer(0.5)]).buffer(-0.5)
        geoms[i] = fica[0] if len(fica) == 1 else MultiPolygon(fica)
    g = g.set_geometry(gpd.GeoSeries(geoms, crs=g.crs))
    return g
