/* Radar Local · interfaz estática para GitHub Pages. Sin secretos ni llamadas privadas. */
(() => {
'use strict';
const $ = (sel) => document.querySelector(sel);
const TZ = 'America/Tijuana';
const state = {data:null, date:null, filter:'todos', query:'', favorites:new Set()};
try { state.favorites = new Set(JSON.parse(localStorage.getItem('radar_local_favoritos') || '[]')); } catch {}

const fmt = new Intl.DateTimeFormat('es-MX', {timeZone:TZ, weekday:'short', day:'numeric', month:'short'});
const clockFmt = new Intl.DateTimeFormat('es-MX',{timeZone:TZ,hour:'2-digit',minute:'2-digit',hour12:false});
const esc = (v) => String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const dateKey = (value) => {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);
  const o = Object.fromEntries(parts.filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
  return `${o.year}-${o.month}-${o.day}`;
};
const addDays = (date, delta) => {
  const dt = new Date(`${date}T12:00:00Z`); dt.setUTCDate(dt.getUTCDate()+delta); return dt.toISOString().slice(0,10);
};
const dateView = (d) => fmt.format(new Date(`${d}T18:00:00Z`));
const dates = () => state.data ? Array.from({length:7},(_,i)=>addDays(state.data.inicio,i)) : [];
const imageSrc = (raw) => {try { const u=new URL(raw);return u.protocol==='https:'?u.href:''; } catch { return ''; }};
const safeUrl = (raw) => {try {const u = new URL(raw);return u.protocol==='https:'?u.href:'';}catch{return '';}};
const teamLogo = (name,src) => imageSrc(src) ? `<img class="team-logo" src="${esc(src)}" loading="lazy" alt="">` : `<div class="team-logo-fallback" aria-hidden="true">${esc((name||'?')[0].toUpperCase())}</div>`;
const fixtureCount = (d) => state.data.partidos.filter(m=>dateKey(m.fecha)===d).length;
function setData(data) {
 state.data=data;
 const today=dateKey(new Date());
 state.date=dates().includes(today)?today:dates()[0];
 render();
}
function render() {
 if(!state.data)return;
 const matches=state.data.partidos;
 $('#totalCount').textContent=matches.length;
 $('#highCount').textContent=matches.filter(m=>m.confianza==='alta').length;
 $('#mediumCount').textContent=matches.filter(m=>m.confianza==='media').length;
 const updated = new Date(state.data.actualizado);
 $('#updatedShort').textContent=Number.isFinite(updated.getTime())?`Actualizado ${clockFmt.format(updated)}`:'Sin actualizar';
 const datesList=dates();
 $('#weekRange').textContent=`${dateView(datesList[0])} — ${dateView(datesList[6])}`;
 const today=dateKey(new Date());
 $('#days').innerHTML=datesList.map(d=>{
  const n=Number(d.slice(8,10)); const w=dateView(d).split(' ')[0].replace('.','');
  const label=d===today?'Hoy':d===addDays(today,1)?'Mañana':w;
  return `<button class="day ${d===state.date?'active':''}" type="button" data-date="${d}" aria-pressed="${d===state.date}"><span class="name">${esc(label)}</span><span class="number">${n}</span><span class="count">${fixtureCount(d)} picks</span></button>`;
 }).join('');
 const at=datesList.indexOf(state.date);
 $('#dayPrev').disabled=at<=0; $('#dayNext').disabled=at>=6;
 document.querySelectorAll('[data-filter]').forEach(b=>{b.classList.toggle('active',b.dataset.filter===state.filter);b.setAttribute('aria-pressed',String(b.dataset.filter===state.filter));});
 const query=state.query.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase();
 const selected=matches.filter(m=>dateKey(m.fecha)===state.date)
  .filter(m=>state.filter==='todos'||(state.filter==='favoritos'?state.favorites.has(String(m.id)):state.filter===m.confianza))
  .filter(m=>[m.local,m.visita,m.liga,m.pais].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(query))
  .sort((a,b)=>b.probabilidades.local-a.probabilidades.local);
 $('#dayCount').textContent=`${selected.length} partidos`;
 const cover=state.data.cobertura || {};
 const note=$('#sourceNote'); note.classList.remove('warning');
 const compromised=['sin_datos','degradado','error'].includes(state.data.estado);
 note.textContent=`${compromised?'⚠ ':''}${state.data.mensaje||'Resultados reales'} · ${cover.ligas_con_datos??0} ligas con historial · ${cover.partidos_programados??0} juegos programados · ${cover.investigaciones_web??0} investigaciones web · ${state.data.datos_insuficientes?.length??0} sin pronóstico. ${state.data.estado==='degradado'?'CACHÉ ANTIGUA: verificar horarios.':''}`;
 if(compromised || (state.data.errores_proveedores||[]).length)note.classList.add('warning');
 $('#fixtures').innerHTML=selected.map(matchMarkup).join('');
 $('#empty').classList.toggle('hidden',selected.length>0);
 $('#emptyText').textContent=state.data.estado==='sin_datos'?'No hay un proveedor de resultados conectado. OpenLigaDB es gratuito; configura football-data.org para ampliar ligas.':'No hay locales que superen el criterio estadístico para este día. Puedes consultar los juegos sin pronóstico en la sección inferior.';
 const insufficient=(state.data.datos_insuficientes||[]).filter(m=>dateKey(m.fecha)===state.date)
  .filter(m=>[m.local,m.visita,m.liga].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(query));
 $('#unratedCount').textContent=`${insufficient.length} encuentros`;
 $('#unratedItems').innerHTML=insufficient.slice(0,80).map(x=>`<div class="unrated-item"><b>${esc(x.local)} — ${esc(x.visita)}</b><small>${esc(x.liga)} · ${esc(x.motivo)} (${esc(x.detalle)})</small></div>`).join('')||'<p>No hay encuentros sin pronóstico registrados para este día.</p>';
 // Los botones de favoritos deben sobrevivir al rerender.

 document.querySelectorAll('.star').forEach(btn=>btn.addEventListener('click',()=>{
   const id=String(btn.dataset.id); if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);
   try{localStorage.setItem('radar_local_favoritos',JSON.stringify([...state.favorites]));}catch{}
   render();
 }));
}
function matchMarkup(m) {
 const ps=m.probabilidades||{local:0,empate:0,visita:0};
 const high=m.confianza==='alta';
 const isFav=state.favorites.has(String(m.id));
 const lg=imageSrc(m.liga_logo)?`<img class="league-logo" src="${esc(m.liga_logo)}" alt="">`:'';
 const hrec=(m.form?.local||[]).slice(0,5);
 const arec=(m.form?.visita||[]).slice(0,5);
 const recent=(records)=>records.length?`<div class="form-row">${records.map(r=>`<span class="form-tag ${String(r.resultado||'').toLowerCase()}" title="${esc((r.lugar||'')+' contra '+(r.rival||''))}">${esc(r.resultado)} ${esc(r.marcador)} · ${esc(r.rival)} (posición ${esc(r.rival_posicion??'—')}, PPG ${esc(r.rival_ppg??'—')})</span>`).join('')}</div>`:'<p>Sin historial suficiente.</p>';
 const warnings=(m.advertencias||[]).map(w=>`<p class="warningline">⚠ ADVERTENCIA: ${esc(w)}</p>`).join('');
 const h2h=(m.h2h||[]).length?`<p>${m.h2h.slice(0,5).map(x=>`${esc(x.fecha)}: ${esc(x.local)} ${esc(x.marcador)} ${esc(x.visita)}`).join('<br>')}</p>`:'<p>Sin H2H confirmado: no se inventan enfrentamientos anteriores.</p>';
 const news=m.investigacion||{};
 const goal=m.goles_probabilidades||{};
 const goalsHtml=`<div class="details-grid">${[['Más de 0.5',goal.mas_05],['Más de 1.5',goal.mas_15],['Más de 2.5',goal.mas_25],['Ambos anotan',goal.ambos]].map(([key,n])=>`<div class="item"><span>${esc(key)}</span><strong>${Number.isFinite(Number(n))?esc(n)+'%':'DATOS INSUFICIENTES'}</strong></div>`).join('')}</div>`;
 const backtest=m.validacion||{};
 const validationHtml=`<p>Evaluaciones retrospectivas: ${esc(backtest.evaluados??0)} · Brier: ${esc(backtest.brier??'sin datos')} · Favoritos de ≥75% estudiados: ${esc(backtest.favoritos_75??0)} · Frecuencia observada: ${backtest.acierto_favoritos_75!==null&&backtest.acierto_favoritos_75!==undefined?Math.round(backtest.acierto_favoritos_75*100)+'%':'DATOS INSUFICIENTES'} · Brecha entre predicción y frecuencia: ${backtest.brecha_calibracion!==undefined&&backtest.brecha_calibracion!==null?Math.round(backtest.brecha_calibracion*100)+' puntos':'DATOS INSUFICIENTES'}. Intervalo Wilson 95%: ${backtest.intervalo_wilson_95?backtest.intervalo_wilson_95.map(x=>Math.round(x*100)+'%').join('–'):'DATOS INSUFICIENTES'}.</p>`;
 const sources=[...(m.fuentes||[])];
 const sourceHtml=sources.length?sources.map(x=>{const url=safeUrl(x.url);return url?`<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(x.nombre)}</a> · Consultado: ${esc(x.consulta||'fecha desconocida')}</li>`:'';}).join(''):'<li>Sin fuentes con URL disponible.</li>';
 const newsHtml=`<p>${esc(news.texto||'DATOS INSUFICIENTES: sin investigación de noticias.')}</p>${(news.riesgos||[]).map(r=>`<p class="warningline">🔴 ADVERTENCIA: Información reportada, comprobar la fuente: ${esc(r)}</p>`).join('')}`;
 const scoreOptions=(m.marcadores||[]).length ? `<div class="mini-score">${m.marcadores.map(x=>`<span>${esc(x.marcador)} · ${Number(x.porcentaje).toFixed(1)}%</span>`).join('')}</div>` : '';
 return `<article class="fixture">
  <div class="fixture-top"><div class="league">${lg}<div><span>${esc(m.liga)}</span> <div class="country">${esc(m.pais)}</div></div></div><div class="top-actions"><span class="game-time">${esc(clockFmt.format(new Date(m.fecha)))} h</span><button class="star ${isFav?'active':''}" data-id="${esc(m.id)}" aria-label="${isFav?'Quitar favorito':'Guardar favorito'}" aria-pressed="${isFav}">${isFav?'★':'☆'}</button></div></div>
  <div class="teams"><div class="team-info">${teamLogo(m.local,m.local_logo)}<div><div class="team-role">Local</div><div class="team-name">${esc(m.local)}</div></div></div><div class="teams-vs">VS</div><div class="team-info team-away"><div><div class="team-role">Visita</div><div class="team-name">${esc(m.visita)}</div></div>${teamLogo(m.visita,m.visita_logo)}</div></div>
  <div class="prob-bars" role="img" aria-label="Local ${ps.local}%, empate ${ps.empate}%, visita ${ps.visita}%"><div class="prob-bar-home" style="width:${Number(ps.local)}%"></div><div class="prob-bar-draw" style="width:${Number(ps.empate)}%"></div><div class="prob-bar-away" style="width:${Number(ps.visita)}%"></div></div>
  <div class="probs"><span>Local ${ps.local}%</span><span>Empate ${ps.empate}%</span><span>Visita ${ps.visita}%</span></div>
  <div class="game-bottom"><div><div class="pickline">Gana ${esc(m.local)} · <strong>${ps.local}%</strong></div><div class="score">Marcador más probable: <b>${esc(m.marcador)}</b> · Goles estimados: ${esc(m.goles_esperados?.local??'?')}–${esc(m.goles_esperados?.visita??'?')}</div></div><div class="confidence ${high?'alta':'media'}">${high?'✦ ESTADÍSTICA ALTA':'◈ ESTADÍSTICA MEDIA'}</div></div>
  <p class="context-notice">🔴 ADVERTENCIA · Bajas, alineaciones y rotaciones ${esc(m.verificacion_contextual === 'datos_desactualizados' ? 'con datos posiblemente desactualizados' : m.verificacion_contextual === 'riesgos_reportados' ? 'con posibles riesgos reportados' : 'no verificadas')}. La etiqueta indica solo confianza estadística.</p>
  <details class="details"><summary>Ver análisis · Forma, rivales, H2H y advertencias</summary><div class="details-body">
  <div class="details-grid"><div class="item"><span>Historial del local en casa</span><strong>${Number(m.muestra?.local_casa||0)} partidos</strong></div><div class="item"><span>Historial del visitante fuera</span><strong>${Number(m.muestra?.visita_fuera||0)} partidos</strong></div><div class="item"><span>Puntos/partido del local</span><strong>${esc(m.rivales?.ppg_local??'—')}</strong></div><div class="item"><span>Puntos/partido visitante</span><strong>${esc(m.rivales?.ppg_visita??'—')}</strong></div></div>
  <h3>Promedios reales de gol (partidos anteriores)</h3>
  <div class="details-grid"><div class="item"><span>Local en casa: favor / contra</span><strong>${esc(m.promedios?.local_casa?.favor??'—')} / ${esc(m.promedios?.local_casa?.contra??'—')}</strong></div><div class="item"><span>Visitante fuera: favor / contra</span><strong>${esc(m.promedios?.visita_fuera?.favor??'—')} / ${esc(m.promedios?.visita_fuera?.contra??'—')}</strong></div></div>
  <h3>Rachas de últimos cinco: G / E / P</h3>
  <p>Local: ${esc(m.rachas?.local?.G??'—')} / ${esc(m.rachas?.local?.E??'—')} / ${esc(m.rachas?.local?.P??'—')} · Visita: ${esc(m.rachas?.visita?.G??'—')} / ${esc(m.rachas?.visita?.E??'—')} / ${esc(m.rachas?.visita?.P??'—')}</p>
  <h3>Últimos partidos del local, con identificación del rival</h3>${recent(hrec)}
  <h3>Últimos partidos del visitante</h3>${recent(arec)}
  <h3>Enfrentamientos directos (H2H)</h3>${h2h}
  <h3>Marcadores exactos estimados</h3>${scoreOptions}
  <h3>Mercados de goles (Poisson)</h3>${goalsHtml}
  <h3>Evaluación histórica del modelo</h3>${validationHtml}
  <h3>Noticias, bajas, sanciones y rotaciones</h3><p class="warningline">🔴 ADVERTENCIA: Verificación contextual ${esc(m.verificacion_contextual||'sin_verificar')}. Una confianza estadística alta NO significa que las bajas o alineaciones estén verificadas.</p>${newsHtml}
  <p>Valor de plantilla según Transfermarkt: <b>NO VERIFICADO</b> (no se extrae información sin licencia o datos fiables).</p>
  <h3>🔴 ADVERTENCIA · Riesgos y limitaciones</h3>${warnings}
  <h3>Fuentes de datos y fecha de consulta</h3><ul class="source-list">${sourceHtml}</ul>
  <p style="font-size:10px;color:#6f849a;margin-top:11px">Modelo estadístico sin cuotas. Las etiquetas no garantizan resultados; comprueba alineaciones, bajas y noticias actuales.</p>
  </div></details>
 </article>`;
}

$('#days').addEventListener('click',(ev)=>{const btn=ev.target.closest('[data-date]');if(!btn)return;state.date=btn.dataset.date;render();});
$('#dayPrev').addEventListener('click',()=>{const i=dates().indexOf(state.date);if(i>0){state.date=dates()[i-1];render();}});
$('#dayNext').addEventListener('click',()=>{const i=dates().indexOf(state.date);if(i>=0&&i<6){state.date=dates()[i+1];render();}});
$('#filterPills').addEventListener('click',(ev)=>{const btn=ev.target.closest('[data-filter]');if(!btn)return;state.filter=btn.dataset.filter;render();});
$('#search').addEventListener('input',(ev)=>{state.query=ev.target.value;render();});
$('#aboutBtn').addEventListener('click',()=>$('#aboutDialog').showModal());
$('#closeDialog').addEventListener('click',()=>$('#aboutDialog').close());
$('#aboutDialog').addEventListener('click',(ev)=>{if(ev.target.id==='aboutDialog')ev.target.close();});

async function init() {
 try {
  const response=await fetch('./data/predictions.json?t='+Date.now(), {cache:'no-store'});
  if(!response.ok)throw new Error('Datos no publicados');
  const data=await response.json();
  if(!data || !Array.isArray(data.partidos)|| !/^\d{4}-\d{2}-\d{2}$/.test(data.inicio||'')) throw new Error('JSON inválido');
  setData(data);
 }catch(ex){setData({estado:'error',mensaje:'Sin conexión a datos. Publica esta carpeta en GitHub Pages o ejecuta un servidor local.',inicio:dateKey(new Date()),actualizado:new Date().toISOString(),cobertura:{},partidos:[],datos_insuficientes:[],errores_proveedores:[]});}
 if('serviceWorker' in navigator&&location.protocol==='https:')navigator.serviceWorker.register('./sw.js').catch(()=>{});
}
init();
})();
