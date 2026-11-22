"""Recorta um arquivo PMTiles v3 remoto (por pedidos HTTP Range) para uma caixa e zooms, gravando um PMTiles local.
Uso: python scripts/pmtiles_recorte.py <url> <saida.pmtiles> <oeste> <sul> <leste> <norte> <zmin> <zmax> [--so-medir]
Sem dependências além da biblioteca padrão. Formato: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md"""
import gzip
import io
import json
import math
import struct
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def ler(url, ini, n):
    req = urllib.request.Request(url, headers={"Range": f"bytes={ini}-{ini + n - 1}", "User-Agent": "mapa-paroquias/1.0"})
    for t in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:
            if t == 4:
                raise


def varint(b, i):
    v, s = 0, 0
    while True:
        x = b[i]; i += 1
        v |= (x & 0x7F) << s
        if not x & 0x80:
            return v, i
        s += 7


def le_dir(b):
    b = gzip.decompress(b)
    n, i = varint(b, 0)
    ids, runs, lens, offs = [], [], [], []
    last = 0
    for _ in range(n):
        d, i = varint(b, i); last += d; ids.append(last)
    for _ in range(n):
        x, i = varint(b, i); runs.append(x)
    for _ in range(n):
        x, i = varint(b, i); lens.append(x)
    for k in range(n):
        x, i = varint(b, i)
        offs.append(offs[k - 1] + lens[k - 1] if x == 0 and k > 0 else x - 1)
    return list(zip(ids, runs, offs, lens))


def wvarint(v):
    o = bytearray()
    while True:
        x = v & 0x7F; v >>= 7
        if v:
            o.append(x | 0x80)
        else:
            o.append(x); return bytes(o)


def escreve_dir(ents):
    o = bytearray(wvarint(len(ents)))
    last = 0
    for e in ents:
        o += wvarint(e[0] - last); last = e[0]
    for e in ents:
        o += wvarint(e[1])
    for e in ents:
        o += wvarint(e[3])
    for k, e in enumerate(ents):
        o += wvarint(0 if k > 0 and e[2] == ents[k - 1][2] + ents[k - 1][3] else e[2] + 1)
    return gzip.compress(bytes(o))


def zxy_id(z, x, y):  # curva de Hilbert, como no spec
    acc = sum(4 ** i for i in range(z))
    n = 2 ** z
    d, s = 0, n // 2
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s //= 2
    return acc + d


def tile_xy(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def main():
    url, saida = sys.argv[1], sys.argv[2]
    w, s, e, n = map(float, sys.argv[3:7]); zmin, zmax = int(sys.argv[7]), int(sys.argv[8])
    medir = "--so-medir" in sys.argv
    h = ler(url, 0, 16384)
    hd = struct.unpack("<7sB" + "Q" * 11 + "BBBBBB" + "iiii" + "Bii", h[:127])
    root_off, root_len, meta_off, meta_len, leaf_off, leaf_len, data_off = hd[2:9]
    ic, tc, tt = hd[14], hd[15], hd[16]
    meta = gzip.decompress(ler(url, meta_off, meta_len)) if meta_len else b"{}"
    raiz = le_dir(h[root_off:root_off + root_len] if root_off + root_len <= 16384 else ler(url, root_off, root_len))
    quer = {}
    for z in range(zmin, zmax + 1):
        x0, y0 = tile_xy(w, n, z); x1, y1 = tile_xy(e, s, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                quer[zxy_id(z, x, y)] = (z, x, y)
    alvo = sorted(quer)
    cache = {}

    def acha(tid):
        ents = raiz
        for _ in range(4):
            import bisect
            k = bisect.bisect_right([x[0] for x in ents], tid) - 1
            if k < 0:
                return None
            eid, run, off, ln = ents[k]
            if run == 0:  # diretório-folha
                key = (off, ln)
                if key not in cache:
                    cache[key] = le_dir(ler(url, leaf_off + off, ln))
                ents = cache[key]
                continue
            return (off, ln) if tid < eid + run else None
        return None

    with ThreadPoolExecutor(16) as ex:
        locs = list(ex.map(acha, alvo))
    por_z = {}
    total = 0
    for tid, loc in zip(alvo, locs):
        if loc:
            z = quer[tid][0]; por_z[z] = por_z.get(z, 0) + loc[1]; total += loc[1]
    print("tiles:", sum(1 for l in locs if l), "bytes por zoom:", {z: f"{v/1e6:.1f}MB" for z, v in sorted(por_z.items())}, f"total {total/1e6:.1f}MB")
    if medir:
        return
    pares = [(tid, loc) for tid, loc in zip(alvo, locs) if loc]
    with ThreadPoolExecutor(16) as ex:
        dados = list(ex.map(lambda p: ler(url, data_off + p[1][0], p[1][1]), pares))
    corpo, ents, visto = bytearray(), [], {}
    for (tid, _), d in zip(pares, dados):
        if d in visto:  # tiles iguais (mar) uma vez só
            off = visto[d]
        else:
            off = len(corpo); visto[d] = off; corpo += d
        if ents and ents[-1][2] == off and ents[-1][0] + ents[-1][1] == tid:
            ents[-1] = (ents[-1][0], ents[-1][1] + 1, off, len(d))
        else:
            ents.append((tid, 1, off, len(d)))
    # raiz + folhas (a raiz precisa caber nos primeiros 16 KB)
    folhas, raiz_n = bytearray(), []
    rd = escreve_dir(ents)
    if 127 + len(rd) <= 16384:
        folhas_b = b""
    else:
        tam = 4096
        for i in range(0, len(ents), tam):
            parte = ents[i:i + tam]; b = escreve_dir(parte)
            raiz_n.append((parte[0][0], 0, len(folhas), len(b))); folhas += b
        rd = escreve_dir(raiz_n); folhas_b = bytes(folhas)
    m = json.loads(meta); m["recorte"] = {"bbox": [w, s, e, n], "zooms": [zmin, zmax]}
    mb = gzip.compress(json.dumps(m).encode())
    o_root = 127; o_meta = o_root + len(rd); o_leaf = o_meta + len(mb); o_data = o_leaf + len(folhas_b)
    cab = struct.pack("<7sB" + "Q" * 11 + "BBBBBB" + "iiii" + "Bii", b"PMTiles", 3, o_root, len(rd), o_meta, len(mb), o_leaf, len(folhas_b),
                      o_data, len(corpo), len(pares), len(ents), len(visto), 1, ic, tc, tt, zmin, zmax,
                      int(w * 1e7), int(s * 1e7), int(e * 1e7), int(n * 1e7), zmin, int((w + e) / 2 * 1e7), int((s + n) / 2 * 1e7))
    with open(saida, "wb") as f:
        f.write(cab + rd + mb + folhas_b + bytes(corpo))
    print("gravado", saida, f"{(len(cab)+len(rd)+len(mb)+len(folhas_b)+len(corpo))/1e6:.1f}MB")


if __name__ == "__main__":
    main()
