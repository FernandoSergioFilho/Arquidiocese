"""Confere a lista do modo IA do Google (dados/arquidiocese/lista_ia.json) contra os dados oficiais e fontes abertas.
Uso: python scripts/casar_lista_ia.py
Saída: dados/arquidiocese/posicoes_lista_ia.json (posições aceitas) e dados/arquidiocese/relatorio_lista_ia.txt

A lista da IA pode inventar endereços. Uma posição só é aceita quando:
  1. a entrada casa com UMA comunidade da mesma paróquia no site da Arquidiocese (nome; localidade desempata);
  2. a comunidade ainda não tem posição exata (só 'localidade', 'aprox' ou 'bairro');
  3. a rua informada existe de verdade no município, confirmada por
       a) um estabelecimento religioso do Censo 2022 (CNEFE) na mesma rua -> usa o ponto do Censo, ou
       b) a rua no OpenStreetMap, curta (até 1,2 km) -> usa o meio da rua;
  4. o ponto fica perto da matriz (8 km nas cidades grandes, 15 km nas demais) e, se a localidade já era conhecida, a até 3 km dela."""
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
from geocodificar_arquidiocese import MUNICIPIOS, cache, municipio_de, nominatim, CACHE  # noqa: E402
from montar_arquidiocese import contido, km, norm_seq  # noqa: E402

D = RAIZ / "dados" / "arquidiocese"
NAO_CATOLICA = re.compile(r"evang|assembl|batista|adventista|universal|quadrangular|presbiter|luteran|esp[ií]rit|testemunh|"
                          r"[uú]ltimos dias|congrega[cç][aã]o crist|maranata|deus [eé] amor|mundial|renascer|metodista|umbanda|"
                          r"candombl|templo|minist[eé]rio|igreja de cristo|igreja crist[aã]|pentecost|sara nossa|bola de neve|"
                          r"videira|internacional da gra[cç]a|nazareno|anglican|ortodox|kardec|budis|mesquita|sinagoga|"
                          r"wesley|cristo vive|vida nova|lagoinha|tabern[aá]culo|reino de deus|avivamento|jeov|ieclb|betel|sinodal|maranata|getsemani|sal[aã]o (de )?festas", re.I)
CIDADE_GRANDE = {"Florianópolis", "São José", "Palhoça", "Biguaçu", "Itajaí", "Balneário Camboriú", "Brusque", "Itapema", "Camboriú"}
ABREV = {"r": "rua", "av": "avenida", "rod": "rodovia", "estr": "estrada", "est": "estrada", "serv": "servidao", "tv": "travessa",
         "trav": "travessa", "al": "alameda", "pca": "praca", "ver": "vereador", "cap": "capitao", "dr": "doutor", "pe": "padre",
         "sen": "senador", "gov": "governador", "mal": "marechal", "prof": "professor", "dep": "deputado", "cel": "coronel",
         "pres": "presidente", "des": "desembargador", "eng": "engenheiro", "gen": "general", "sto": "santo", "sta": "santa",
         "intend": "intendente", "alm": "almirante", "ten": "tenente", "maj": "major", "con": "conego", "irma": "irma",
         "profa": "professora", "dna": "dona", "d": "dom", "sr": "senhor", "sra": "senhora", "nsa": "nossa", "n": "nossa", "s": "sao"}
TIPO_RUA = {"rua", "avenida", "rodovia", "estrada", "servidao", "travessa", "alameda", "praca", "largo", "caminho", "geral", "beco", "acesso"}
LIGA = {"de", "da", "do", "dos", "das", "e"}


def sem_acento(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def toks_rua(s):
    ws = [ABREV.get(w, w) for w in re.sub(r"[^a-z0-9 ]", " ", sem_acento(s)).split()]
    return [w for w in ws if w not in LIGA and w not in TIPO_RUA]


def mesma_rua(a, b):
    ta, tb = toks_rua(a), toks_rua(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    curto, longo = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(curto) >= 2 and contido(curto, longo) and len(curto) / len(longo) >= 0.6


GENERICO_CNEFE = {"igreja", "catolica", "comunidade", "capela", "paroquia", "centro", "social", "pavilhao", "casa", "paroquial", "salao",
                  "templo", "matriz", "anexo", "sede", "mr", "unidos", "em", "na", "no", "a", "o"}


def santo_confere(nome_cnefe, nome_com, outros):
    """Se o registro do Censo cita um santo/devoção, ele precisa ser o da comunidade (tolerando erros de digitação)."""
    from difflib import SequenceMatcher
    if not re.search(r"(?i)\b(s[aã]o|santa|santo|nossa|n\.? ?s|senhor|sagrad|divino|cristo|imaculada|bom jesus)\b", nome_cnefe):
        return True
    ws = [w for w in norm_seq(nome_cnefe) if w not in GENERICO_CNEFE and w not in outros and w not in {"sao", "santa", "santo", "senhor"}]
    if not ws:
        return True
    alvo = [w for w in norm_seq(nome_com) if w not in {"sao", "santa", "santo", "senhor"}]
    return all(any(SequenceMatcher(None, w, a).ratio() >= 0.8 for a in alvo) for w in ws)


def elegivel(c):
    """Sem posição exata própria (as que vieram desta mesma lista numa rodada anterior também contam)."""
    return c.get("posicao") in ("localidade", "aprox", "bairro") or bool(c.get("endereco_google"))


def parse_endereco(end):
    partes = [p.strip() for p in re.split(r"\s+[-–]\s+", end)]
    rua = num = bairro = None
    if partes and re.match(r"(?i)^(r\.|rua|av\.?|avenida|rod\.?|rodovia|estr\.?|estrada|serv\.?|servid[aã]o|tv\.?|travessa|al\.|alameda|pra[cç]a|p[cç]a\.?|largo|caminho)(?=[\s.]|$)", partes[0]):
        m = re.match(r"^(.*?)(?:,\s*(\d+[\w-]*|s/n))?$", partes[0])
        rua, num = m.group(1).strip(), (m.group(2) if m.group(2) and m.group(2) != "s/n" else None)
        if len(partes) > 1:
            bairro = partes[1].split(",")[0].strip()
    elif partes:
        bairro = partes[0].split(",")[0].strip()
    return rua, num, bairro, municipio_de(end)


def main():
    lista = json.loads((D / "lista_ia.json").read_text(encoding="utf-8"))
    H = json.loads((RAIZ / "mapa" / "dados.json").read_text(encoding="utf-8"))["hierarquia"]
    cnefe = json.loads((D / "cnefe_religiosos.json").read_text(encoding="utf-8"))
    pars = [p for f in H["foranias"] for p in f["paroquias"]]
    rel, aceitas, conflitos = [], {}, []

    def paroquia_de(cab, ents):
        if not cab:
            return None
        nome = re.sub(r"\s*\(.*$", "", cab)
        mun = municipio_de(cab) or next((municipio_de(e["endereco"] or "") for e in ents if e["endereco"] and municipio_de(e["endereco"])), None)
        sq = norm_seq(nome)
        def mun_ok(p):  # o cabeçalho pode citar vários municípios ("Municípios: Santo Amaro da Imperatriz e Águas Mornas")
            return not mun or p["municipio"] == mun or p["municipio"].lower() in cab.lower()
        cands = [p for p in pars if norm_seq(p["nome"]) == sq and mun_ok(p)]
        if len(cands) != 1:
            cands = [p for p in pars if (contido(sq, norm_seq(p["nome"])) or contido(norm_seq(p["nome"]), sq)) and mun_ok(p)]
        return cands[0] if len(cands) == 1 else None

    grupos = {}
    for e in lista:
        grupos.setdefault((e["forania"], e["paroquia"]), []).append(e)
    stats = {"entradas": len(lista), "sem_paroquia": 0, "sem_comunidade": 0, "ambigua": 0, "ja_exata": 0, "sem_rua": 0,
             "rua_nao_confirmada": 0, "longe": 0, "aceita_cnefe": 0, "aceita_rua": 0}
    for (fo, cab), ents in grupos.items():
        p = paroquia_de(cab, ents)
        if not p:
            stats["sem_paroquia"] += len(ents); rel.append(f"PARÓQUIA NÃO IDENTIFICADA: {cab} ({len(ents)} entradas)"); continue
        mz = next((c for c in p["comunidades"] if c["matriz"]), None)
        for e in ents:
            nome_l = re.sub(r"^(Igreja Matriz|Matriz|Igreja|Capela|Comunidade Cat[oó]lica|Comunidade|Gruta|Santu[aá]rio|Par[oó]quia)\s+", "", e["nome"])
            dentro = " ".join(re.findall(r"\(([^)]*)\)", nome_l))
            nome_l = re.sub(r"\s*\(.*?\)", "", nome_l).split(" – ")[0].split(" - ")[0]
            sq = norm_seq(nome_l)
            texto_loc = norm_seq(dentro + " " + (e["endereco"] or ""))
            cands = [c for c in p["comunidades"] if sq and (norm_seq(c["nome"]) == sq or
                     (contido(norm_seq(c["nome"]), sq) or contido(sq, norm_seq(c["nome"]))) and min(len(sq), len(norm_seq(c["nome"]))) / max(len(sq), len(norm_seq(c["nome"]))) >= 0.6)]
            if re.match(r"(?i)^igreja matriz|^matriz", e["nome"]):
                cands = [c for c in p["comunidades"] if c["matriz"]] or cands
            if len(cands) > 1:
                pelo_local = [c for c in cands if norm_seq(c["local"]) and contido(norm_seq(c["local"]), texto_loc)]
                cands = pelo_local
            if not cands:
                stats["sem_comunidade"] += 1; rel.append(f"  sem comunidade: {p['id']} | {e['nome']} | {e['endereco']}"); continue
            if len(cands) > 1:
                stats["ambigua"] += 1; rel.append(f"  ambígua: {p['id']} | {e['nome']} -> {[c['local'] for c in cands]}"); continue
            c = cands[0]
            chave = f"{p['id']}|{c['nome']}|{c['local']}"
            if not e["endereco"]:
                stats["sem_rua"] += 1; continue
            rua, num, bairro, mun = parse_endereco(e["endereco"])
            mun = mun or p["municipio"]
            if not rua:
                stats["sem_rua"] += 1; continue
            # confirmação a) Censo 2022 na mesma rua
            ponto, fonte, como = None, None, None
            outros = set(norm_seq(rua)) | set(norm_seq(c["local"])) | set(norm_seq(bairro or ""))
            regs = [r for r in cnefe if r["municipio"] == mun and mesma_rua(rua, r["logradouro"]) and not NAO_CATOLICA.search(r["nome"])
                    and santo_confere(r["nome"], c["nome"], outros)]
            if regs:
                cat = [r for r in regs if re.search(r"(?i)cat[oó]lic|capela|par[oó]quia|comunidade|n\.? ?s\b|nossa|s[aã]o |santa |santo |gruta", r["nome"])]
                melhor = cat if len(cat) == 1 else (regs if len(regs) == 1 else [])
                if not melhor and num and num.isdigit():  # pelo número da casa, quando o Censo traz número
                    com_num = sorted((r for r in (cat or regs) if str(r["numero"]).isdigit() and int(r["numero"]) > 0), key=lambda r: abs(int(r["numero"]) - int(num)))
                    if com_num and abs(int(com_num[0]["numero"]) - int(num)) <= 60:
                        melhor = [com_num[0]]
                if len(melhor) == 1:
                    r0 = melhor[0]
                    ponto, como = (r0["lat"], r0["lng"]), "cnefe"
                    fonte = f"Lista do Google (modo IA): {e['endereco']} · confirmada no Censo 2022: {r0['nome']}, {r0['logradouro']} {r0['numero']}"
            # confirmação b) rua no OpenStreetMap
            if not ponto:
                rua_q = " ".join(ABREV.get(w.lower().rstrip("."), w) if w.endswith(".") else w for w in rua.split())
                res = nominatim({"street": rua_q, "city": mun, "state": "Santa Catarina", "country": "Brasil", "limit": 5, "addressdetails": 1}) or []
                ok = []
                for x in res:
                    a = x.get("address", {})
                    cidade = a.get("city") or a.get("town") or a.get("municipality") or a.get("village") or ""
                    if x.get("category") != "highway" or sem_acento(cidade) != sem_acento(mun) or not mesma_rua(rua, x.get("name") or ""):
                        continue
                    bb = [float(v) for v in x["boundingbox"]]
                    if km((bb[0], bb[2]), (bb[1], bb[3])) > 1.2:
                        continue
                    ok.append(x)
                if len(ok) >= 1 and all(km((float(o["lat"]), float(o["lon"])), (float(ok[0]["lat"]), float(ok[0]["lon"]))) < 0.8 for o in ok):
                    ponto, como = (round(float(ok[0]["lat"]), 6), round(float(ok[0]["lon"]), 6)), "rua"
                    fonte = f"Lista do Google (modo IA): {e['endereco']} · rua confirmada no OpenStreetMap: {ok[0].get('name')}"
            if not ponto:
                stats["rua_nao_confirmada"] += 1
                if elegivel(c):
                    rel.append(f"  rua não confirmada: {chave} | {e['endereco']}")
                continue
            if not elegivel(c):
                stats["ja_exata"] += 1
                d = km(ponto, (c["lat"], c["lng"])) if "lat" in c else 0
                if d > 1.5:
                    conflitos.append(f"  {chave} | mapa ({c.get('posicao')}) x lista: {d:.1f} km | {e['endereco']}")
                continue
            lim = 8 if p["municipio"] in CIDADE_GRANDE else 15
            if mz and mz.get("posicao") not in ("aprox", None) and "lat" in mz and km(ponto, (mz["lat"], mz["lng"])) > lim:
                stats["longe"] += 1; rel.append(f"  longe da matriz ({km(ponto, (mz['lat'], mz['lng'])):.1f} km): {chave} | {e['endereco']}"); continue
            if c.get("posicao") == "localidade" and "lat" in c and km(ponto, (c["lat"], c["lng"])) > 3:
                stats["longe"] += 1; rel.append(f"  longe da localidade ({km(ponto, (c['lat'], c['lng'])):.1f} km): {chave} | {e['endereco']}"); continue
            stats["aceita_" + ("cnefe" if como == "cnefe" else "rua")] += 1
            aceitas[chave] = {"lat": ponto[0], "lng": ponto[1], "posicao": "cnefe" if como == "cnefe" else "rua_google", "fonte": fonte, "endereco": e["endereco"]}
            if como == "cnefe":
                aceitas[chave]["cnefe"] = f"{r0['nome'].title()}, {r0['logradouro'].title()}{', ' + str(r0['numero']) if str(r0['numero']) not in ('0', '') else ''}"
            rel.append(f"  ACEITA ({como}): {chave} <- {e['endereco']}")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    (D / "posicoes_lista_ia.json").write_text(json.dumps({"_sobre": __doc__.split("\n\n")[1], "posicoes": aceitas}, ensure_ascii=False, indent=1), encoding="utf-8")
    txt = "\n".join([json.dumps(stats, ensure_ascii=False), "", "== Divergências com posições já exatas (só para conferir; nada mudou):"] + conflitos + ["", "== Detalhe:"] + rel)
    (D / "relatorio_lista_ia.txt").write_text(txt, encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False)); print(len(conflitos), "divergências com posições exatas")


if __name__ == "__main__":
    main()
