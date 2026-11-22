# Mapa das Paróquias — Arquidiocese de Florianópolis

Mapa interativo (estilo Google Maps) com as 13 foranias, as paróquias e todas as igrejas e comunidades da Arquidiocese de Florianópolis.

## Como gerar
1. `python scripts/geocodificar_arquidiocese.py` — consulta o Nominatim (OpenStreetMap) e guarda tudo em `dados/arquidiocese/geocache.json` (pode ser interrompido e retomado).
2. `python scripts/montar_dados.py <bairros.gpkg> <municipios_sc.geojson>` — Ilha de Santa Catarina (bairros do IBGE, conferência manual).
3. `python scripts/montar_arquidiocese.py <bairros.gpkg> <municipios_sc.geojson>` — junta a Ilha com o resto da Arquidiocese e gera `mapa/dados.json`.
4. `python scripts/montar_pagina.py <leaflet.css>` — gera `mapa/index.html` a partir de `mapa/index.src.html`.

## Dados
- `dados/arquidiocese/paroquias_site.json` — 83 páginas de paróquias, capelanias, reitoria e santuário do site arquifln.org.br (lidas em 21/11/2026).
- `dados/arquidiocese/foranias_links.txt` — paróquias listadas em cada página de forania.
- `dados/arquidiocese/hierarquia.json` — hierarquia final (forania → paróquia → igrejas, com posição).
- `dados/paroquias_site.json`, `dados/localidades_bairros.json`, `dados/coordenadas_igrejas.json` — Ilha, com correspondências conferidas uma a uma.

## Como as áreas são desenhadas
- Florianópolis (Ilha e Continente): bairros oficiais do IBGE (Censo 2022), pintados pela paróquia da igreja que fica no bairro; sem igreja, herda do bairro vizinho ("estimado").
- Demais municípios: o site não publica limites de paróquia. A área de cada paróquia é aproximada pelas regiões mais próximas das suas igrejas (Voronoi), recortadas pelo limite do município (OpenStreetMap).

## Posição das igrejas
- `osm`: igreja encontrada no OpenStreetMap pelo nome, perto da localidade informada pelo site.
- `endereco`: matriz posicionada pelo endereço da paróquia.
- `localidade`: centro da localidade (bairro, vila) informada pelo site.
- `aprox`: localidade não encontrada; marcador perto da matriz.

Fontes: Arquidiocese de Florianópolis; IBGE; © colaboradores do OpenStreetMap (ODbL).
