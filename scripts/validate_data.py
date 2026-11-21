"""Comprobaciones de publicación: descarta JSON corruptos y porcentajes inventados."""
import json
import math
import sys
from datetime import datetime
from pathlib import Path


def verify(path):
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    assert payload.get('version') == 2, 'Versión de JSON incorrecta'
    assert payload.get('estado') in {'ok','sin_candidatos','sin_datos','degradado'}, 'Estado inválido'
    assert payload.get('inicio') and payload.get('fin')
    assert isinstance(payload.get('partidos'),list)
    assert isinstance(payload.get('datos_insuficientes'),list)
    for m in payload['partidos']:
        assert m.get('local') and m.get('visita') and m.get('fecha')
        assert datetime.fromisoformat(m['fecha'])
        assert m['confianza'] in {'media','alta'}
        vals=m['probabilidades']
        assert set(vals) == {'local','empate','visita'}
        assert all(isinstance(x,int) and 0<=x<=100 for x in vals.values())
        assert sum(vals.values())==100
        assert 0<=float(m['prob_modelo'])<=1
        assert 0.0 < m['goles_esperados']['local'] <= 4.3
        assert 0.0 < m['goles_esperados']['visita'] <= 3.5
        for v in m['goles_probabilidades'].values():
            assert math.isfinite(v) and 0 <= v <= 100
        for src in m.get('fuentes',[]):
            assert src['url'].startswith('https://') and src['consulta']
        assert 'APISPORTS' not in str(m), 'Prohibido incluir claves de proveedor viejo'
    print('JSON válido:',len(payload['partidos']),'pronósticos;',len(payload['datos_insuficientes']),'sin porcentaje')
    return True

if __name__=='__main__':
    verify(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'data'/'predictions.json')
