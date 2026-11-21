#!/usr/bin/env python3
"""Radar Local: 7 días, proveedores redundantes y OpenAI opcional.

Actualiza datos sin publicar secretos; ante caída de proveedor no fabrica partidos.
"""
from __future__ import annotations
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from model import analyze_fixture, date_of
from providers import HttpClient, football_data, openligadb, sportsdb, FD_CODES
from backtest import evaluate, label_prediction
from research import investigate

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'data'/'predictions.json'
STALE = ROOT/'.cache'/'last_good.json'


def update(now=None, client=None):
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(os.getenv('APP_TIMEZONE','America/Tijuana'))
    start = now.astimezone(tz).date()
    stop = start+timedelta(days=6)
    http = client or HttpClient()
    data = {'version':2,'estado':'sin_datos','actualizado':now.isoformat(),
            'zona_horaria':str(tz),'inicio':start.isoformat(),'fin':stop.isoformat(),
            'fuente':'football-data.org + OpenLigaDB (+ TheSportsDB opcional)',
            'nota':'Confianza estadística evaluada walk-forward, independiente de OpenAI; no implica bajas o alineaciones verificadas. Noticias no alteran porcentajes sin coeficientes validados.',
            'cobertura':{},'partidos':[], 'datos_insuficientes':[], 'errores_proveedores':[]}
    year=start.year if start.month>=7 else start.year-1
    codes = [x.strip() for x in os.getenv('FD_COMPETITIONS',','.join(FD_CODES)).split(',') if x.strip()]
    fd, errors = football_data(http, os.getenv('FOOTBALL_DATA_TOKEN','').strip(), codes)
    data['errores_proveedores'].extend(errors)
    ol, errors = openligadb(http, year, ['bl1','bl2'])
    data['errores_proveedores'].extend(errors)
    # Priorizar OpenLigaDB para Bundesliga si hay temporada completa: permite
    # comprobar temporadas anteriores; football-data.org queda como respaldo.
    if 'fd:BL1' in fd and len(ol.get('ol:bl1', [])) >= 50:
        fd.pop('fd:BL1', None)
    elif 'fd:BL1' in fd:
        ol.pop('ol:bl1', None)
    h2h_archive = {}
    if ol:
        for prior_year in (year-1, year-2):
            older, old_errors = openligadb(http, prior_year, [k.split(':')[1] for k in ol])
            # Los datos anteriores son exclusivamente para H2H, nunca para calibrar sin evaluación.
            for league_key, league_matches in older.items():
                h2h_archive.setdefault(league_key, []).extend(league_matches)
            data['errores_proveedores'].extend(old_errors)
    ts_key=os.getenv('THESPORTSDB_KEY','').strip()
    ts_leagues=[]
    for x in os.getenv('THESPORTSDB_LEAGUES','4328,4335').split(','):
        if x.strip().isdigit():ts_leagues.append(int(x.strip()))
    ts, errors = sportsdb(http, year, ts_key,ts_leagues)
    data['errores_proveedores'].extend(errors)
    # TheSportsDB is fallback; do not mix its team identifiers with other feeds.
    sources = {**fd, **ol}
    for sport_db_key, sport_db_matches in ts.items():
        known_equivalent = {'ts:4328':'fd:PL', 'ts:4335':'fd:PD', 'ts:4331':'fd:BL1'}
        if known_equivalent.get(sport_db_key) not in fd and not (sport_db_key=='ts:4331' and 'ol:bl1' in ol):
            sources[sport_db_key] = sport_db_matches
    groups_with_data=0
    all_scheduled=0
    candidates=[]
    reason_counts=Counter()
    for group, matches in sources.items():
        if len(matches)<20:
            data['errores_proveedores'].append(f'{group}: temporada demasiado corta para modelar')
            continue
        groups_with_data += 1
        # La muestra histórica externa, cuando existe, aumenta la potencia
        # del backtesting sin introducir resultados futuros en cada pronóstico.
        report=evaluate(h2h_archive.get(group, []) + matches)
        for fixture in matches:
            kickoff=date_of(fixture)
            if not kickoff or kickoff<now or kickoff.astimezone(tz).date()<start or kickoff.astimezone(tz).date()>stop:
                continue
            if fixture['fixture']['status']['short'] != 'NS':continue
            all_scheduled += 1
            pred, why=analyze_fixture(fixture,matches,h2h=matches+h2h_archive.get(group,[]))
            if pred:
                pred=label_prediction(pred, report)
                pred['investigacion']={'estado':'no_consultada','texto':'Sin investigación de noticias. No se presumen alineaciones ni bajas.', 'fuentes':[], 'riesgos':[]}
                candidates.append(pred)
            else:
                reason_counts[why]+=1
                data['datos_insuficientes'].append({'id':fixture['fixture']['id'],'fecha':fixture['fixture']['date'],
                    'liga':fixture['league']['name'],'local':fixture['teams']['home']['name'],
                    'visita':fixture['teams']['away']['name'],
                    'motivo':'DATOS INSUFICIENTES' if why != 'local_no_favorito_suficiente' else 'LOCAL NO FAVORITO',
                    'detalle':why})
    # 1 consulta web por candidato TOP como máximo, con presupuesto explícito.
    try: max_research=max(0,min(30,int(os.getenv('MAX_WEB_SEARCHES','0'))))
    except ValueError: max_research=0
    key=os.getenv('OPENAI_API_KEY','').strip()
    research_count=0
    for p in sorted(candidates, key=lambda x:x['prob_modelo'], reverse=True):
        if not key or research_count>=max_research:break
        research_count+=1
        news=investigate(p,key)
        p['investigacion']=news
        p['fuentes'].extend(news['fuentes'])
        if news['riesgos']:
            p['advertencias'].extend(f'Posible riesgo en noticia; verificar con la fuente antes del partido: {r}' for r in news['riesgos'])
            p['verificacion_contextual']='riesgos_reportados'
        else:
            # Una búsqueda sin alertas NO comprueba que no existan lesiones.
            p['verificacion_contextual']='sin_verificar'
    # La investigación web NO sube ni baja la confianza ESTADÍSTICA.
    # El estado de bajas y rotaciones se comunica por separado.
    candidates.sort(key=lambda x:(x['fecha'],-x['prob_modelo']))
    data['partidos']=candidates
    data['cobertura']={'ligas_con_datos':groups_with_data,'partidos_programados':all_scheduled,
                       'candidatos_locales':len(candidates),'consultas_http':http.calls,
                       'investigaciones_web':research_count if key else 0,
                       'respuestas_cache_antigua':getattr(http,'stale_reads',0),
                       'exclusiones':dict(reason_counts),
                       'nota':'La cobertura de proveedores gratuitos es parcial. Noticias, H2H antiguos y Transfermarkt pueden faltar.'}
    if getattr(http,'stale_reads',0):
        data['mensaje']='Algunos datos provienen de caché anterior por fallo de conexión; comprueba el calendario.'
        for p in candidates:
            p['advertencias'].append('Proveedor temporalmente inaccesible: parte de la información puede estar desactualizada.')
            p['verificacion_contextual']='datos_desactualizados'
    if sources:
        data['estado']='ok' if candidates else 'sin_candidatos'
        data.setdefault('mensaje','Calendario real procesado. Si no hay pronósticos, no se inventan.')
    else:
        data['estado']='sin_datos'
        data['mensaje']='No hay datos deportivos accesibles. Conecta football-data.org o comprueba OpenLigaDB.'
        # Cache of a last good publication can keep future fixtures visible for 36h, flagged.
        if STALE.exists():
            try:
                saved=json.loads(STALE.read_text(encoding='utf-8'))
                saved_at=datetime.fromisoformat(saved['actualizado'])
                if 0 <= (now-saved_at).total_seconds() < 36*3600:
                    retained=[p for p in saved.get('partidos',[]) if datetime.fromisoformat(p['fecha']) > now]
                    if retained:
                        data['partidos']=retained
                        data['estado']='degradado'
                        data['mensaje']='SIN DATOS NUEVOS: se muestra la última caché disponible; verifica horarios y noticias.'
            except (OSError,ValueError,TypeError,KeyError): pass
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if data['estado'] in {'ok','sin_candidatos'}:
        STALE.parent.mkdir(parents=True,exist_ok=True)
        STALE.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'estado':data['estado'],'ligas':groups_with_data,'partidos':len(candidates),
                      'partidos_sin_porcentaje':len(data['datos_insuficientes']),
                      'web':research_count,'errores':data['errores_proveedores']},ensure_ascii=False))
    return data

if __name__=='__main__': update()
