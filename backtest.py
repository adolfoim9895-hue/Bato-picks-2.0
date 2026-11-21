"""Validación retrospectiva temporal de las probabilidades locales.

La confianza ALTA es exclusivamente ESTADÍSTICA: no certifica alineaciones,
lesiones, rotaciones ni un riesgo bajo. OpenAI nunca es un prerrequisito.

La validación usa predicciones walk-forward calculadas con encuentros anteriores
al inicio de cada partido. Los umbrales son reglas explícitas de evaluación,
no porcentajes de 'confianza' ni garantías de éxito futuro.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from model import analyze_fixture, completed_before

# Requisitos publicados, modificables solo con evaluación posterior independiente.
MIN_FAVORITES = 25
FAVORITE_PROBABILITY = 0.75
MIN_OBSERVED_WINS = 0.70
MAX_CALIBRATION_GAP = 0.10


def wilson_interval(wins, count, z=1.96):
    """Intervalo Wilson al 95% para la frecuencia de victorias observada."""
    if not count:
        return None
    p = wins / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    margin = z * sqrt((p * (1-p) + z*z/(4*count))/count) / denominator
    return [round(max(0, center-margin), 4), round(min(1, center+margin), 4)]


def evaluate(history, max_games=260):
    """Evalúa partidos históricos, sin exponer resultados al calcular el pick."""
    completed = completed_before(history, datetime.max.replace(tzinfo=timezone.utc)) if history else []
    assessed = []
    for match in completed[-max_games:]:
        pred, _ = analyze_fixture(match, completed, min_home_probability=0.0)
        if not pred:
            continue
        home_goals, away_goals = match['goals']['home'], match['goals']['away']
        outcome = [int(home_goals>away_goals), int(home_goals==away_goals), int(home_goals<away_goals)]
        # Guardar probabilidades calculadas con precisión del modelo, no redondeos enteros de pantalla.
        probs = [pred['prob_modelo'], pred['probabilidades']['empate']/100, pred['probabilidades']['visita']/100]
        # Normalizar el redondeo para métrica multiclase (nunca para alterar las probabilidades publicadas).
        denominator = sum(probs)
        probs = [v/denominator for v in probs]
        assessed.append({'p':pred['prob_modelo'], 'actual':outcome[0],
                         'brier':sum((x-y)**2 for x,y in zip(probs, outcome))/3})

    favorites = [row for row in assessed if row['p'] >= FAVORITE_PROBABILITY]
    count = len(favorites)
    wins = sum(row['actual'] for row in favorites)
    observed = wins/count if count else None
    predicted = sum(row['p'] for row in favorites)/count if count else None
    gap = abs(observed-predicted) if count else None
    high_validated = bool(count>=MIN_FAVORITES and observed>=MIN_OBSERVED_WINS and gap<=MAX_CALIBRATION_GAP)
    return {
        'evaluados':len(assessed),
        'brier':round(sum(row['brier'] for row in assessed)/len(assessed),4) if assessed else None,
        'favoritos_75':count,
        'victorias_favoritos_75':wins,
        'acierto_favoritos_75':round(observed,4) if observed is not None else None,
        'prediccion_media_favoritos_75':round(predicted,4) if predicted is not None else None,
        'brecha_calibracion':round(gap,4) if gap is not None else None,
        'intervalo_wilson_95':wilson_interval(wins,count),
        'alta_validada':high_validated,
        'criterios_alta':{'min_favoritos_75':MIN_FAVORITES,
                         'acierto_minimo':MIN_OBSERVED_WINS,
                         'desviacion_maxima':MAX_CALIBRATION_GAP},
        'metodo':'Evaluación walk-forward: predicción realizada solo con encuentros previos; muestra de favoritos con P(local)>=75%. No garantiza calibración futura.',
    }


def label_prediction(pred, report, risks=None):
    """Confianza estadística separada del estado de verificación contextual."""
    risks = risks or []
    sample = pred['muestra']
    sufficient = (sample['liga'] >= 55 and
                  min(sample['local_casa'],sample['visita_fuera']) >= 5 and
                  min(sample['local_total'],sample['visita_total']) >= 8)
    eligible = pred['prob_modelo'] >= FAVORITE_PROBABILITY and sufficient and report['alta_validada']
    pred['confianza'] = 'alta' if eligible else 'media'
    pred['tipo_confianza'] = 'estadistica'
    pred['validacion'] = report
    pred['verificacion_contextual'] = 'riesgos_reportados' if risks else 'sin_verificar'
    if not eligible and pred['prob_modelo'] >= FAVORITE_PROBABILITY:
        pred['advertencias'].insert(0,'Confianza media estadística: la muestra o el historial walk-forward aún no acreditan la clasificación alta.')
    if risks:
        pred['advertencias'].extend(risks)
    return pred
