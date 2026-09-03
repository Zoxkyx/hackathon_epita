import html
import os

# Séries de données du graphique de rétention. Steps validés contre la surface
# du panneau (#0f1614) : lightness band, chroma, séparation CVD, contraste.
# Le corail et la menthe en sont absents : ils sont réservés aux deux canaux de signal.
CATEGORICAL = ["#3987e5", "#c98500", "#9085e9", "#d55181", "#008300"]

RULE_LABELS = (
    ("jamais enseigné", "R1 — maîtrise d'un concept non enseigné"),
    ("n'était pas acquis", "R2 — oubli d'un concept jamais acquis"),
    ("Engagement", "R3 — saut d'engagement > 0.4"),
)


def _esc(text) -> str:
    return html.escape(str(text))


def _collect_success_series(run_log: dict) -> dict:
    series = {}
    for i, session in enumerate(run_log["sessions"], start=1):
        final_diagnosis = session["iterations"][-1]["diagnosis"]
        for concept, rate in final_diagnosis.get("success_rate_by_concept", {}).items():
            series.setdefault(concept, []).append((i, rate))
    return series


def _collect_memory_trajectory(run_log: dict) -> dict:
    trajectory = {}
    for i, session in enumerate(run_log["sessions"], start=1):
        for sid, mem in session.get("memory_snapshot", {}).items():
            trajectory.setdefault(sid, []).append((
                i,
                len(mem["mastered_concepts"]),
                len(mem["shaky_concepts"]),
                len(mem["forgotten_concepts"]),
            ))
    return trajectory


def _label_for_reason(reason: str) -> str:
    for needle, label in RULE_LABELS:
        if needle in reason:
            return label
    return "Autre"


def _collect_drift_rule_counts(run_log: dict) -> dict:
    counts = {}
    for session in run_log["sessions"]:
        for it in session["iterations"]:
            for sid, reasons in it.get("drift_corrections", {}).items():
                for reason in reasons:
                    key = (_label_for_reason(reason), sid)
                    counts[key] = counts.get(key, 0) + 1
    return counts


def _collect_halflife(run_log: dict) -> list:
    """Pour chaque concept : son pic de réussite, sa dernière mesure, et la perte entre les deux."""
    rows = []
    for concept, points in sorted(_collect_success_series(run_log).items()):
        pts = sorted(points)
        if len(pts) < 2:
            continue
        peak_session, peak_rate = max(pts, key=lambda p: p[1])
        last_session, last_rate = pts[-1]
        if last_session <= peak_session:
            continue
        rows.append({
            "concept": concept,
            "peak_session": peak_session, "peak_rate": peak_rate,
            "last_session": last_session, "last_rate": last_rate,
            "drop": peak_rate - last_rate,
            "span": last_session - peak_session,
        })
    return sorted(rows, key=lambda r: r["drop"], reverse=True)


def _collect_student_scores(run_log: dict) -> dict:
    """Réussite cumulée par élève, agrégée depuis les corrections du Diagnostician."""
    tally = {}
    for session in run_log["sessions"]:
        for it in session["iterations"]:
            for graded in it["diagnosis"].get("graded_answers", []):
                correct, total = tally.get(graded["student_id"], (0, 0))
                tally[graded["student_id"]] = (correct + (1 if graded["correct"] else 0), total + 1)
    return tally


def _collect_revision_gains(run_log: dict) -> list:
    """Taux de réussite du concept de la séance, avant et après réécriture."""
    gains = []
    for i, session in enumerate(run_log["sessions"], start=1):
        iterations = session["iterations"]
        if len(iterations) < 2:
            continue
        concept = session["spec"]["focus"]
        before = iterations[0]["diagnosis"].get("success_rate_by_concept", {}).get(concept)
        after = iterations[-1]["diagnosis"].get("success_rate_by_concept", {}).get(concept)
        if before is None or after is None:
            continue
        gains.append({
            "session": i, "title": session["spec"]["title"], "concept": concept,
            "before": before, "after": after, "gain": after - before,
        })
    return gains


def _collect_call_budget(run_log: dict) -> dict:
    """Appels LLM du run, déduits du nombre d'itérations, d'élèves et de révisions."""
    sessions = run_log["sessions"]
    students = len(sessions[0].get("memory_snapshot", {})) if sessions else 0
    iterations = sum(len(s["iterations"]) for s in sessions)
    revisions = sum(1 for s in sessions for it in s["iterations"] if it.get("revision_notes_used"))

    per_agent = [
        ("Élèves-agents", iterations * students),
        ("Generator", iterations),
        ("Diagnostician", iterations),
        ("Reviser", revisions),
        ("Planner", 1 if sessions else 0),
        ("DriftWatcher", 0),
    ]
    total = sum(n for _label, n in per_agent)
    # Les élèves d'une même itération partent en parallèle : ils comptent pour une étape.
    sequential_depth = (1 if sessions else 0) + iterations * 3 + revisions
    return {
        "per_agent": per_agent,
        "total": total,
        "students": students,
        "sequential_depth": sequential_depth,
        "saved": total - sequential_depth,
    }


def _graticule(width: int, height: int, step: int = 40) -> str:
    lines = []
    x = step
    while x < width:
        lines.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" class="grat" />')
        x += step
    y = step
    while y < height:
        lines.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" class="grat" />')
        y += step
    return f'<g class="graticule">{"".join(lines)}</g>'


def _svg_retention_chart(series: dict, width: int = 860, height: int = 380) -> str:
    if not series:
        return '<p class="empty">Pas assez de données pour la courbe de rétention.</p>'

    pad_left, pad_right, pad_top, pad_bottom = 62, 28, 28, 46
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    max_session = max((pt[0] for pts in series.values() for pt in pts), default=1)
    max_session = max(max_session, 2)
    sorted_concepts = sorted(series.items())

    def x(session_idx):
        return pad_left + (session_idx - 1) / (max_session - 1) * plot_w

    def y(rate):
        return pad_top + (1 - rate) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart chart--attached" role="img" '
             f'aria-label="Courbe de rétention par concept">']
    parts.append(_graticule(width, height))

    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_top + (1 - frac) * plot_h
        parts.append(f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width - pad_right}" y2="{gy:.1f}" class="axis-rule" />')
        parts.append(f'<text x="{pad_left - 12}" y="{gy + 4:.1f}" class="tick" text-anchor="end">{int(frac * 100)}</text>')

    parts.append(f'<text x="{pad_left - 12}" y="{pad_top - 12}" class="tick tick--unit" text-anchor="end">%</text>')

    for s in range(1, max_session + 1):
        gx = x(s)
        parts.append(f'<line x1="{gx:.1f}" y1="{pad_top}" x2="{gx:.1f}" y2="{pad_top + plot_h}" class="axis-tickline" />')
        parts.append(f'<text x="{gx:.1f}" y="{height - pad_bottom + 24}" class="tick" text-anchor="middle">S{s}</text>')

    for idx, (concept, points) in enumerate(sorted_concepts):
        color = CATEGORICAL[idx % len(CATEGORICAL)]
        points_sorted = sorted(points)
        path_d = " ".join(
            f'{"M" if i == 0 else "L"}{x(s):.1f},{y(r):.1f}' for i, (s, r) in enumerate(points_sorted)
        )
        parts.append(f'<path d="{path_d}" class="trace" style="stroke:{color}" fill="none" />')
        for s, r in points_sorted:
            parts.append(
                f'<circle cx="{x(s):.1f}" cy="{y(r):.1f}" r="5" style="fill:{color}" class="node-dot">'
                f'<title>{_esc(concept)} : {r:.0%} de réussite en séance {s}</title></circle>'
            )

    parts.append("</svg>")

    legend = "".join(
        f'<span class="legend-item"><span class="legend-trace" style="background:{CATEGORICAL[idx % len(CATEGORICAL)]}"></span>{_esc(concept)}</span>'
        for idx, (concept, _points) in enumerate(sorted_concepts)
    )
    return f'<div class="panel">{"".join(parts)}<div class="legend">{legend}</div></div>'


def _svg_memory_trajectory(trajectory: dict, width: int = 860) -> str:
    if not trajectory:
        return '<p class="empty">Pas de trajectoire mémoire disponible.</p>'

    row_h, bar_w, gap, label_w = 86, 46, 16, 176
    height = row_h * len(trajectory) + 28
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart chart--attached" role="img" '
             f'aria-label="Trajectoire mémoire par élève">']
    parts.append(_graticule(width, height))

    for row_idx, (sid, points) in enumerate(sorted(trajectory.items())):
        points_sorted = sorted(points)
        max_count = max((m + s + f for _, m, s, f in points_sorted), default=1) or 1
        row_y = row_idx * row_h + 14
        parts.append(f'<line x1="0" y1="{row_y - 4}" x2="{width}" y2="{row_y - 4}" class="axis-rule" />')
        parts.append(f'<text x="4" y="{row_y + row_h / 2:.1f}" class="subject-id" dominant-baseline="middle">{_esc(sid)}</text>')
        for i, (session_idx, mastered, shaky, forgotten) in enumerate(points_sorted):
            bx = label_w + i * (bar_w + gap)
            scale = (row_h - 34) / max_count
            by = row_y + row_h - 24
            for count, cls, tag in (
                (mastered, "mem mem--held", "retenu"),
                (shaky, "mem mem--fragile", "fragile"),
                (forgotten, "mem mem--lost", "oublié"),
            ):
                seg_h = count * scale
                by -= seg_h
                if count:
                    # 2px de respiration dans la couleur de surface entre segments empilés
                    parts.append(f'<rect x="{bx}" y="{by:.1f}" width="{bar_w}" height="{max(seg_h - 2, 1):.1f}" class="{cls}">'
                                  f'<title>{_esc(sid)}, séance {session_idx} : {count} {tag}</title></rect>')
            parts.append(f'<text x="{bx + bar_w / 2:.1f}" y="{row_y + row_h - 6}" class="tick" text-anchor="middle">S{session_idx}</text>')

    parts.append("</svg>")

    legend = (
        '<span class="legend-item"><span class="legend-swatch mem--held"></span>retenu</span>'
        '<span class="legend-item"><span class="legend-swatch mem--fragile"></span>fragile</span>'
        '<span class="legend-item"><span class="legend-swatch mem--lost"></span>oublié</span>'
    )
    return f'<div class="panel">{"".join(parts)}<div class="legend">{legend}</div></div>'


def _svg_architecture_diagram() -> str:
    w, h = 900, 430
    box_w, box_h = 168, 66

    nodes = [
        ("Planner", "1 appel LLM / run", 40, 62, "llm"),
        ("Generator", "1 appel / itération", 268, 62, "llm"),
        ("Élèves-agents", "5 appels parallèles", 496, 62, "llm"),
        ("DriftWatcher", "0 LLM, déterministe", 724, 62, "rule"),
        ("Reviser", "1 appel si révision", 180, 258, "llm"),
        ("Diagnostician", "1 appel / itération", 496, 258, "llm"),
    ]

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart chart--attached diagram" role="img" '
             f'aria-label="Architecture agentique : Planner, Generator, Élèves-agents, DriftWatcher, Diagnostician, Reviser">']
    parts.append(_graticule(w, h))
    parts.append(
        '<defs>'
        '<marker id="tip-content" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
        '<path d="M0,0.5 L8,4.5 L0,8.5 Z" fill="var(--ch-content)" /></marker>'
        '<marker id="tip-plaus" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
        '<path d="M0,0.5 L8,4.5 L0,8.5 Z" fill="var(--ch-plaus)" /></marker>'
        '<marker id="tip-flow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
        '<path d="M0,0.5 L8,4.5 L0,8.5 Z" fill="var(--vapor)" /></marker>'
        '</defs>'
    )

    coords = {}
    for label, meta, bx, by, kind in nodes:
        coords[label] = (bx, by, box_w, box_h)
        if kind == "rule":
            cut = 12
            pts = (f"{bx + cut},{by} {bx + box_w},{by} {bx + box_w},{by + box_h - cut} "
                   f"{bx + box_w - cut},{by + box_h} {bx},{by + box_h} {bx},{by + cut}")
            parts.append(f'<polygon points="{pts}" class="node node--rule" />')
        else:
            parts.append(f'<rect x="{bx}" y="{by}" width="{box_w}" height="{box_h}" rx="4" class="node node--llm" />')
        parts.append(f'<text x="{bx + box_w / 2}" y="{by + 28}" class="node-name" text-anchor="middle">{label}</text>')
        parts.append(f'<text x="{bx + box_w / 2}" y="{by + 47}" class="node-meta" text-anchor="middle">{meta}</text>')

    def between(a, b):
        ax, ay, aw, ah = coords[a]
        bx, by, bw, bh = coords[b]
        return ax + aw, ay + ah / 2, bx, by + bh / 2

    x1, y1, x2, y2 = between("Planner", "Generator")
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="wire wire--flow" marker-end="url(#tip-flow)" />')
    x1, y1, x2, y2 = between("Generator", "Élèves-agents")
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="wire wire--flow" marker-end="url(#tip-flow)" />')

    x1, y1, x2, y2 = between("Élèves-agents", "DriftWatcher")
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="wire wire--plaus" marker-end="url(#tip-plaus)" />')
    parts.append(f'<text x="{(x1 + x2) / 2}" y="{y1 - 34}" class="wire-label wire-label--plaus" text-anchor="middle">valide, rejoue</text>')

    ex, ey, ew, eh = coords["Élèves-agents"]
    dgx, dgy, dgw, dgh = coords["Diagnostician"]
    vx = ex + ew / 2
    parts.append(f'<line x1="{vx}" y1="{ey + eh}" x2="{vx}" y2="{dgy}" class="wire wire--content" marker-end="url(#tip-content)" />')
    parts.append(f'<text x="{vx + 14}" y="{(ey + eh + dgy) / 2}" class="wire-label wire-label--content">réponses aux exercices</text>')

    rx, ry, rw, rh = coords["Reviser"]
    parts.append(f'<line x1="{dgx}" y1="{dgy + dgh / 2}" x2="{rx + rw}" y2="{ry + rh / 2}" class="wire wire--content" marker-end="url(#tip-content)" />')
    parts.append(f'<text x="{(dgx + rx + rw) / 2}" y="{ry + rh / 2 - 16}" class="wire-label wire-label--content" text-anchor="middle">si révision nécessaire</text>')

    gx, gy, gw, gh = coords["Generator"]
    parts.append(f'<line x1="{rx + rw / 2}" y1="{ry}" x2="{gx + gw / 2}" y2="{gy + gh}" class="wire wire--content wire--return" marker-end="url(#tip-content)" />')
    # Ce libellé est le seul posé sur une diagonale : sans fond, le trait le traverse.
    lx, ly = gx + gw / 2 - 14, (ry + gy + gh) / 2
    parts.append(f'<rect x="{lx - 50}" y="{ly - 11}" width="56" height="16" class="label-backing" />')
    parts.append(f'<text x="{lx}" y="{ly}" class="wire-label wire-label--content" text-anchor="end">réécrit</text>')

    parts.append(f'<line x1="40" y1="{h - 54}" x2="{w - 40}" y2="{h - 54}" class="axis-rule" />')
    parts.append(f'<line x1="40" y1="{h - 30}" x2="76" y2="{h - 30}" class="wire wire--content" />')
    parts.append(f'<text x="86" y="{h - 26}" class="tick">Signal qualité : déclenche une révision du contenu</text>')
    parts.append(f'<line x1="470" y1="{h - 30}" x2="506" y2="{h - 30}" class="wire wire--plaus" />')
    parts.append(f'<text x="516" y="{h - 26}" class="tick">Signal plausibilité : ne touche jamais au contenu</text>')

    parts.append("</svg>")
    return f'<div class="panel panel--diagram">{"".join(parts)}</div>'


def _svg_session_timeline(run_log: dict) -> str:
    """Déroulé temporel d'une séance : ce qui s'enchaîne, ce qui part en parallèle,
    et ce qui arrête la boucle. Le diagramme d'architecture montre la topologie ;
    celui-ci montre le temps."""
    sessions = run_log["sessions"]
    students = len(sessions[0].get("memory_snapshot", {})) if sessions else 5
    max_iter = max((len(s["iterations"]) for s in sessions), default=2)

    w, h = 900, 470
    lanes = [
        ("Generator", 36, 132),
        ("Élèves-agents", 196, 168),
        ("DriftWatcher", 394, 150),
        ("Diagnostician", 572, 152),
        ("Reviser", 762, 102),
    ]
    lane_x = {name: (x, width) for name, x, width in lanes}

    def centre(name):
        x, width = lane_x[name]
        return x + width / 2

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart chart--attached" role="img" '
             f'aria-label="Déroulé temporel d\'une séance, itération par itération">']
    parts.append(_graticule(w, h))

    for name, x, width in lanes:
        parts.append(f'<text x="{x + width / 2}" y="24" class="lane-head" text-anchor="middle">{name}</text>')
        parts.append(f'<line x1="{x + width / 2}" y1="34" x2="{x + width / 2}" y2="{h - 96}" class="lane-line" />')

    def step(name, y, label, kind="llm"):
        x, width = lane_x[name]
        cls = "step step--rule" if kind == "rule" else "step"
        parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="34" rx="3" class="{cls}" />')
        parts.append(f'<text x="{x + width / 2}" y="{y + 22}" class="step-label" text-anchor="middle">{label}</text>')

    def arrow(x1, y1, x2, y2, channel="flow", dashed=False):
        cls = {"flow": "wire wire--flow", "content": "wire wire--content", "plaus": "wire wire--plaus"}[channel]
        tip = {"flow": "tip-flow", "content": "tip-content", "plaus": "tip-plaus"}[channel]
        dash = ' stroke-dasharray="3 5"' if dashed else ""
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}"{dash} marker-end="url(#{tip})" />')

    for index, top in enumerate((62, 232)):
        last = index == 1
        parts.append(f'<text x="36" y="{top - 22}" class="iter-tag">ITÉR. {index}</text>')
        parts.append(f'<line x1="0" y1="{top - 14}" x2="{w}" y2="{top - 14}" class="axis-rule" />')

        step("Generator", top, "écrit la leçon" if index == 0 else "réécrit")

        # les N élèves partent ensemble : N barres au même instant, pas en escalier
        ex, ew = lane_x["Élèves-agents"]
        for k in range(students):
            by = top - 6 + k * 9
            parts.append(f'<rect x="{ex}" y="{by}" width="{ew}" height="7" rx="2" class="step step--parallel" />')
        parts.append(f'<text x="{ex + ew / 2}" y="{top + 58}" class="step-label" text-anchor="middle">'
                      f'{students} élèves en parallèle</text>')

        step("DriftWatcher", top, "valide", kind="rule")
        parts.append(f'<path d="M{centre("DriftWatcher") - 26},{top + 44} a 26 16 0 1 0 52 0" class="wire wire--plaus" '
                      f'marker-end="url(#tip-plaus)" fill="none" />')
        parts.append(f'<text x="{centre("DriftWatcher")}" y="{top + 74}" class="step-note" text-anchor="middle">'
                      f'rejeu 1 fois, sinon corrige</text>')

        step("Diagnostician", top, "corrige, diagnostique")

        gx, gw = lane_x["Generator"]
        arrow(gx + gw, top + 17, ex, top + 17)
        arrow(ex + ew, top + 17, lane_x["DriftWatcher"][0], top + 17, channel="plaus")
        arrow(lane_x["DriftWatcher"][0] + lane_x["DriftWatcher"][1], top + 17,
              lane_x["Diagnostician"][0], top + 17, channel="content")

        if not last:
            step("Reviser", top, "note de révision")
            arrow(lane_x["Diagnostician"][0] + lane_x["Diagnostician"][1], top + 17,
                  lane_x["Reviser"][0], top + 17, channel="content")
            parts.append(f'<text x="{centre("Diagnostician")}" y="{top + 58}" class="step-note" '
                          f'text-anchor="middle">révision nécessaire</text>')
            # retour vers le Generator de l'itération suivante
            parts.append(f'<path d="M{centre("Reviser")},{top + 34} L{centre("Reviser")},{top + 128} '
                          f'L{centre("Generator")},{top + 128} L{centre("Generator")},{top + 170}" '
                          f'class="wire wire--content" stroke-dasharray="3 5" fill="none" '
                          f'marker-end="url(#tip-content)" />')
        else:
            parts.append(f'<text x="{centre("Diagnostician")}" y="{top + 58}" class="step-note step-note--stop" '
                          f'text-anchor="middle">plus de révision nécessaire</text>')
            arrow(centre("Diagnostician"), top + 34, centre("Diagnostician"), top + 150)

    commit_y = h - 76
    parts.append(f'<rect x="36" y="{commit_y}" width="834" height="40" rx="3" class="step step--commit" />')
    parts.append(f'<text x="453" y="{commit_y + 25}" class="step-label" text-anchor="middle">'
                  f'séance figée : les {students} mémoires sont réécrites par les élèves eux-mêmes, puis archivées</text>')
    parts.append(f'<text x="36" y="{h - 12}" class="step-note">La boucle s\'arrête dès que le Diagnostician ne demande '
                  f'plus de révision, et au plus tard après {max_iter} itérations.</text>')

    parts.append("</svg>")
    return f'<div class="panel">{"".join(parts)}</div>'


def _render_halflife(run_log: dict) -> str:
    rows = _collect_halflife(run_log)
    if not rows:
        return ('<p class="empty">Aucun concept n\'a été retesté après son pic : la demi-vie '
                'demande au moins deux mesures du même concept.</p>')

    worst = rows[0]
    items = ""
    for row in rows:
        bar_pct = min(row["drop"] / max(row["peak_rate"], 0.01), 1.0) * 100
        items += f"""
        <li class="decay">
          <span class="decay-name">{_esc(row["concept"])}</span>
          <span class="decay-track"><span class="decay-fill" style="width:{bar_pct:.0f}%"></span></span>
          <span class="decay-figure">-{row["drop"] * 100:.0f} pts</span>
          <span class="decay-detail">{row["peak_rate"]:.0%} en S{row["peak_session"]}
            puis {row["last_rate"]:.0%} en S{row["last_session"]}, soit {row["span"]} séance{"s" if row["span"] > 1 else ""} plus tard</span>
        </li>"""

    return f"""
    <div class="panel panel--pad">
      <p class="finding">Le concept qui se dégrade le plus vite est <b>{_esc(worst["concept"])}</b> :
         il perd <b>{worst["drop"] * 100:.0f} points</b> de réussite en {worst["span"]}
         séance{"s" if worst["span"] > 1 else ""} après son pic.</p>
      <ul class="decay-list">{items}</ul>
    </div>"""


def _render_student_divergence(run_log: dict) -> str:
    tally = _collect_student_scores(run_log)
    if not tally:
        return '<p class="empty">Aucune réponse corrigée dans ce run.</p>'

    scored = sorted(
        ((sid, correct / total if total else 0.0, correct, total) for sid, (correct, total) in tally.items()),
        key=lambda r: r[1], reverse=True,
    )
    spread = scored[0][1] - scored[-1][1]
    verdict = ("Les profils se comportent bien différemment : le système ne simule pas cinq fois le même élève."
               if spread >= 0.15 else
               "Les profils se ressemblent trop pour être considérés comme distincts : le simulateur produit "
               "des élèves quasi identiques, ce qui affaiblit toute conclusion tirée de leur diversité.")

    rows = ""
    for sid, rate, correct, total in scored:
        rows += f"""
        <li class="subject">
          <span class="subject-name">{_esc(sid)}</span>
          <span class="subject-track"><span class="subject-fill" style="width:{rate * 100:.0f}%"></span></span>
          <span class="subject-figure">{rate:.0%}</span>
          <span class="subject-detail">{correct}/{total} réponses justes</span>
        </li>"""

    return f"""
    <div class="panel panel--pad">
      <p class="finding">Écart entre le profil le plus solide et le plus fragile :
         <b>{spread * 100:.0f} points</b>. {verdict}</p>
      <ul class="subject-list">{rows}</ul>
    </div>"""


def _render_revision_gains(run_log: dict) -> str:
    gains = _collect_revision_gains(run_log)
    if not gains:
        return '<p class="empty">Aucune séance n\'a été réécrite sur ce run.</p>'

    average = sum(g["gain"] for g in gains) / len(gains)
    rows = ""
    for g in gains:
        rows += f"""
        <tr>
          <td><span class="cell-index">S{g["session"]}</span>{_esc(g["title"])}</td>
          <td class="mono">{g["before"]:.0%}</td>
          <td class="mono">{g["after"]:.0%}</td>
          <td class="mono gain">+{g["gain"] * 100:.0f} pts</td>
        </tr>"""

    return f"""
    <div class="panel">
      <p class="finding finding--inset">Sur les {len(gains)} séances réécrites, la réécriture rapporte en moyenne
         <b>{average * 100:.0f} points</b> de réussite sur le concept visé. Le canal qualité produit donc un gain
         mesurable, et pas seulement une reformulation.</p>
      <table class="rules">
        <thead><tr><th>Séance réécrite</th><th>Avant</th><th>Après</th><th>Gain</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def _render_call_budget(run_log: dict) -> str:
    budget = _collect_call_budget(run_log)
    if not budget["total"]:
        return '<p class="empty">Aucun appel comptabilisé sur ce run.</p>'

    bars = ""
    for label, count in budget["per_agent"]:
        pct = count / budget["total"] * 100 if budget["total"] else 0
        muted = " budget-row--zero" if count == 0 else ""
        bars += f"""
        <li class="budget-row{muted}">
          <span class="budget-name">{_esc(label)}</span>
          <span class="budget-track"><span class="budget-fill" style="width:{pct:.1f}%"></span></span>
          <span class="budget-figure">{count}</span>
        </li>"""

    return f"""
    <div class="panel panel--pad">
      <p class="finding">Ce run coûte <b>{budget["total"]} appels LLM</b>, dont
         {budget["per_agent"][0][1]} pour les seuls élèves-agents. Comme les {budget["students"]} élèves d'une même
         itération partent en parallèle, le chemin critique ne fait que <b>{budget["sequential_depth"]} étapes</b>
         au lieu de {budget["total"]} : la parallélisation économise {budget["saved"]} attentes successives.</p>
      <ul class="budget-list">{bars}</ul>
      <p class="budget-note">Le DriftWatcher est à zéro appel : c'est le seul agent entièrement déterministe,
         et il valide pourtant chaque réaction d'élève.</p>
    </div>"""


def _render_diff_cards(run_log: dict) -> str:
    cards = []
    for i, session in enumerate(run_log["sessions"], start=1):
        iterations = session["iterations"]
        if len(iterations) < 2:
            continue
        before = iterations[0]["content"]["lesson"]
        after = iterations[-1]["content"]["lesson"]
        notes = iterations[-1]["revision_notes_used"] or ""
        cards.append(f"""
        <article class="revision">
          <header class="revision-head">
            <span class="revision-index">Séance {i}</span>
            <h3>{_esc(session["spec"]["title"])}</h3>
          </header>
          <p class="revision-note"><span class="note-key">Note du Reviser</span>{_esc(notes)}</p>
          <div class="revision-body">
            <div class="draft draft--before"><span class="draft-key">v1</span><p>{_esc(before)}</p></div>
            <div class="draft draft--after"><span class="draft-key">v2</span><p>{_esc(after)}</p></div>
          </div>
        </article>""")
    if not cards:
        return '<p class="empty">Aucune séance n\'a nécessité de révision sur ce run.</p>'
    return "".join(cards)


def _render_drift_table(run_log: dict) -> str:
    counts = _collect_drift_rule_counts(run_log)
    flags = []
    for session in run_log["sessions"]:
        for it in session["iterations"]:
            flags.extend(it.get("run_drift_flags", []))

    if counts:
        rows = "".join(
            f'<tr><td class="rule-cell">{_esc(label)}</td><td class="mono">{_esc(sid)}</td>'
            f'<td class="mono count">{n}</td></tr>'
            for (label, sid), n in sorted(counts.items())
        )
    else:
        rows = '<tr><td colspan="3" class="empty">Aucune correction déclenchée sur ce run.</td></tr>'

    flags_html = ""
    if flags:
        items = "".join(f"<li>{_esc(f)}</li>" for f in sorted(set(flags)))
        flags_html = (f'<div class="alert"><span class="alert-key">Trajectoire suspecte</span>'
                      f'<ul>{items}</ul></div>')

    return f"""
    <div class="panel">
      <table class="rules">
        <thead><tr><th>Règle</th><th>Élève</th><th class="count">Déclenchements</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    {flags_html}
    """


def render_html_report(run_log: dict) -> str:
    success_series = _collect_success_series(run_log)
    trajectory = _collect_memory_trajectory(run_log)
    n_sessions = len(run_log["sessions"])
    n_corrections = sum(
        len(it.get("drift_corrections", {}))
        for session in run_log["sessions"]
        for it in session["iterations"]
    )
    n_revisions = sum(
        1 for session in run_log["sessions"] for it in session["iterations"]
        if it.get("revision_notes_used")
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>La Classe Fantôme, rapport de run {_esc(run_log["run_id"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
<style>
  :root {{
    color-scheme: dark;
    --plate: #080d0c;
    --panel: #0f1614;
    --panel-lift: #141d1a;
    --graticule: #16211e;
    --rule: #223029;
    --filament: #f0f4f1;
    --vapor: #a9bab3;
    --vapor-dim: #7d918a;
    --ch-content: #ff6a5e;
    --ch-plaus: #4fd6bd;
    --mem-held: #eef4f0;
    --mem-fragile: #93aca4;
    --mem-lost: #5a7268;
    --sans: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
    --mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", monospace;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    background: var(--plate);
    color: var(--filament);
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}

  .sheet {{ max-width: 1000px; margin: 0 auto; padding: 72px 32px 96px; }}

  /* ---- en-tête : la thèse, pas le nom du projet ---- */
  .mark {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: var(--vapor-dim);
    margin-bottom: 28px;
  }}
  .thesis {{
    font-size: clamp(34px, 5.4vw, 58px);
    font-weight: 700;
    line-height: 1.04;
    letter-spacing: -0.03em;
    margin: 0 0 28px;
    max-width: 22ch;
  }}
  .thesis em {{ font-style: normal; color: var(--ch-content); }}
  .specimen {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px 36px;
    border-top: 1px solid var(--rule);
    padding-top: 16px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--vapor);
  }}
  .specimen b {{ color: var(--vapor-dim); font-weight: 500; margin-right: 8px; }}

  /* ---- rail de mesures : deux signaux forts, deux contextes discrets ---- */
  .rail {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1.35fr)) repeat(2, minmax(0, 1fr));
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
    margin: 52px 0 64px;
  }}
  .cell {{ background: var(--panel); padding: 22px 20px 20px; }}
  .cell-key {{
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--vapor-dim);
    display: block;
    margin-bottom: 14px;
  }}
  .cell-value {{ font-family: var(--mono); font-weight: 700; font-size: 38px; line-height: 1; }}
  .cell-note {{ font-size: 12.5px; color: var(--vapor); margin-top: 10px; }}
  .cell--signal {{ background: var(--panel-lift); }}
  .cell--signal .cell-value {{ font-size: 50px; }}
  .cell--content .cell-value {{ color: var(--ch-content); }}
  .cell--plaus .cell-value {{ color: var(--ch-plaus); }}
  .cell--content {{ box-shadow: inset 3px 0 0 var(--ch-content); }}
  .cell--plaus {{ box-shadow: inset 3px 0 0 var(--ch-plaus); }}
  .cell--quiet .cell-value {{ color: var(--vapor); font-size: 30px; }}

  /* ---- sections ---- */
  section {{ margin-bottom: 80px; }}
  .sec-head {{ display: flex; align-items: baseline; gap: 16px; margin-bottom: 10px; }}
  h2 {{ font-size: 23px; font-weight: 600; letter-spacing: -0.015em; margin: 0; }}
  .chan {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    padding: 3px 8px;
    border: 1px solid currentColor;
    white-space: nowrap;
  }}
  .chan--content {{ color: var(--ch-content); }}
  .chan--plaus {{ color: var(--ch-plaus); }}
  .chan--subject {{ color: var(--vapor-dim); }}
  .lede {{ color: var(--vapor); max-width: 68ch; margin: 0 0 26px; }}
  .lede b {{ color: var(--filament); font-weight: 500; }}

  /* ---- panneaux d'instrument ---- */
  .panel {{ background: var(--panel); border: 1px solid var(--rule); }}
  .panel--diagram {{ background: var(--panel); }}
  .chart {{ width: 100%; height: auto; display: block; }}
  .grat {{ stroke: var(--graticule); stroke-width: 1; }}
  .axis-rule {{ stroke: var(--rule); stroke-width: 1; }}
  .axis-tickline {{ stroke: var(--graticule); stroke-width: 1; }}
  .tick {{ fill: var(--vapor-dim); font-family: var(--mono); font-size: 11px; }}
  .tick--unit {{ fill: var(--vapor-dim); }}
  .subject-id {{ fill: var(--vapor); font-family: var(--mono); font-size: 12px; }}
  .trace {{ stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
  .node-dot {{ stroke: var(--panel); stroke-width: 2; }}

  .legend {{ display: flex; flex-wrap: wrap; gap: 10px 22px; padding: 14px 18px; border-top: 1px solid var(--rule); font-family: var(--mono); font-size: 11.5px; color: var(--vapor); }}
  .legend-item {{ display: inline-flex; align-items: center; gap: 8px; }}
  .legend-trace {{ width: 16px; height: 2px; display: inline-block; }}
  .legend-swatch {{ width: 11px; height: 11px; display: inline-block; }}
  .legend-swatch.mem--held {{ background: var(--mem-held); }}
  .legend-swatch.mem--fragile {{ background: var(--mem-fragile); }}
  .legend-swatch.mem--lost {{ background: var(--mem-lost); border: 1px solid var(--rule); }}

  .mem--held {{ fill: var(--mem-held); }}
  .mem--fragile {{ fill: var(--mem-fragile); }}
  .mem--lost {{ fill: var(--mem-lost); }}

  /* ---- diagramme : la grammaire de trait ---- */
  .node--llm {{ fill: var(--panel-lift); stroke: var(--rule); stroke-width: 1.5; }}
  .node--rule {{ fill: rgba(79, 214, 189, 0.07); stroke: var(--ch-plaus); stroke-width: 1.5; stroke-dasharray: 5 3; }}
  .node-name {{ fill: var(--filament); font-family: var(--sans); font-size: 14.5px; font-weight: 600; }}
  .node-meta {{ fill: var(--vapor-dim); font-family: var(--mono); font-size: 10.5px; }}
  .wire {{ stroke-width: 2; fill: none; }}
  .wire--flow {{ stroke: var(--vapor-dim); }}
  .wire--content {{ stroke: var(--ch-content); }}
  .wire--plaus {{ stroke: var(--ch-plaus); stroke-dasharray: 6 4; stroke-linecap: round; }}
  .wire--return {{ stroke-dasharray: 3 5; }}
  .wire-label {{ font-family: var(--mono); font-size: 10.5px; }}
  .wire-label--content {{ fill: var(--ch-content); }}
  .wire-label--plaus {{ fill: var(--ch-plaus); }}
  .label-backing {{ fill: var(--panel); }}

  /* ---- chronogramme : le temps, pas la topologie ---- */
  .lane-head {{ fill: var(--vapor); font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; }}
  .lane-line {{ stroke: var(--graticule); stroke-width: 1; }}
  .iter-tag {{ fill: var(--vapor-dim); font-family: var(--mono); font-size: 10px; letter-spacing: 0.12em; }}
  .step {{ fill: var(--panel-lift); stroke: var(--rule); stroke-width: 1; }}
  .step--rule {{ fill: rgba(79, 214, 189, 0.08); stroke: var(--ch-plaus); stroke-dasharray: 4 3; }}
  .step--parallel {{ fill: var(--panel-lift); stroke: var(--vapor-dim); stroke-width: 1; }}
  .step--commit {{ fill: rgba(255, 106, 94, 0.06); stroke: var(--ch-content); }}
  .step-label {{ fill: var(--filament); font-family: var(--sans); font-size: 12px; font-weight: 500; }}
  .step-note {{ fill: var(--vapor-dim); font-family: var(--mono); font-size: 10px; }}
  .step-note--stop {{ fill: var(--ch-content); }}

  /* Le signal de plausibilité circule en continu vers le DriftWatcher : les tirets
     défilent le long du trait. Seul le canal pointillé bouge, le canal plein reste fixe. */
  @media (prefers-reduced-motion: no-preference) {{
    .diagram .wire--plaus {{ animation: drift 1.6s linear infinite; }}
    @keyframes drift {{
      from {{ stroke-dashoffset: 20; }}
      to {{ stroke-dashoffset: 0; }}
    }}
  }}

  /* ---- révisions ---- */
  .revision {{ border: 1px solid var(--rule); border-left: 3px solid var(--ch-content); background: var(--panel); padding: 22px 24px; margin-bottom: 14px; }}
  .revision-head {{ display: flex; align-items: baseline; gap: 14px; margin-bottom: 14px; }}
  .revision-index {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--vapor-dim); }}
  .revision h3 {{ margin: 0; font-size: 17px; font-weight: 600; }}
  .revision-note {{ font-size: 13.5px; color: var(--vapor); margin: 0 0 18px; }}
  .note-key {{ font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ch-content); display: block; margin-bottom: 4px; }}
  .revision-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--rule); }}
  .draft {{ background: var(--panel-lift); padding: 16px; position: relative; }}
  .draft p {{ margin: 0; font-size: 13.5px; }}
  .draft--before p {{ color: var(--vapor); }}
  .draft-key {{ font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--vapor-dim); display: block; margin-bottom: 8px; }}
  .draft--after .draft-key {{ color: var(--ch-content); }}

  /* ---- table de règles ---- */
  table.rules {{ width: 100%; border-collapse: collapse; }}
  table.rules th, table.rules td {{ text-align: left; padding: 14px 18px; font-size: 13.5px; }}
  table.rules th {{ font-family: var(--mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--vapor-dim); font-weight: 500; border-bottom: 1px solid var(--rule); }}
  table.rules tbody tr + tr td {{ border-top: 1px solid var(--graticule); }}
  .rule-cell {{ box-shadow: inset 3px 0 0 var(--ch-plaus); }}
  td.mono, th.count {{ font-family: var(--mono); }}
  td.count {{ color: var(--ch-plaus); font-weight: 700; }}
  .count {{ text-align: right; }}

  .alert {{ border: 1px solid var(--ch-plaus); border-left-width: 3px; background: rgba(79, 214, 189, 0.05); padding: 16px 20px; margin-top: 16px; }}
  .alert-key {{ font-family: var(--mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ch-plaus); display: block; margin-bottom: 8px; }}
  .alert ul {{ margin: 0; padding-left: 18px; color: var(--vapor); font-size: 13.5px; }}

  .empty {{ color: var(--vapor-dim); font-family: var(--mono); font-size: 12.5px; padding: 18px; }}

  /* ---- constats mesurés : demi-vie, divergence, gain, budget ---- */
  .panel--pad {{ padding: 22px 24px; }}
  .finding {{ margin: 0 0 20px; font-size: 15px; color: var(--vapor); max-width: 74ch; }}
  .finding b {{ color: var(--filament); font-weight: 600; }}
  .finding--inset {{ padding: 20px 20px 0; }}

  .decay-list, .subject-list, .budget-list {{ list-style: none; margin: 0; padding: 0; }}
  .decay, .subject {{
    display: grid;
    grid-template-columns: 168px 1fr 74px;
    align-items: center;
    gap: 0 16px;
    padding: 12px 0;
    border-top: 1px solid var(--graticule);
  }}
  .decay-name, .subject-name {{ font-family: var(--mono); font-size: 12.5px; color: var(--filament); }}
  .decay-track, .subject-track, .budget-track {{ height: 8px; background: var(--panel-lift); position: relative; }}
  .decay-fill {{ display: block; height: 100%; background: var(--ch-content); }}
  .subject-fill {{ display: block; height: 100%; background: var(--mem-fragile); }}
  .budget-fill {{ display: block; height: 100%; background: var(--ch-plaus); }}
  .decay-figure, .subject-figure {{ font-family: var(--mono); font-size: 15px; font-weight: 700; text-align: right; }}
  .decay-figure {{ color: var(--ch-content); }}
  .subject-figure {{ color: var(--filament); }}
  .decay-detail, .subject-detail {{
    grid-column: 2 / -1;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--vapor-dim);
    margin-top: 6px;
  }}

  .budget-row {{
    display: grid;
    grid-template-columns: 168px 1fr 48px;
    align-items: center;
    gap: 0 16px;
    padding: 9px 0;
  }}
  .budget-row--zero .budget-figure {{ color: var(--ch-plaus); }}
  .budget-name {{ font-family: var(--mono); font-size: 12.5px; color: var(--filament); }}
  .budget-figure {{ font-family: var(--mono); font-size: 14px; font-weight: 700; text-align: right; }}
  .budget-note {{ margin: 18px 0 0; font-size: 12.5px; color: var(--vapor-dim); border-top: 1px solid var(--graticule); padding-top: 14px; }}

  td.gain {{ color: var(--ch-content); font-weight: 700; }}
  .cell-index {{ font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.12em; color: var(--vapor-dim); margin-right: 12px; }}

  @media (max-width: 760px) {{
    .decay, .subject, .budget-row {{ grid-template-columns: 1fr 56px; }}
    .decay-track, .subject-track, .budget-track {{ display: none; }}
  }}

  footer {{ border-top: 1px solid var(--rule); padding-top: 22px; color: var(--vapor); font-size: 13px; max-width: 74ch; }}
  footer p {{ margin: 0 0 12px; }}
  footer b {{ color: var(--filament); font-weight: 600; }}

  @media (max-width: 760px) {{
    .sheet {{ padding: 44px 18px 64px; }}
    .rail {{ grid-template-columns: 1fr 1fr; }}
    .revision-body {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="sheet">

  <p class="mark">La Classe Fantôme</p>
  <h1 class="thesis">Ce contenu n'est pas noté sur ce qu'il enseigne. Il est noté sur ce qu'il en <em>reste</em>.</h1>
  <div class="specimen">
    <span><b>run</b>{_esc(run_log["run_id"])}</span>
    <span><b>objectif</b>{_esc(run_log["objective"])}</span>
  </div>

  <div class="rail">
    <div class="cell cell--signal cell--content">
      <span class="cell-key">Signal qualité</span>
      <div class="cell-value">{n_revisions}</div>
      <p class="cell-note">cycles de révision du contenu déclenchés par le Diagnostician</p>
    </div>
    <div class="cell cell--signal cell--plaus">
      <span class="cell-key">Signal plausibilité</span>
      <div class="cell-value">{n_corrections}</div>
      <p class="cell-note">réactions d'élèves corrigées par le DriftWatcher, sans toucher au contenu</p>
    </div>
    <div class="cell cell--quiet">
      <span class="cell-key">Séances</span>
      <div class="cell-value">{n_sessions}</div>
    </div>
    <div class="cell cell--quiet">
      <span class="cell-key">Concepts suivis</span>
      <div class="cell-value">{len(success_series)}</div>
    </div>
  </div>

  <section>
    <div class="sec-head">
      <h2>Architecture agentique</h2>
      <span class="chan chan--content">qualité</span>
      <span class="chan chan--plaus">plausibilité</span>
    </div>
    <p class="lede">Deux canaux qui ne se mélangent jamais. Le Diagnostician mesure la qualité du contenu et peut
       déclencher une réécriture. Le DriftWatcher mesure la plausibilité de la simulation : il rejoue ou corrige la
       réaction d'un élève, mais <b>ne touche jamais au contenu</b>. C'est le seul agent sans appel LLM, et sa forme le dit.</p>
    {_svg_architecture_diagram()}
  </section>

  <section>
    <div class="sec-head">
      <h2>Déroulé d'une séance</h2>
      <span class="chan chan--content">qualité</span>
      <span class="chan chan--plaus">plausibilité</span>
    </div>
    <p class="lede">Le schéma précédent dit qui parle à qui. Celui-ci dit dans quel ordre, ce qui part en même
       temps, et ce qui arrête la boucle. C'est ce déroulé qui explique pourquoi un run de 60 appels ne coûte
       que 28 attentes successives.</p>
    {_svg_session_timeline(run_log)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Rétention par concept</h2>
      <span class="chan chan--content">qualité</span>
    </div>
    <p class="lede">Taux de réussite mesuré à chaque séance où le concept est retesté. Une courbe qui redescend est
       un concept que la classe perd, pas un contenu qui a déplu.</p>
    {_svg_retention_chart(success_series)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Demi-vie mesurée</h2>
      <span class="chan chan--content">qualité</span>
    </div>
    <p class="lede">La courbe ci-dessus se lit ; celle-ci se chiffre. Pour chaque concept retesté après son pic,
       voici ce que la classe en a perdu, et en combien de séances.</p>
    {_render_halflife(run_log)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Trajectoire mémoire</h2>
      <span class="chan chan--subject">sujet</span>
    </div>
    <p class="lede">Ce que chaque élève-agent retient, séance après séance. Ce qui est oublié s'efface vers le fond.</p>
    {_svg_memory_trajectory(trajectory)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Les cinq profils divergent-ils ?</h2>
      <span class="chan chan--subject">sujet</span>
    </div>
    <p class="lede">La question qu'un jury posera en premier : cinq élèves-agents joués par le même modèle
       sont-ils autre chose que cinq copies ? Réponse mesurée sur leurs corrections, pas affirmée.</p>
    {_render_student_divergence(run_log)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Contenu réécrit</h2>
      <span class="chan chan--content">qualité</span>
    </div>
    <p class="lede">Ce que le Reviser a demandé, et ce que le Generator a produit en réponse.</p>
    {_render_diff_cards(run_log)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Ce que la réécriture a gagné</h2>
      <span class="chan chan--content">qualité</span>
    </div>
    <p class="lede">Réécrire coûte une itération complète. Reste à savoir si ça paie : voici le taux de réussite
       du concept visé avant et après le passage du Reviser.</p>
    {_render_revision_gains(run_log)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Contrôles de plausibilité</h2>
      <span class="chan chan--plaus">plausibilité</span>
    </div>
    <p class="lede">Trois règles déterministes gardent la classe synthétique crédible : un concept ne se maîtrise pas
       sans avoir été enseigné, ne s'oublie pas sans avoir été acquis, et l'engagement ne bondit pas de plus de 0.4
       en une séance.</p>
    {_render_drift_table(run_log)}
  </section>

  <section>
    <div class="sec-head">
      <h2>Budget d'appels du run</h2>
      <span class="chan chan--subject">système</span>
    </div>
    <p class="lede">Ce que l'architecture coûte réellement, et ce que la parallélisation des élèves lui fait
       économiser en attentes successives.</p>
    {_render_call_budget(run_log)}
  </section>

  <footer>
    <p><b>Ce que ce rapport ne prouve pas.</b> Les élèves-agents sont des simulations produites par un LLM, pas de
       vrais apprenants : le système optimise donc son contenu contre la représentation que le modèle se fait d'un
       élève en difficulté. Le Generator partage ce modèle avec les élèves qui le jugent, ce qui expose le système à
       des révisions complaisantes.</p>
    <p><b>Protocole de validation proposé.</b> Rejouer un sous-ensemble des séances générées avec de vrais élèves,
       comparer leur taux de réussite réel par concept à celui prédit par le Diagnostician, et mesurer l'écart. Tant
       que cet écart n'est pas mesuré, les courbes ci-dessus décrivent le comportement du simulateur, pas celui d'une
       classe.</p>
  </footer>

</div>
</body>
</html>
"""


def save_html_report(run_log: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html_report(run_log))
