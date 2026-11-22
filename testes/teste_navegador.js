const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const c=await b.newContext({viewport:{width:1300,height:820}});const p=await c.newPage();
 const errs=[];p.on('pageerror',e=>errs.push(e.message));
 await p.route('https://cdnjs.cloudflare.com/**',r=>r.fulfill({path:'/tmp/claude-0/-home-user-Arquidiocese/94036d4b-43e5-5447-8ee2-d906f6486752/scratchpad/dl/leaf/package/dist/leaflet.js',contentType:'application/javascript'}));
 await p.route('https://fonts.googleapis.com/**',r=>r.fulfill({body:'',contentType:'text/css'}));
 await p.goto('http://localhost:8766/_preview.html');await p.waitForTimeout(1000);
 const r=await p.evaluate(()=>{
  const T=window.__t, prob=[]; const km=(a,b)=>Math.hypot((a[0]-b[0])*111.2,(a[1]-b[1])*98.6);
  let n={par:0,igr:0,reg:0};
  // 1) cada paróquia
  for (const p of Object.values(T.paroquia)){
    n.par++;
    try{ T.selecionar({tipo:'paroquia',id:p.id},false); }catch(e){prob.push('erro paróquia '+p.id+': '+e.message);continue;}
    const h=document.querySelector('#conteudo h2')?.textContent;
    if (h!==p.nome) prob.push('painel errado em '+p.id+': '+h);
    const bb=T.boundsParoquia(p); const diag=km([bb.getSouth(),bb.getWest()],[bb.getNorth(),bb.getEast()]);
    const mz=p.comunidades.find(c=>c.matriz);
    if (!mz) prob.push('sem matriz: '+p.id);
    if (!mz?.pos) prob.push('matriz sem posição: '+p.id);
    if (diag>45) prob.push('paróquia espalhada demais ('+diag.toFixed(0)+' km): '+p.id);
    for (const c of p.comunidades){ if(!c.pos) prob.push('igreja sem posição: '+p.id+' / '+c.nome); else if (mz?.pos && km(c.pos,mz.pos)>30) prob.push('igreja a '+km(c.pos,mz.pos).toFixed(0)+' km da matriz: '+p.id+' / '+c.nome); }
    for (const f of p.regioes){ const rr=f.properties; if(!rr.paroquias.includes(p.id)) prob.push('região inconsistente '+rr.nome); 
      const cb=T.camadaDe[rr.id].getBounds().getCenter(); if (mz?.pos && km([cb.lat,cb.lng],mz.pos)>35) prob.push('área longe da matriz: '+p.id+' -> '+rr.nome); }
  }
  // 2) cada igreja
  for (const c of Object.values(T.igreja)){
    n.igr++;
    try{ T.selecionar({tipo:'igreja',id:c.id},false); }catch(e){prob.push('erro igreja '+c.id+': '+e.message);continue;}
    const h=document.querySelector('#conteudo h2')?.textContent;
    if (h!==c.nome) prob.push('painel errado na igreja '+c.id+': '+h);
    const btn=[...document.querySelectorAll('#conteudo [data-sel]')].find(e=>e.dataset.sel.includes('"paroquia"'));
    if (!btn || JSON.parse(btn.dataset.sel).id!==c.paroquia.id) prob.push('botão Ver paróquia errado na igreja '+c.id);
    try{ T.abrirJanelaIgreja(c); const js=document.querySelectorAll('.janela'), j=js[js.length-1]; if(!j||!j.innerText.includes(c.paroquia.nome)) prob.push('janela da igreja sem paróquia '+c.id); T.map.closePopup(); document.querySelectorAll('.janela').forEach(e=>e.remove()); }catch(e){prob.push('erro janela igreja '+c.id+': '+e.message);}
  }
  // 3) cada região
  for (const f of T.regioes){
    n.reg++; const rr=f.properties;
    try{ T.abrirJanelaRegiao(rr, T.camadaDe[rr.id].getBounds().getCenter()); }catch(e){prob.push('erro janela região '+rr.nome+': '+e.message);continue;}
    const jj=document.querySelectorAll('.janela'); const ids=[...jj[jj.length-1].querySelectorAll('[data-sel]')].map(e=>JSON.parse(e.dataset.sel)).filter(s=>s.tipo==='paroquia').map(s=>s.id);
    if (!ids.length || ids.some(id=>!rr.paroquias.includes(id))) prob.push('janela da região com paróquia errada: '+rr.nome);
    for (const id of ids){ const P=T.paroquia[id]; const mz=P.comunidades.find(c=>c.matriz); const cb=T.camadaDe[rr.id].getBounds().getCenter();
      if (mz?.pos && km([cb.lat,cb.lng],mz.pos)>35) prob.push('Ver paróquia da região '+rr.nome+' leva a '+P.nome+' ('+km([cb.lat,cb.lng],mz.pos).toFixed(0)+' km)'); }
    T.map.closePopup(); document.querySelectorAll('.janela').forEach(e=>e.remove());
    try{ T.selecionar({tipo:'regiao',id:rr.id},false); }catch(e){prob.push('erro região '+rr.nome+': '+e.message);}
  }
  // 4) foranias
  for (const f of Object.values(T.forania)){ try{T.selecionar({tipo:'forania',id:f.id},false);}catch(e){prob.push('erro forania '+f.id);} }
  T.selecionar(null,false);
  return {n,prob};
 });
 console.log(JSON.stringify(r.n)); console.log(r.prob.length+' problemas'); const cat={};r.prob.forEach(x=>{const k=x.split(':')[0].replace(/[0-9.]+ km/,'N km').replace(/ [a-z0-9-]+~[0-9]+$/,'');cat[k]=(cat[k]||0)+1;});console.log(cat);r.prob.filter(x=>!/janela da igreja sem|igreja sem posição|erro janela igreja/.test(x)).slice(0,40).forEach(x=>console.log(' -',x)); console.log('erros JS:',errs);
 await b.close();})();
