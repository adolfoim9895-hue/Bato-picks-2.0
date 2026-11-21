"""Motor estadístico de pronósticos, sin cuotas de apuestas ni IA generativa.

El modelo es una heurística Poisson con suavizado; NO es un modelo validado/calibrado.
Sólo usa información anterior al inicio de cada partido.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

FINISHED = {"FT"}


def safe_float(value, default=0.0):
    try:
        val = float(value)
        return val if math.isfinite(val) else default
    except (ValueError, TypeError):
        return default


def clamp(value, low, high):
    return min(high, max(low, value))


def date_of(match):
    value = (match.get("fixture") or {}).get("date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def completed_before(matches, before):
    selected = []
    for match in matches:
        date = date_of(match)
        status = (match.get("fixture") or {}).get("status") or {}
        teams = match.get("teams") or {}
        goals = match.get("goals") or {}
        if (date is not None and date < before and status.get("short") in FINISHED
            and teams.get("home", {}).get("id") and teams.get("away", {}).get("id")
            and isinstance(goals.get("home"), int) and isinstance(goals.get("away"), int)):
            selected.append(match)
    return sorted(selected, key=date_of)


def team_stats(matches):
    played = defaultdict(lambda: {"p": 0, "pts": 0, "gf": 0, "ga": 0})
    for m in matches:
        h = m["teams"]["home"]["id"]
        a = m["teams"]["away"]["id"]
        hg, ag = m["goals"]["home"], m["goals"]["away"]
        for key, gf, ga in ((h, hg, ag), (a, ag, hg)):
            played[key]["p"] += 1
            played[key]["gf"] += gf
            played[key]["ga"] += ga
            played[key]["pts"] += 3 if gf > ga else 1 if gf == ga else 0
    for row in played.values():
        row["ppg"] = row["pts"] / max(row["p"], 1)
    return played


def calculate_elo(matches):
    ratings = defaultdict(lambda: 1500.0)
    for m in matches:
        h, a = m["teams"]["home"]["id"], m["teams"]["away"]["id"]
        home_goals, away_goals = m["goals"]["home"], m["goals"]["away"]
        expected = 1.0 / (1.0 + 10 ** ((ratings[a] - ratings[h] - 65) / 400))
        actual = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        change = 24 * (actual - expected) * clamp(1 + abs(home_goals - away_goals) * 0.12, 1, 1.65)
        ratings[h] += change
        ratings[a] -= change
    return ratings


def team_matches(matches, tid, location=None):
    filtered = []
    for m in matches:
        h = m["teams"]["home"]["id"]
        a = m["teams"]["away"]["id"]
        if (location == "home" and h == tid) or (location == "away" and a == tid) or (location is None and (h == tid or a == tid)):
            filtered.append(m)
    return filtered


def goals_for_against(m, tid):
    ish = m["teams"]["home"]["id"] == tid
    gf = m["goals"]["home"] if ish else m["goals"]["away"]
    ga = m["goals"]["away"] if ish else m["goals"]["home"]
    return gf, ga


def recent_form(matches, tid, team_table):
    """Forma ponderada por calidad de rival mediante sus puntos por partido."""
    selected = team_matches(matches, tid)[-10:]
    if not selected:
        return 0.0, []
    edges, explain = [], []
    ranking = {t: i+1 for i, (t, _) in enumerate(sorted(team_table.items(), key=lambda row: (-row[1]["ppg"], -(row[1]["gf"]-row[1]["ga"]), -row[1]["gf"])))}
    for m in selected:
        h = m["teams"]["home"]["id"]
        a = m["teams"]["away"]["id"]
        opposing = a if h == tid else h
        opp_ppg = team_table.get(opposing, {}).get("ppg", 1.35)
        gf, ga = goals_for_against(m, tid)
        outcome = "G" if gf > ga else "E" if gf == ga else "P"
        points = 1 if gf > ga else 1/3 if gf == ga else 0
        expected = clamp(0.47 - 0.11 * (opp_ppg - 1.35) + (0.055 if h == tid else -0.055), 0.2, 0.7)
        edges.append(points - expected)
        explain.append({
            "rival": m["teams"]["away"]["name"] if h == tid else m["teams"]["home"]["name"],
            "rival_ppg": round(opp_ppg, 2),
            "rival_posicion": ranking.get(opposing),
            "lugar": "Local" if h == tid else "Visita",
            "resultado": outcome,
            "marcador": f"{gf}-{ga}"
        })
    return sum(edges) / len(edges), list(reversed(explain))


def smoothed_avg(values, baseline, prior=3):
    return (sum(values) + prior * baseline) / (len(values) + prior)


def poisson_probs(xg_home, xg_away, cap=12):
    def pois(k, rate):
        return math.exp(-rate) * (rate ** k) / math.factorial(k)
    hp = [pois(i, xg_home) for i in range(cap + 1)]
    ap = [pois(i, xg_away) for i in range(cap + 1)]
    win = draw = lose = total = 0.0
    score_prob = []
    for h in range(cap + 1):
        for a in range(cap + 1):
            p = hp[h] * ap[a]
            total += p
            if h > a:
                win += p
            elif h == a:
                draw += p
            else:
                lose += p
            score_prob.append((p, h, a))
    if total <= 0:
        return None
    score_prob.sort(reverse=True)
    return win / total, draw / total, lose / total, score_prob[:5]


def percentages(*probs):
    """Redondeo por restos mayores garantizando que sumen 100."""
    unrounded = [clamp(p * 100, 0, 100) for p in probs]
    floored = [int(math.floor(p)) for p in unrounded]
    residual = 100 - sum(floored)
    order = sorted(range(len(probs)), key=lambda i: unrounded[i] - floored[i], reverse=True)
    for i in order[:residual]:
        floored[i] += 1
    return floored


def analyze_fixture(fixture, season_history, h2h=None, min_home_probability=0.60):
    """Devuelve pronóstico o (None, motivo)."""
    before = date_of(fixture)
    if before is None:
        return None, "fecha_invalida"
    old = completed_before(season_history, before)
    if len(old) < 25:
        return None, "liga_sin_muestra"
    home_id = fixture["teams"]["home"]["id"]
    away_id = fixture["teams"]["away"]["id"]
    ht = team_matches(old, home_id)
    at = team_matches(old, away_id)
    hh = team_matches(old, home_id, "home")
    aa = team_matches(old, away_id, "away")
    if len(ht) < 5 or len(at) < 5 or len(hh) < 3 or len(aa) < 3:
        return None, "equipos_sin_muestra"

    avg_home = sum(m["goals"]["home"] for m in old) / len(old)
    avg_away = sum(m["goals"]["away"] for m in old) / len(old)
    avg_home = clamp(avg_home, 0.65, 2.4)
    avg_away = clamp(avg_away, 0.45, 1.95)

    hg_for = [m["goals"]["home"] for m in hh]
    hg_against = [m["goals"]["away"] for m in hh]
    aa_for = [m["goals"]["away"] for m in aa]
    aa_against = [m["goals"]["home"] for m in aa]

    home_atk = smoothed_avg(hg_for, avg_home) / avg_home
    away_def = smoothed_avg(aa_against, avg_home) / avg_home
    away_atk = smoothed_avg(aa_for, avg_away) / avg_away
    home_def = smoothed_avg(hg_against, avg_away) / avg_away
    table = team_stats(old)
    elos = calculate_elo(old)
    home_form, home_recent = recent_form(old, home_id, table)
    away_form, away_recent = recent_form(old, away_id, table)
    elo_factor = math.exp(clamp((elos[home_id] - elos[away_id]) / 850, -0.35, 0.35))
    form_factor = math.exp(clamp((home_form - away_form) * 0.29, -0.18, 0.18))

    lam_h = clamp(avg_home * home_atk * away_def * elo_factor * form_factor, 0.2, 4.3)
    lam_a = clamp(avg_away * away_atk * home_def / elo_factor / form_factor, 0.15, 3.5)

    meetings = completed_before(h2h or [], before)
    meeting_report = []
    h2h_results = []
    for m in meetings[-5:]:
        if {m["teams"]["home"]["id"], m["teams"]["away"]["id"]} != {home_id, away_id}:
            continue
        gf, ga = goals_for_against(m, home_id)
        h2h_results.append((1 if gf > ga else -1 if gf < ga else 0))
        meeting_report.append({
            "fecha": date_of(m).date().isoformat(),
            "local": m["teams"]["home"]["name"],
            "visita": m["teams"]["away"]["name"],
            "marcador": f"{m['goals']['home']}-{m['goals']['away']}"
        })
    # El H2H se muestra como contexto; no modifica lambdas sin validación histórica.

    probs = poisson_probs(lam_h, lam_a)
    if probs is None:
        return None, "calculo_invalido"
    w, d, l, top_scores = probs
    if w < min_home_probability or w <= l and min_home_probability > 0:
        return None, "local_no_favorito_suficiente"
    enough_high = len(hh) >= 5 and len(aa) >= 5 and len(old) >= 55 and len(ht) >= 8 and len(at) >= 8
    # No declarar "alta" antes de aplicar evaluación temporal fuera de muestra.
    confidence = "media"
    warnings = []
    if not enough_high:
        warnings.append("Muestra limitada: la confianza estadística es media aunque el porcentaje sea elevado.")
    if not h2h_results:
        warnings.append("No hay H2H verificable con los datos consultados.")
    warnings.append("Bajas, alineaciones y rotaciones NO VERIFICADAS. La confianza estadística no significa riesgo deportivo bajo; no se ajustan porcentajes sin datos validados.")

    # Las probabilidades de goles se deducen del MISMO modelo (Poisson independiente),
    # no de la IA ni de porcentajes inventados.
    total_lambda = lam_h + lam_a
    over05 = 1.0 - math.exp(-total_lambda)
    over15 = 1.0 - math.exp(-total_lambda) * (1.0 + total_lambda)
    over25 = 1.0 - math.exp(-total_lambda) * (1.0 + total_lambda + total_lambda**2 / 2)
    btts = (1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a))
    winning_pct, draw_pct, losing_pct = percentages(w, d, l)
    return {
        "id": fixture["fixture"]["id"],
        "fecha": fixture["fixture"]["date"],
        "liga": fixture["league"]["name"],
        "pais": fixture["league"].get("country", ""),
        "liga_logo": fixture["league"].get("logo"),
        "local": fixture["teams"]["home"]["name"],
        "visita": fixture["teams"]["away"]["name"],
        "local_logo": fixture["teams"]["home"].get("logo"),
        "visita_logo": fixture["teams"]["away"].get("logo"),
        "probabilidades": {"local": winning_pct, "empate": draw_pct, "visita": losing_pct},
        "prob_modelo": round(w, 4),
        "confianza": confidence,
        "goles_probabilidades": {"mas_05": round(over05*100, 1), "mas_15": round(over15*100, 1), "mas_25": round(over25*100, 1), "ambos": round(btts*100, 1)},
        "marcador": f"{top_scores[0][1]}-{top_scores[0][2]}",
        "marcadores": [{"marcador": f"{h}-{a}", "porcentaje": round(p * 100, 1)} for p, h, a in top_scores[:3]],
        "goles_esperados": {"local": round(lam_h, 2), "visita": round(lam_a, 2)},
        "promedios": {
            "local_general": {"favor": round(sum(goals_for_against(m,home_id)[0] for m in ht)/len(ht),2), "contra": round(sum(goals_for_against(m,home_id)[1] for m in ht)/len(ht),2)},
            "visita_general": {"favor": round(sum(goals_for_against(m,away_id)[0] for m in at)/len(at),2), "contra": round(sum(goals_for_against(m,away_id)[1] for m in at)/len(at),2)},
            "local_casa": {"favor": round(sum(hg_for)/len(hh),2), "contra": round(sum(hg_against)/len(hh),2)},
            "visita_fuera": {"favor": round(sum(aa_for)/len(aa),2), "contra": round(sum(aa_against)/len(aa),2)}
        },
        "rachas": {
            "local": {k:sum(r["resultado"]==k for r in home_recent[:5]) for k in ("G","E","P")},
            "visita": {k:sum(r["resultado"]==k for r in away_recent[:5]) for k in ("G","E","P")}
        },
        "muestra": {"liga": len(old), "local_casa": len(hh), "visita_fuera": len(aa), "local_total": len(ht), "visita_total": len(at)},
        "forma": {"local": home_recent, "visita": away_recent},
        "rivales": {"ppg_local": round(table[home_id]["ppg"], 2), "ppg_visita": round(table[away_id]["ppg"], 2),
                    "elo_local": round(elos[home_id]), "elo_visita": round(elos[away_id])},
        "h2h": list(reversed(meeting_report)),
        "fuentes": [{"nombre": fixture.get("source", "Estadísticas oficiales"), "url": fixture.get("source_url", ""), "consulta": datetime.now(timezone.utc).date().isoformat(), "tipo_fecha": "consulta"}],
        "advertencias": warnings,
        "metodo": "Poisson independiente + casa/fuera + forma + Elo. H2H descriptivo; sin cuotas; parámetros aún sujetos a validación retrospectiva."
    }, None
