"""Búsqueda web opcional de OpenAI. Los datos estadísticos jamás vienen de la IA.

No usamos scraping: la herramienta web_search oficial devuelve citas de fuentes.
Si la salida no tiene citas de URL válidas, se descarta cualquier afirmación.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parents[1] / '.cache' / 'research'
URL_RE = re.compile(r'^https://[^\s]+$')


def source_list(data):
    """Extrae URLs de anotaciones url_citation reales de Responses API."""
    citations = []
    for item in data.get('output') or []:
        for piece in item.get('content') or []:
            for ann in piece.get('annotations') or []:
                if ann.get('type') != 'url_citation': continue
                url = ann.get('url', '')
                if URL_RE.match(url) and urlparse(url).hostname:
                    citations.append({'nombre':str(ann.get('title') or urlparse(url).hostname)[:110], 'url': url,
                                      'consulta':datetime.now(timezone.utc).date().isoformat(),'tipo_fecha':'consulta'})
    return list({i['url']: i for i in citations}.values())


def investigate(prediction, key, timeout=80):
    """Return verified citation URLs, not assumed injuries or numeric adjustments."""
    if not key:
        return {'estado':'sin_clave', 'texto':'Investigación web desactivada; bajas y alineaciones sin verificar.', 'fuentes':[], 'riesgos':[]}
    match_id = str(prediction['id'])
    name = hashlib.sha256((match_id + prediction['fecha']).encode()).hexdigest() + '.json'
    path = BASE / name
    if path.exists() and time.time() - path.stat().st_mtime < 10*3600:
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    date = prediction['fecha'][:10]
    request_body = {
        'model':os.getenv('OPENAI_MODEL', 'gpt-6.2-sol'),
        'tools':[{'type':'web_search','search_context_size':'low'}],
        'max_output_tokens':650,
        'input': (
            f'Investiga noticias PREPARTIDO del {date}: {prediction["local"]} vs {prediction["visita"]}, '
            f'competición {prediction["liga"]}. Busca lesiones, sanciones, descanso, rotaciones '
            'y alineaciones confirmadas SOLO si están documentadas. Evita resultados posteriores al inicio. '
            'Responde en ESPAÑOL, solo JSON con campos "resumen" (texto breve), "riesgos" (arreglo de textos breves). '
            'Si no se puede corroborar una ausencia no la menciones. No inventes datos ni porcentajes. '
            'Las cifras y fuentes las verificará la aplicación con las citas del resultado. '
            'No incluyas opiniones sobre apuestas.'
        ),
    }
    req=Request('https://api.openai.com/v1/responses', data=json.dumps(request_body).encode(),
                headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'}, method='POST')
    try:
        with urlopen(req, timeout=timeout) as r:
            response=json.load(r)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as ex:
        return {'estado':'error', 'texto':f'No se pudo consultar noticias: {type(ex).__name__}', 'fuentes':[], 'riesgos':[]}
    links = source_list(response)
    result = {'estado':'sin_fuentes','texto':'DATOS INSUFICIENTES: noticias sin citas verificables.', 'fuentes':links, 'riesgos':[]}
    raw = ''.join(piece.get('text', '') for item in response.get('output') or [] for piece in item.get('content') or [] if piece.get('type')=='output_text').strip()
    # No admitimos conclusiones sin fuentes citadas por la propia herramienta de búsqueda.
    if links and raw:
        try:
            stripped = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw).strip()
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict): raise ValueError('Objeto inválido')
            risks = [str(r)[:240] for r in parsed.get('riesgos',[]) if isinstance(r,str) and len(r.strip())>=12][:5] if isinstance(parsed.get('riesgos'),list) else []
            summary = str(parsed.get('resumen',''))[:360]
            result={'estado':'con_fuentes','texto':summary or 'Noticias consultadas con referencias.',
                    'fuentes':links[:8], 'riesgos':risks}
        except (TypeError,ValueError):
            # No publicar narración del modelo sin una estructura validable.
            result['texto']='Fuentes consultadas; la síntesis de IA no pasó las verificaciones.'
    BASE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf-8')
    return result
