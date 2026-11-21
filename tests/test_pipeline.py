"""Tests aislados (sin conexión): schemas, errores, integridad y datos insuficientes.

Los equipos simulados existen solamente dentro de tests; no se publican como picks.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from providers import football_data, openligadb, ProviderError
from research import source_list, investigate
from backtest import evaluate
from validate_data import verify
import update

class FakeClient:
    def __init__(self, data=None, error=False):
        self.data=data or {}
        self.calls=0
        self.error=error
    def get(self, url, headers=None):
        self.calls += 1
        if self.error: raise ProviderError('No hay conexión')
        return self.data.get(url, [])

class ProvidersTests(unittest.TestCase):
    def test_football_data_normalizes_real_api_shape(self):
        url='https://api.football-data.org/v4/competitions/PL/matches'
        payload={'competition':{'name':'Premier League','area':{'name':'England'}},'matches':[
            {'id':100,'utcDate':'2026-11-20T12:00:00Z','status':'FINISHED','homeTeam':{'id':1,'name':'Arsenal'},'awayTeam':{'id':2,'name':'Chelsea'},'score':{'fullTime':{'home':2,'away':1}}},
            {'id':101,'utcDate':'2026-11-22T12:00:00Z','status':'TIMED','homeTeam':{'id':3,'name':'Liverpool'},'awayTeam':{'id':4,'name':'Everton'},'score':{'fullTime':{'home':None,'away':None}}},
        ]}
        items,errors=football_data(FakeClient({url:payload}),'test-token',['PL'])
        self.assertFalse(errors)
        self.assertEqual(len(items['fd:PL']),2)
        self.assertEqual(items['fd:PL'][0]['goals']['home'],2)
        self.assertEqual(items['fd:PL'][1]['fixture']['status']['short'],'NS')
        self.assertEqual(items['fd:PL'][1]['goals']['home'],None)

    def test_openligadb_uses_fulltime_not_halftime(self):
        url='https://api.openligadb.de/getmatchdata/bl1/2026'
        rows=[{'matchID':100,'matchDateTimeUTC':'2026-10-20T12:00:00Z','matchIsFinished':True,
            'team1':{'teamId':1,'teamName':'Bayern'},'team2':{'teamId':2,'teamName':'Dortmund'},
            'matchResults':[{'resultTypeID':1,'pointsTeam1':1,'pointsTeam2':0},{'resultTypeID':2,'pointsTeam1':3,'pointsTeam2':1}]}]
        items,errors=openligadb(FakeClient({url:rows}),2026,['bl1'])
        self.assertFalse(errors)
        self.assertEqual(items['ol:bl1'][0]['goals'],{'home':3,'away':1})

    def test_errors_do_not_fabricate_results(self):
        items,errors=openligadb(FakeClient(error=True),2026,['bl1'])
        self.assertFalse(items)
        self.assertTrue(errors)

    def test_news_requires_actual_citations(self):
        bad={'output':[{'content':[{'type':'output_text','text':'{"riesgos":["Faltan cinco titulares"]}'}]}]}
        self.assertEqual(source_list(bad),[])
        self.assertEqual(investigate({'id':'1','fecha':'2026-11-21'},''),
            {'estado':'sin_clave','texto':'Investigación web desactivada; bajas y alineaciones sin verificar.','fuentes':[], 'riesgos':[]})
        cited={'output':[{'content':[{'type':'output_text','text':'...','annotations':[{'type':'url_citation','url':'https://example.org/match','title':'Fuente'}]}]}]}
        self.assertEqual(source_list(cited)[0]['nombre'],'Fuente')

    def test_json_validator_rejects_invented_percentages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.json'
            data={'version':2,'estado':'ok','inicio':'2026-11-21','fin':'2026-11-27','partidos':[], 'datos_insuficientes':[]}
            path.write_text(json.dumps(data),encoding='utf8')
            self.assertTrue(verify(path))
            data['partidos'].append({'local':'A','visita':'B','fecha':'2026-11-22T14:00:00+00:00',
                'confianza':'alta','probabilidades':{'local':80,'empate':20,'visita':20}, 'prob_modelo':0.8,
                'goles_esperados':{'local':2,'visita':0.5},'goles_probabilidades':{'mas_05':90},'fuentes':[]})
            path.write_text(json.dumps(data),encoding='utf8')
            with self.assertRaises(AssertionError):verify(path)

    def test_pipeline_publishes_zero_predictions_on_all_provider_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'OUTPUT',Path(tmp)/'publish.json'), patch.object(update,'STALE',Path(tmp)/'cache.json'):
            with patch.dict(os.environ,{'FOOTBALL_DATA_TOKEN':'','THESPORTSDB_KEY':'','OPENAI_API_KEY':''}):
                result=update.update(datetime(2026,11,21,19,0,tzinfo=timezone.utc),FakeClient(error=True))
            self.assertEqual(result['estado'],'sin_datos')
            self.assertEqual(result['partidos'],[])
            self.assertGreaterEqual(len(result['errores_proveedores']),1)

    def test_pipeline_calculates_only_from_past_results(self):
        base=datetime(2026,9,1,tzinfo=timezone.utc)
        rows=[]
        for i in range(150):
            home=i%8+1
            away=(i*3+3)%8+1
            if home==away:away=(away%8)+1
            hg,ag=(4,0) if home==1 else (0,3) if away==1 else ((i%3)+1,i%2)
            rows.append({'matchID':i,'matchDateTimeUTC':(base+timedelta(hours=i*6)).isoformat(),
                         'matchIsFinished':True,'team1':{'teamId':home,'teamName':f'Equipo {home}'},
                         'team2':{'teamId':away,'teamName':f'Equipo {away}'},
                         'matchResults':[{'resultTypeID':2,'pointsTeam1':hg,'pointsTeam2':ag}]})
        rows.append({'matchID':999,'matchDateTimeUTC':'2026-11-22T20:00:00+00:00',
                     'matchIsFinished':False,'team1':{'teamId':1,'teamName':'Equipo 1'},
                     'team2':{'teamId':8,'teamName':'Equipo 8'},'matchResults':[]})
        url='https://api.openligadb.de/getmatchdata/bl1/2026'
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'OUTPUT',Path(tmp)/'publish.json'), patch.object(update,'STALE',Path(tmp)/'cache.json'):
            with patch.dict(os.environ,{'FOOTBALL_DATA_TOKEN':'','THESPORTSDB_KEY':'','OPENAI_API_KEY':''}):
                result=update.update(datetime(2026,11,21,19,0,tzinfo=timezone.utc),FakeClient({url:rows}))
            self.assertIn(result['estado'],['ok','sin_candidatos'])
            self.assertEqual(result['cobertura']['partidos_programados'],1)
            self.assertEqual(result['cobertura']['investigaciones_web'],0)
            self.assertEqual(len(result['partidos'])+len(result['datos_insuficientes']),1)
            self.assertTrue(verify(Path(tmp)/'publish.json'))
            if result['partidos']:
                p=result['partidos'][0]
                self.assertGreaterEqual(p['probabilidades']['local'],60)
                self.assertIn('mas_25',p['goles_probabilidades'])
                self.assertTrue(p['fuentes'][0]['url'].startswith('https://api.openligadb.de/'))

if __name__=='__main__': unittest.main()

class InstallationReadinessTests(unittest.TestCase):
    def test_no_legacy_api_dependency_in_executable_files(self):
        for name in ('app.js','sw.js','scripts/providers.py','scripts/update.py','scripts/research.py'):
            contents=(ROOT/name).read_text(encoding='utf8').lower()
            for old in ('api-football.com','api-sports.io','apisports_key','api_football_key'):
                self.assertNotIn(old,contents,name)

    def test_workflow_contains_pages_and_tests(self):
        workflow=(ROOT/'.github/workflows/publicar.yml').read_text(encoding='utf8')
        self.assertIn('actions/upload-pages-artifact@v4',workflow)
        self.assertIn('actions/deploy-pages@v4',workflow)
        self.assertIn('python -m unittest discover -s tests -v',workflow)
        self.assertIn("vars.MAX_WEB_SEARCHES || '0'",workflow)
        self.assertIn('secrets.FOOTBALL_DATA_TOKEN',workflow)
        self.assertNotIn('secrets.APISPORTS_KEY',workflow)

    def test_backtest_needs_25_retro_favorites(self):
        from backtest import evaluate
        self.assertFalse(evaluate([])['alta_validada'])
        self.assertEqual(evaluate([])['favoritos_75'],0)

    def test_full_pipeline_preserves_high_without_openai(self):
        from backtest import label_prediction
        base=datetime(2026,9,1,tzinfo=timezone.utc)
        rows=[]
        for i in range(160):
            home=i%8+1;away=((i*3+3)%8)+1
            if home==away:away=away%8+1
            hg,ag=(4,0) if home==1 else (0,3) if away==1 else ((i%3)+1,i%2)
            rows.append({'matchID':i,'matchDateTimeUTC':(base+timedelta(hours=i*6)).isoformat(),
                         'matchIsFinished':True,'team1':{'teamId':home,'teamName':f'Equipo {home}'},
                         'team2':{'teamId':away,'teamName':f'Equipo {away}'},
                         'matchResults':[{'resultTypeID':2,'pointsTeam1':hg,'pointsTeam2':ag}]})
        rows.append({'matchID':999,'matchDateTimeUTC':'2026-11-22T20:00:00+00:00',
                     'matchIsFinished':False,'team1':{'teamId':1,'teamName':'Equipo 1'},
                     'team2':{'teamId':8,'teamName':'Equipo 8'},'matchResults':[]})
        url='https://api.openligadb.de/getmatchdata/bl1/2026'
        validated={'alta_validada':True,'favoritos_75':35,'acierto_favoritos_75':.80,'evaluados':100}
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'OUTPUT',Path(tmp)/'publish.json'),patch.object(update,'STALE',Path(tmp)/'cache.json'),patch.object(update,'evaluate',return_value=validated):
            with patch.dict(os.environ,{'FOOTBALL_DATA_TOKEN':'','THESPORTSDB_KEY':'','OPENAI_API_KEY':'','MAX_WEB_SEARCHES':'0'}):
                result=update.update(datetime(2026,11,21,19,0,tzinfo=timezone.utc),FakeClient({url:rows}))
            self.assertTrue(result['partidos'])
            self.assertEqual(result['partidos'][0]['confianza'],'alta')
            self.assertEqual(result['partidos'][0]['verificacion_contextual'],'sin_verificar')
            self.assertEqual(result['cobertura']['investigaciones_web'],0)
            self.assertTrue(verify(Path(tmp)/'publish.json'))

class DataIntegrityTests(unittest.TestCase):
    def test_completed_without_score_is_not_resurrected_as_future(self):
        from providers import normalize_match
        m=normalize_match('test', '2026-11-20T10:00:00Z','FT','Liga','Pais',
                          'team1','Equipo 1','team2','Equipo 2',None,0)
        self.assertIsNone(m)

    def test_http_503_can_use_recent_cache_and_flags_stale(self):
        from providers import HttpClient
        import providers
        from urllib.error import HTTPError
        from hashlib import sha256
        url='https://example.org/matches'
        with tempfile.TemporaryDirectory() as tmp, patch.object(providers,'CACHE',Path(tmp)):
            path=Path(tmp)/(sha256(url.encode()).hexdigest()+'.json')
            path.write_text('{"matches":[]}',encoding='utf8')
            def fail(request, timeout):
                raise HTTPError(request.full_url,503,'unavailable',{},None)
            client=HttpClient(cache_ttl=0,opener=fail)
            self.assertEqual(client.get(url),{'matches':[]})
            self.assertEqual(client.stale_reads,1)
