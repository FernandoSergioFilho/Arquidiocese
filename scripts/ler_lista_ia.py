"""Lê a lista de igrejas gerada pelo modo IA do Google (PDF convertido com pdftotext -layout) e grava candidatos.
Uso: python scripts/ler_lista_ia.py <lista.txt>  -> dados/arquidiocese/lista_ia.json
Cada candidato: forania, paróquia (cabeçalho), nome, endereço, formato ('linha' = "Nome. Endereço"; 'cartao' = cartão do Google Maps)."""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TIPOS = r"(?:Igreja|Capela|Comunidade|Gruta|Santu[aá]rio|Par[oó]quia|Carmelo|Mosteiro|Orat[oó]rio|Catedral|Bas[ií]lica|Matriz|Cruzeiro|Ermida)"
linhas = Path(sys.argv[1]).read_text(encoding="utf-8").split("\n")
ini = next(i for i, l in enumerate(linhas) if "Vamos começar pela Forania" in l)
forania = paroquia = None
saida = []
i = ini
while i < len(linhas):
    l = linhas[i].rstrip()
    s = l.strip()
    mf = re.match(r"^Forania (?:de )?(.+?)(?: \(|$)", s)
    if mf and len(s) < 140:
        forania = mf.group(1).strip()
    mp = re.match(r"^\d+\.\s+(Par[oó]quia .+)$", s)
    if mp:
        paroquia = mp.group(1).strip(); i += 1; continue
    # cartão do Google Maps: nome, linha de nota "4.7 (284) · Igreja", linha "Cidade · km", botões, endereço
    if i + 1 < len(linhas) and re.match(r"^\s*\d[.,]\d\s+\(\S+\)\s+·", linhas[i + 1]) and s and not re.search(r"\bSC\b", s):
        nome, cat = s, linhas[i + 1].split("·", 1)[1].strip()
        end = None
        for j in range(i + 2, min(i + 7, len(linhas))):
            t = linhas[j].strip()
            if re.search(r"\bSC\b.*\d{5}-?\d{3}|\bSC\b\.?$", t) and "·" not in t:
                end = t.rstrip("."); break
        saida.append({"forania": forania, "paroquia": paroquia, "nome": nome, "endereco": end, "categoria": cat, "formato": "cartao"})
        i += 2; continue
    m = re.match(rf"^({TIPOS}[^\n]*?)\.\s+(.+)$", s)
    if m and not re.match(r"^Par[oó]quia .*\)$", s):
        nome, end = m.group(1), m.group(2)
        k = i + 1
        while not re.search(r"\d{5}-?\d{3}\.?\s*$|\bSC\.?\s*$", end) and k < len(linhas) and linhas[k].strip() and k - i < 3:
            t = linhas[k].strip()
            if re.match(rf"^{TIPOS}\b", t) or re.match(r"^\d+\.\s", t):
                break
            end += " " + t; k += 1
        end = re.sub(r"\s{2,}.*$", "", end).strip().rstrip(".")
        if re.search(r"\bSC\b", end):
            saida.append({"forania": forania, "paroquia": paroquia, "nome": nome.strip(), "endereco": end, "formato": "linha"})
        i = k; continue
    i += 1
(RAIZ / "dados" / "arquidiocese" / "lista_ia.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
from collections import Counter
print(len(saida), Counter(x["formato"] for x in saida), Counter(x["forania"] for x in saida))
