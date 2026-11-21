"""Clientes exclusivamente de APIs documentadas. Sin scraping, sin API-Football.

Normaliza resultados de proveedores independientes al esquema usado por model.py.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'providers'

class ProviderError(RuntimeError):
    pass

class HttpClient:
    def __init__(self, timeout=24, cache_ttl=18000, opener=None):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.opener = opener or urlopen
        self.calls = 0
        self.stale_reads = 0

    def get(self, url, headers=None):
        # Cache path is based on sanitized URL only (never persists API keys).
        import hashlib
        path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if path.exists() and time.time() - path.stat().st_mtime < self.cache_ttl:
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        request = Request(url, headers={'User-Agent': os.getenv('RADAR_USER_AGENT', 'RadarLocalBatoPicks/2.1 (personal research)'), 'Accept':'application/json', **(headers or {})})
        try:
            self.calls += 1
            with self.opener(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as ex:
            # En una saturación temporal (429/5xx), continuar con caché marcada
            # como desactualizada. Un 401/403 no se disfraza de éxito.
            if ex.code in {429,500,502,503,504} and path.exists() and time.time()-path.stat().st_mtime < 36*3600:
                try:
                    self.stale_reads += 1
                    return json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    pass
            raise ProviderError(f'HTTP {ex.code} ({url.split("?")[0]})') from ex
        except (URLError, OSError, ValueError, TimeoutError) as ex:
            # Stale cached responses are preferable to provider outages, but flagged via age.
            if path.exists() and time.time() - path.stat().st_mtime < 36 * 3600:
                try:
                    self.stale_reads += 1
                    return json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    pass
            raise ProviderError(f'Conexión con proveedor fallida ({url.split("?")[0]}): {type(ex).__name__}') from ex
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return data


def normalize_match(mid, when, status, league, country, h_id, h_name, a_id, a_name, hg=None, ag=None, source='', source_url=''):
    if not when or not h_id or not a_id or not h_name or not a_name or h_id == a_id:
        return None
    try:
        parsed = datetime.fromisoformat(str(when).replace('Z', '+00:00'))
        if not parsed.tzinfo: parsed = parsed.replace(tzinfo=timezone.utc)
        when = parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None
    if status == 'FT' and (type(hg) is not int or type(ag) is not int or hg < 0 or ag < 0):
        return None # Jamás convertir un partido ya finalizado sin marcador en uno programado
    return {
        'fixture': {'id': str(mid), 'date': when, 'status': {'short': status}},
        'teams': {'home': {'id': str(h_id), 'name': str(h_name)}, 'away': {'id': str(a_id), 'name': str(a_name)}},
        'goals': {'home': hg if status == 'FT' else None, 'away': ag if status == 'FT' else None},
        'league': {'name': league, 'country': country},
        'source': source, 'source_url': source_url,
    }

FD_CODES = ['PL','PD','BL1','SA','FL1','DED','PPL','BSA','ELC']
FD_LABELS = {'PL':'Premier League','PD':'LaLiga','BL1':'Bundesliga','SA':'Serie A','FL1':'Ligue 1','DED':'Eredivisie','PPL':'Primeira Liga','BSA':'Brasileirão','ELC':'Championship'}


def football_data(client: HttpClient, token, codes=None):
    """Get all current-season matches once per league (free tier: 12 competitions)."""
    if not token: return {}, ['football-data.org: sin token; proveedor opcional']
    results, errors = {}, []
    codes = codes or FD_CODES
    for code in codes:
        if code not in FD_LABELS: continue
        url = f'https://api.football-data.org/v4/competitions/{code}/matches'
        try:
            payload = client.get(url, {'X-Auth-Token': token})
            rows = payload.get('matches')
            if not isinstance(rows, list): raise ProviderError('Falta matches[]')
            comp = payload.get('competition') or {}
            area = comp.get('area') or {}
            country = area.get('name') or ''
            matches = []
            for x in rows:
                h, a = x.get('homeTeam') or {}, x.get('awayTeam') or {}
                score = (x.get('score') or {}).get('fullTime') or {}
                status = 'FT' if x.get('status') == 'FINISHED' else 'NS' if x.get('status') in {'SCHEDULED','TIMED'} else 'OTHER'
                if status == 'OTHER': continue
                m = normalize_match('fd:'+str(x.get('id')), x.get('utcDate'), status,
                    comp.get('name') or FD_LABELS[code], country,
                    'fd:'+str(h.get('id')) if h.get('id') else '', h.get('name'),
                    'fd:'+str(a.get('id')) if a.get('id') else '', a.get('name'),
                    score.get('home'), score.get('away'), 'football-data.org', url)
                if m:
                    m['league']['logo'] = comp.get('emblem')
                    m['teams']['home']['logo'] = h.get('crest')
                    m['teams']['away']['logo'] = a.get('crest')
                    matches.append(m)
            if not matches: raise ProviderError('Sin encuentros utilizables')
            results['fd:'+code] = matches
        except (ProviderError, KeyError, TypeError) as ex:
            errors.append(f'football-data.org {code}: {ex}')
        # 10 req/min in free tier; sleep only if real network calls are made.
        if client.calls and client.calls % 8 == 0: time.sleep(5)
    return results, errors

OL_LEAGUES = {'bl1': ('Bundesliga', 'Alemania'), 'bl2': ('2. Bundesliga', 'Alemania')}

def openligadb(client: HttpClient, year, slugs=None):
    results, errors = {}, []
    for slug in (slugs or list(OL_LEAGUES)):
        if slug not in OL_LEAGUES: continue
        url = f'https://api.openligadb.de/getmatchdata/{slug}/{year}'
        try:
            rows = client.get(url)
            if not isinstance(rows, list): raise ProviderError('No llegó una lista')
            matches=[]
            for x in rows:
                home, away = x.get('team1') or {}, x.get('team2') or {}
                final = next((r for r in x.get('matchResults') or [] if r.get('resultTypeID', r.get('resultTypeId')) == 2 or r.get('resultName') == 'Endergebnis'), {})
                status = 'FT' if x.get('matchIsFinished') and final else 'NS' if not x.get('matchIsFinished') else 'OTHER'
                if status == 'OTHER': continue
                m = normalize_match('ol:'+str(x.get('matchID')), x.get('matchDateTimeUTC'), status,
                    *OL_LEAGUES[slug],
                    'ol:'+str(home.get('teamId')) if home.get('teamId') else '', home.get('teamName'),
                    'ol:'+str(away.get('teamId')) if away.get('teamId') else '', away.get('teamName'),
                    final.get('pointsTeam1'), final.get('pointsTeam2'), 'OpenLigaDB', url)
                if m: matches.append(m)
            if not matches: raise ProviderError('No hay partidos utilizables')
            results['ol:'+slug] = matches
        except (ProviderError, TypeError) as ex:
            errors.append(f'OpenLigaDB {slug}: {ex}')
    return results, errors


def sportsdb(client: HttpClient, year, key='', leagues=None):
    """Optional paid/production key. The shared free key 123 returns only 15 events/season,
    which is insufficient for a serious statistical prediction; never use it to model games.
    """
    if not key or key == '123':
        return {}, ['TheSportsDB: desactivado (la clave pública limita 15 partidos por temporada)']
    result, errors = {}, []
    leagues = leagues or [4328,4335]
    season = f'{year}-{year+1}'
    for league in leagues:
        url = f'https://www.thesportsdb.com/api/v1/json/{key}/eventsseason.php?' + urlencode({'id':league,'s':season})
        # Never cache a URL containing an API key, even via SHA; use separate keyless cache key?
        # This endpoint is opt-in. Query response is not written to a URL-bearing log.
        try:
            import urllib.request
            req = Request(url, headers={'User-Agent':'RadarLocalBatoPicks/2.1','Accept':'application/json'})
            with urlopen(req, timeout=25) as response: payload=json.load(response)
            rows = payload.get('events') or []
            if len(rows) < 40: raise ProviderError('Temporada incompleta (menos de 40 eventos)')
            games=[]
            for x in rows:
                h,a=x.get('idHomeTeam'),x.get('idAwayTeam')
                time_str = x.get('strTimestamp')
                status='FT' if x.get('intHomeScore') is not None and x.get('intAwayScore') is not None else 'NS'
                hg=int(x['intHomeScore']) if status=='FT' else None
                ag=int(x['intAwayScore']) if status=='FT' else None
                m=normalize_match('ts:'+str(x.get('idEvent')),time_str,status,x.get('strLeague') or 'Liga',x.get('strCountry') or '',
                    'ts:'+str(h) if h else '', x.get('strHomeTeam'), 'ts:'+str(a) if a else '',x.get('strAwayTeam'),hg,ag,
                    'TheSportsDB',f'https://www.thesportsdb.com/league/{league}')
                if m: games.append(m)
            if games:result['ts:'+str(league)] = games
        except (ValueError, TypeError, KeyError, ProviderError, HTTPError, URLError, TimeoutError) as ex:
            errors.append(f'TheSportsDB {league}: {type(ex).__name__} (sin URL ni token en registro)')
    return result, errors
