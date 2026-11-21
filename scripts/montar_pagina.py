"""Gera mapa/index.html a partir de mapa/index.src.html, embutindo o CSS do Leaflet 1.9.4.
Uso: python scripts/montar_pagina.py <leaflet.css>"""
import sys, re
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
css = re.sub(r"url\(images/[^)]*\)", "none", Path(sys.argv[1]).read_text(encoding="utf-8"))
src = (RAIZ / "mapa" / "index.src.html").read_text(encoding="utf-8")
(RAIZ / "mapa" / "index.html").write_text(src.replace("/*@@LEAFLET_CSS@@*/", css), encoding="utf-8")
