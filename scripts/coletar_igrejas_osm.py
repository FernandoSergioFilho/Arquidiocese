import json, time, urllib.request, urllib.parse, sys
import geopandas as gpd
from shapely.geometry import box
ilha = gpd.read_file(sys.argv[1]); ilha = ilha[ilha.REGIAO_FUNCIONAL!='Continente'].to_crs(4326).union_all()
UA = {"User-Agent": "mapa-paroquias-ilha/0.1 (uso pontual)"}
res = {}
def busca(x0,y0,x1,y1,prof=0):
    q = urllib.parse.urlencode({"amenity":"place_of_worship","viewbox":f"{x0},{y1},{x1},{y0}","bounded":1,"limit":50,"format":"jsonv2","extratags":1,"addressdetails":1})
    for t in range(3):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request("https://nominatim.openstreetmap.org/search?"+q, headers=UA), timeout=40)); break
        except Exception as e:
            print("erro", e, file=sys.stderr); time.sleep(5)
    else: return
    time.sleep(1.1)
    for x in d: res[x["osm_type"]+str(x["osm_id"])] = x
    if len(d) >= 50 and prof < 4:
        mx, my = (x0+x1)/2, (y0+y1)/2
        for a in [(x0,y0,mx,my),(mx,y0,x1,my),(x0,my,mx,y1),(mx,my,x1,y1)]: busca(*a, prof+1)
x0,y0,x1,y1 = ilha.bounds; passo=0.03
x=x0
while x < x1:
    y=y0
    while y < y1:
        if box(x,y,x+passo,y+passo).intersects(ilha): busca(x,y,x+passo,y+passo)
        y+=passo
    x+=passo
json.dump(list(res.values()), open(sys.argv[2],"w"), ensure_ascii=False)
print(len(res))
