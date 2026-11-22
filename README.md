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
- O mapa não usa divisão por bairro. Em todos os municípios, a área de cada paróquia é aproximada (Voronoi das suas igrejas, recortado pelo município; em Florianópolis, só a parte em terra). Os bairros do IBGE servem apenas para posicionar as igrejas da Ilha conhecidas só pelo bairro (`bairro`).
- Demais municípios: o site não publica limites de paróquia. A área de cada paróquia é aproximada pelas regiões mais próximas das suas igrejas (Voronoi), recortadas pelo limite do município (OpenStreetMap).

## Posição das igrejas
- `osm`: igreja encontrada no OpenStreetMap pelo nome, perto da localidade informada pelo site.
- `endereco`: matriz posicionada pelo endereço da paróquia.
- `localidade`: centro da localidade (bairro, vila) informada pelo site.
- `aprox`: localidade não encontrada; marcador perto da matriz.

Fontes: Arquidiocese de Florianópolis; IBGE; © colaboradores do OpenStreetMap (ODbL).

## Verificação
- `python scripts/verificar.py` — confere ids, contagem de comunidades contra o site, forania (maioria entre cabeçalho da paróquia, classificação interna do site e lista da forania), posição das matrizes, nomes das igrejas do OSM, coordenadas repetidas, distâncias até a matriz e áreas. Grava `dados/arquidiocese/relatorio_verificacao.txt`.
- `testes/teste_navegador.js` — abre a página (Playwright) e seleciona cada paróquia, cada igreja, cada área e cada forania, conferindo painel, janelas e para onde o mapa vai.
- Regras de posição: localidade só vale se o resultado tiver o mesmo nome e estiver no mesmo município; endereço só vale se a rua e a cidade baterem; igreja do OSM só com o nome na mesma ordem, perto da localidade (ou única no município, quando o nome também é único entre as comunidades do município); cada igreja do OSM serve a uma comunidade só.
- `dados/arquidiocese/correcoes.json` — posições conferidas à mão.
- `scripts/baixar_cnefe.py` — estabelecimentos religiosos do CNEFE 2022 (IBGE) nos municípios da Arquidiocese (`dados/arquidiocese/cnefe_religiosos.json`). Usados por nome + localidade, nome único no município (conferido pela distância) ou "única igreja da localidade".
- `scripts/ler_sites_paroquias.py`, `scripts/enderecos_dos_sites.py`, `scripts/geocodificar_enderecos_sites.py` — endereços publicados nos sites das paróquias.
