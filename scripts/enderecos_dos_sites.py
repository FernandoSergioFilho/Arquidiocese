"""Procura, nos sites das paróquias, o endereço de cada comunidade.
Uso: python scripts/enderecos_dos_sites.py  -> dados/arquidiocese/enderecos_sites.json (candidatos, para conferência)

Para cada comunidade da paróquia: acha o nome no texto (palavras na mesma ordem) e pega o primeiro endereço
(Rua, Av., Rodovia, Servidão, Estrada, Travessa, Praça...) nas linhas seguintes, antes do nome de outra comunidade."""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
from montar_arquidiocese import contido, norm_seq  # noqa: E402

D = RAIZ / "dados" / "arquidiocese"
END = re.compile(r"\b(Rua|R\.|Avenida|Av\.?|Rodovia|Rod\.|SC[- ]?\d{3}|BR[- ]?\d{3}|Estrada|Servid[aã]o|Travessa|Tv\.|Pra[cç]a|Alameda|"
                 r"Largo|Caminho|Loteamento|Rua Geral)\b[^\n]{3,120}", re.I)
hier = json.loads((D / "hierarquia.json").read_text(encoding="utf-8"))
slug_de = {p["fonte"].rstrip("/").rsplit("/", 1)[1]: p for f in hier["foranias"] for p in f["paroquias"]}
saida = {}
for arq in sorted((D / "sites").glob("*.json")):
    p = slug_de.get(arq.stem)
    if not p:
        continue
    paginas = json.loads(arq.read_text(encoding="utf-8"))
    nomes = [(c, norm_seq(c["nome"])) for c in p["comunidades"]]
    for url, txt in paginas.items():
        linhas = txt.split("\n")
        seqs = [norm_seq(l) for l in linhas]
        for i, sq in enumerate(seqs):
            for c, ns in nomes:
                if not ns or not contido(ns, sq) or len(linhas[i]) > 160:
                    continue
                # outra comunidade com nome mais longo que também casa nesta linha? então não é esta
                if any(len(n2) > len(ns) and contido(n2, sq) and contido(ns, n2) for _, n2 in nomes):
                    continue
                for j in range(i, min(i + 7, len(linhas))):
                    if j > i and any(contido(n2, seqs[j]) for _, n2 in nomes if n2):
                        break  # começou outra comunidade
                    m = END.search(linhas[j])
                    if m:
                        k = f"{p['id']}|{c['nome']}|{c['local']}"
                        saida.setdefault(k, []).append({"endereco": m.group(0).strip(" .;,"), "linha_nome": linhas[i][:120], "url": url})
                        break
for k in saida:  # sem repetidos
    vistos, uni = set(), []
    for x in saida[k]:
        if x["endereco"].lower() not in vistos:
            vistos.add(x["endereco"].lower()); uni.append(x)
    saida[k] = uni
(D / "enderecos_sites.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(saida), "comunidades com endereço candidato")
