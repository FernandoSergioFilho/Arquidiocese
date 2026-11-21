# Mapa das Paróquias — Arquidiocese de Florianópolis

Mapa interativo (estilo apuração de eleição) dos bairros da Ilha de Santa Catarina, coloridos por paróquia e por forania.

- `dados/paroquias.json` — hierarquia forania → paróquia → comunidades (editar aqui; campos `conferir` marcam o que falta validar).
- `dados/bairros_ilha.geojson` — bairros da Ilha (IBGE, Censo 2022) com a paróquia atribuída.
- `mapa/index.src.html` — página; `mapa/index.html` é gerado com o CSS do Leaflet embutido.
- `scripts/montar_dados.py <bairros.gpkg> <municipios_sc.geojson>` → gera `mapa/dados.json`.
- `scripts/montar_pagina.py <leaflet.css>` → gera `mapa/index.html`.

Fontes: malha de bairros do IBGE (via catarinacm/pickup-points-florianopolis), municípios de SC (tbrugz/geodata-br), lista de paróquias levantada por busca na web — a conferir no site arquifln.org.br.
Situação de cada bairro: `sede`/`comunidade` = confirmado; `estimado` = herda a paróquia confirmada mais próxima por vizinhança.
