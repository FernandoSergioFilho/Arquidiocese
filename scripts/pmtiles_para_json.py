"""Converte um PMTiles local em pacotes JSON (o host do mapa só serve tipos web comuns).
Uso: python scripts/pmtiles_para_json.py <entrada.pmtiles> <pasta_saida> [z_pacote=11]
Saída: base_0.json (zooms < 9), base9_<x>_<y>.json (zooms 9 até z_pacote-1, por tile do zoom 9) e base_<x>_<y>.json (cada tile z_pacote com seus filhos), {"z/x/y": base64 do tile gzip}."""
import base64
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from pmtiles_recorte import le_dir  # noqa: E402


def id_para_zxy(tid):
    z, acc = 0, 0
    while acc + 4 ** z <= tid:
        acc += 4 ** z; z += 1
    d, n = tid - acc, 2 ** z
    x = y = 0
    s, t = 1, d
    while s < n:
        rx = 1 & (t // 2); ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        x += s * rx; y += s * ry; t //= 4; s *= 2
    return z, x, y


def main(ent, pasta, zp=11):
    b = Path(ent).read_bytes()
    hd = struct.unpack("<7sB" + "Q" * 11 + "BBBBBB" + "iiii" + "Bii", b[:127])
    ro, rl, _, _, lo, ll, do = hd[2:9]
    ents = []
    for tid, run, off, ln in le_dir(b[ro:ro + rl]):
        if run == 0:
            ents += le_dir(b[lo + off:lo + off + ln])
        else:
            ents.append((tid, run, off, ln))
    pacotes = {}
    for tid, run, off, ln in ents:
        dado = base64.b64encode(b[do + off:do + off + ln]).decode()
        for k in range(run):
            z, x, y = id_para_zxy(tid + k)
            if z < 8:  # o mapa não se afasta além do zoom 8
                continue
            if z < 9:
                nome = "base_0"
            elif z < zp:  # zooms intermediários: por tile do zoom 9
                nome = f"base9_{x >> (z - 9)}_{y >> (z - 9)}"
            else:
                nome = f"base_{x >> (z - zp)}_{y >> (z - zp)}"
            pacotes.setdefault(nome, {})[f"{z}/{x}/{y}"] = dado
    Path(pasta).mkdir(parents=True, exist_ok=True)
    for f in Path(pasta).glob("base*.json"):
        f.unlink()
    for nome, t in pacotes.items():
        (Path(pasta) / f"{nome}.json").write_text(json.dumps(t, separators=(",", ":")))
    tams = sorted(os.path.getsize(Path(pasta) / f"{n}.json") for n in pacotes)
    print(len(pacotes), "pacotes; maior", f"{tams[-1]/1e6:.2f}MB; total {sum(tams)/1e6:.1f}MB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(x) for x in sys.argv[3:4]))
