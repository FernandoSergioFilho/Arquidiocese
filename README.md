# Mapa das Paróquias — Arquidiocese de Florianópolis

Mapa interativo (estilo apuração de eleição) dos bairros da Ilha de Santa Catarina, coloridos por paróquia e por forania.

- `dados/paroquias_site.json` — paróquias e comunidades lidas do site arquifln.org.br (21/11/2026).
- `dados/localidades_bairros.json` — localidade de cada comunidade → bairro do IBGE (feito à mão; `null` = não identificado). Corrigir aqui.
- `dados/paroquias.json` — hierarquia gerada (forania → paróquia → comunidades com bairro).
- `dados/bairros_ilha.geojson` — bairros da Ilha (IBGE, Censo 2022) com a paróquia atribuída.
- `mapa/index.src.html` — página; `mapa/index.html` é gerado com o CSS do Leaflet embutido.
- `scripts/montar_dados.py <bairros.gpkg> <municipios_sc.geojson>` → gera `mapa/dados.json`.
- `scripts/montar_pagina.py <leaflet.css>` → gera `mapa/index.html`.

Fontes: malha de bairros do IBGE (via catarinacm/pickup-points-florianopolis), municípios de SC (tbrugz/geodata-br), paróquias e comunidades do site arquifln.org.br.
Situação de cada bairro: `matriz`/`comunidade` = confirmado; `estimado` = herda a paróquia confirmada mais próxima por vizinhança.
