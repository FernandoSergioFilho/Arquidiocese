import json, re, unicodedata, sys, math
from difflib import SequenceMatcher
import geopandas as gpd
from shapely.geometry import Point
H = json.load(open(sys.argv[1])); osm = json.load(open(sys.argv[2])); geo = json.load(open(sys.argv[3]))
ilha = gpd.read_file(sys.argv[4]); ilha = ilha[ilha.REGIAO_FUNCIONAL!='Continente'].to_crs(4326).union_all().buffer(0.003)
ponto = {f['properties']['bairro']: f['properties']['ponto'] for f in geo['features']}
def norm(s):
    s = unicodedata.normalize('NFD', s or '').encode('ascii','ignore').decode().lower()
    s = re.sub(r'\b(igreja|capela|paroquia|santuario|matriz|gruta|de|da|do|dos|das|e|arquidiocese|n\.?|sra\.?|senhora|nossa|nossas|s\.)\b',' ', s)
    return re.sub(r'[^a-z ]',' ', s).split()
cands = []
for x in osm:
    t = x.get('extratags') or {}
    if t.get('denomination') not in ('roman_catholic','catholic') and not (t.get('denomination') is None and re.search(r'capela|par[oó]quia|santu|nossa senhora|s[aã]o |santa |santo ', (x.get('name') or '').lower())): continue
    la, lo = float(x['lat']), float(x['lon'])
    if not ilha.contains(Point(lo, la)): continue
    cands.append({'nome': x.get('name') or '', 'lat': la, 'lng': lo, 'osm': x['osm_type'][0]+str(x['osm_id']), 'tok': set(norm(x.get('name')))})
def dist(a,b): return math.hypot((a[0]-b[0])*111, (a[1]-b[1])*111*0.885)
out = []
for f in H['foranias']:
    for p in f['paroquias']:
        for c in p['comunidades']:
            alvo = c['nome'] if not c['matriz'] else c['nome']
            tk = set(norm(alvo)); best = []
            for o in cands:
                inter = len(tk & o['tok']); 
                if not inter: continue
                sc = inter / max(len(tk), 1)
                d = dist(ponto[c['bairro']], (o['lat'], o['lng'])) if c['bairro'] else None
                best.append((sc, -(d if d is not None else 9), o, d))
            best.sort(key=lambda t:(t[0], t[1]), reverse=True)
            out.append((p['id'], c['nome'], c['local'], c['bairro'], [(round(s,2), round(d,1) if d is not None else None, o['nome'], o['osm']) for s,_,o,d in best[:3]]))
for r in out: print(r[0][:10].ljust(10), '|', r[1][:38].ljust(38), '|', (r[2] or '')[:22].ljust(22), '|', r[4])
