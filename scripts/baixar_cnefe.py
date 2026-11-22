"""Baixa o CNEFE 2022 (IBGE) de cada município da Arquidiocese e guarda só os estabelecimentos religiosos.
Uso: python scripts/baixar_cnefe.py  -> dados/arquidiocese/cnefe_religiosos.json"""
import csv, io, json, re, sys, unicodedata, urllib.parse, urllib.request, zipfile
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
from geocodificar_arquidiocese import MUNICIPIOS
BASE = "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/42_SC/"
def sem_acento(s): return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().upper().replace(" ", "_")
lista = urllib.request.urlopen(BASE, timeout=60).read().decode("utf-8", "replace")
arquivos = re.findall(r'href="(\d{7}_[^"]+\.zip)"', lista)
alvo = {sem_acento(m): m for m in MUNICIPIOS}
saida = []
for a in arquivos:
    nome = urllib.parse.unquote(a)[8:-4] if hasattr(urllib, "parse") else a[8:-4]
    chave = sem_acento(urllib.request.unquote(a)[8:-4])
    if chave not in alvo:
        continue
    mun = alvo[chave]
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(BASE + a, timeout=300).read()))
    n = 0
    for nomearq in z.namelist():
        with z.open(nomearq) as fh:
            for x in csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";"):
                est = (x.get("DSC_ESTABELECIMENTO") or "").strip()
                if x.get("COD_ESPECIE") == "8" or re.search(r"IGREJA|CAPELA|PAROQUIA|ORATORIO|SANTUARIO|GRUTA|MATRIZ|COMUNIDADE CATOLICA", est.upper()):
                    saida.append({"municipio": mun, "nome": est, "especie": x["COD_ESPECIE"], "localidade": x.get("DSC_LOCALIDADE", ""),
                                  "logradouro": " ".join(v for v in (x.get("NOM_TIPO_SEGLOGR"), x.get("NOM_TITULO_SEGLOGR"), x.get("NOM_SEGLOGR")) if v),
                                  "numero": x.get("NUM_ENDERECO"), "lat": float(x["LATITUDE"]), "lng": float(x["LONGITUDE"]), "nivel": x.get("NV_GEO_COORD")})
                    n += 1
    print(mun, n, flush=True)
(RAIZ / "dados" / "arquidiocese" / "cnefe_religiosos.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
print("fim", len(saida))
