import html
import os

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

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


def _svg_retention_chart(series: dict, width: int = 760, height: int = 340) -> str:
    if not series:
        return '<p class="empty">Pas assez de données pour la courbe de rétention.</p>'

    pad_left, pad_right, pad_top, pad_bottom = 56, 24, 24, 40
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    max_session = max((pt[0] for pts in series.values() for pt in pts), default=1)
    max_session = max(max_session, 2)
    sorted_concepts = sorted(series.items())
    use_direct_labels = len(sorted_concepts) <= 4

    def x(session_idx):
        return pad_left + (session_idx - 1) / (max_session - 1) * plot_w

    def y(rate):
        return pad_top + (1 - rate) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
             f'aria-label="Courbe de rétention par concept">']

    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_top + (1 - frac) * plot_h
        parts.append(f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width - pad_right}" y2="{gy:.1f}" class="gridline" />')
        parts.append(f'<text x="{pad_left - 10}" y="{gy + 4:.1f}" class="axis-label" text-anchor="end">{int(frac * 100)}%</text>')

    for s in range(1, max_session + 1):
        gx = x(s)
        parts.append(f'<text x="{gx:.1f}" y="{height - pad_bottom + 20}" class="axis-label" text-anchor="middle">S{s}</text>')

    for idx, (concept, points) in enumerate(sorted_concepts):
        color = CATEGORICAL[idx % len(CATEGORICAL)]
        points_sorted = sorted(points)
        path_d = " ".join(
            f'{"M" if i == 0 else "L"}{x(s):.1f},{y(r):.1f}' for i, (s, r) in enumerate(points_sorted)
        )
        parts.append(f'<path d="{path_d}" class="line" style="stroke:{color}" fill="none" />')
        for s, r in points_sorted:
            parts.append(
                f'<circle cx="{x(s):.1f}" cy="{y(r):.1f}" r="5" style="fill:{color}" class="marker">'
                f'<title>{_esc(concept)} — séance {s} : {r:.0%} de réussite</title></circle>'
            )
        if use_direct_labels:
            last_s, last_r = points_sorted[-1]
            parts.append(
                f'<text x="{x(last_s) + 10:.1f}" y="{y(last_r) + 4:.1f}" class="direct-label">{_esc(concept)}</text>'
            )

    parts.append("</svg>")

    legend = "".join(
        f'<span class="legend-item"><span class="legend-dot" style="background:{CATEGORICAL[idx % len(CATEGORICAL)]}"></span>{_esc(concept)}</span>'
        for idx, (concept, _points) in enumerate(sorted_concepts)
    )
    svg_no_border = "\n".join(parts).replace('class="chart"', 'class="chart chart--attached"')
    return f'<div class="chart-card">{svg_no_border}<div class="legend">{legend}</div></div>'


def _svg_memory_trajectory(trajectory: dict, width: int = 760) -> str:
    if not trajectory:
        return '<p class="empty">Pas de trajectoire mémoire disponible.</p>'

    row_h, bar_w, gap, label_w = 64, 28, 10, 130
    height = row_h * len(trajectory) + 20
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
             f'aria-label="Trajectoire mémoire par élève">']

    for row_idx, (sid, points) in enumerate(sorted(trajectory.items())):
        points_sorted = sorted(points)
        max_count = max((m + s + f for _, m, s, f in points_sorted), default=1) or 1
        row_y = row_idx * row_h + 10
        parts.append(f'<text x="0" y="{row_y + row_h / 2:.1f}" class="axis-label" dominant-baseline="middle">{_esc(sid)}</text>')
        for i, (session_idx, mastered, shaky, forgotten) in enumerate(points_sorted):
            bx = label_w + i * (bar_w + gap)
            scale = (row_h - 20) / max_count
            by = row_y + row_h - 14
            for count, color in ((mastered, "var(--status-good)"), (shaky, "var(--status-warning)"), (forgotten, "var(--status-critical)")):
                seg_h = count * scale
                by -= seg_h
                if count:
                    parts.append(f'<rect x="{bx}" y="{by:.1f}" width="{bar_w}" height="{seg_h:.1f}" rx="2" fill="{color}">'
                                  f'<title>{_esc(sid)} — séance {session_idx} : {count}</title></rect>')
            parts.append(f'<text x="{bx + bar_w / 2:.1f}" y="{row_y + row_h - 2}" class="axis-label" text-anchor="middle">S{session_idx}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def _svg_architecture_diagram() -> str:
    # Row 1 (y=20): Planner -> Generator -> Élèves-agents -> DriftWatcher (side branch, same row)
    # Row 2 (y=180): Reviser <- Diagnostician <- (straight down from Élèves-agents)
    boxes = [
        ("Planner", 20, 20, "#2a78d6"),
        ("Generator", 220, 20, "#2a78d6"),
        ("Élèves-agents", 420, 20, "#2a78d6"),
        ("DriftWatcher", 640, 20, "#4a3aa7"),
        ("Reviser", 220, 180, "#2a78d6"),
        ("Diagnostician", 420, 180, "#2a78d6"),
    ]
    box_w, box_h = 160, 60
    parts = ['<svg viewBox="0 0 840 280" class="chart architecture" role="img" '
             'aria-label="Architecture agentique : boucle Planner, Generator, Élèves-agents, Diagnostician, Reviser, DriftWatcher">']
    parts.append(
        '<defs>'
        '<marker id="arrow-quality" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 Z" fill="#eb6834" /></marker>'
        '<marker id="arrow-plausibility" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 Z" fill="#4a3aa7" /></marker>'
        '<marker id="arrow-neutral" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 Z" fill="#898781" /></marker>'
        '</defs>'
    )
    coords = {}
    for label, bx, by, color in boxes:
        coords[label] = (bx, by, box_w, box_h)
        parts.append(f'<rect x="{bx}" y="{by}" width="{box_w}" height="{box_h}" rx="10" class="agent-box" style="border-color:{color}" />')
        parts.append(f'<text x="{bx + box_w / 2}" y="{by + box_h / 2 + 5}" class="agent-label" text-anchor="middle">{label}</text>')

    def hline(a, b, color, marker, dashed=False, label=None, label_dy=-10):
        ax, ay, aw, ah = coords[a]
        bx, by, bw, bh = coords[b]
        x1, y1 = ax + aw, ay + ah / 2
        x2, y2 = bx, by + bh / 2
        dash = ' stroke-dasharray="4 3"' if dashed else ""
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}"{dash} '
                      f'stroke-width="2" marker-end="url(#{marker})" />')
        if label:
            parts.append(f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 + label_dy}" class="edge-label" text-anchor="middle">{label}</text>')

    hline("Planner", "Generator", "#898781", "arrow-neutral")
    hline("Generator", "Élèves-agents", "#898781", "arrow-neutral")
    hline("Élèves-agents", "DriftWatcher", "#4a3aa7", "arrow-plausibility", label="valide / rejoue")

    # Élèves-agents -> Diagnostician: straight vertical line, x=420, no crossing
    ex, ey, ew, eh = coords["Élèves-agents"]
    dgx, dgy, dgw, dgh = coords["Diagnostician"]
    vx = ex + ew / 2
    parts.append(f'<line x1="{vx}" y1="{ey + eh}" x2="{vx}" y2="{dgy}" stroke="#eb6834" '
                  f'stroke-width="2" marker-end="url(#arrow-quality)" />')
    parts.append(f'<text x="{vx + 8}" y="{(ey + eh + dgy) / 2}" class="edge-label" fill="#eb6834">taux de réussite</text>')

    # Diagnostician -> Reviser: horizontal, row 2, right to left
    rx, ry, rw, rh = coords["Reviser"]
    parts.append(f'<line x1="{dgx}" y1="{dgy + dgh / 2}" x2="{rx + rw}" y2="{ry + rh / 2}" stroke="#eb6834" '
                  f'stroke-width="2" marker-end="url(#arrow-quality)" />')
    parts.append(f'<text x="{(dgx + rx + rw) / 2}" y="{ry + rh / 2 - 10}" class="edge-label" text-anchor="middle" fill="#eb6834">si révision nécessaire</text>')

    # Reviser -> Generator: dashed loop back up
    gx, gy, gw, gh = coords["Generator"]
    parts.append(f'<line x1="{rx + rw / 2}" y1="{ry}" x2="{gx + gw / 2}" y2="{gy + gh}" stroke="#eb6834" '
                  f'stroke-width="2" stroke-dasharray="4 3" marker-end="url(#arrow-quality)" />')

    legend_y = 264
    parts.append(f'<rect x="20" y="{legend_y}" width="14" height="14" fill="#eb6834" rx="2" />'
                  f'<text x="40" y="{legend_y + 11}" class="axis-label">Signal qualité (déclenche une révision)</text>')
    parts.append(f'<rect x="360" y="{legend_y}" width="14" height="14" fill="#4a3aa7" rx="2" />'
                  f'<text x="380" y="{legend_y + 11}" class="axis-label">Signal plausibilité (rejoue ou corrige, ne révise jamais)</text>')

    parts.append("</svg>")
    return "\n".join(parts)


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
        <div class="diff-card">
          <h3>Séance {i} — {_esc(session["spec"]["title"])}</h3>
          <p class="revision-note"><strong>Notes de révision appliquées :</strong> {_esc(notes)}</p>
          <div class="diff-columns">
            <div class="diff-col before"><h4>Avant</h4><p>{_esc(before)}</p></div>
            <div class="diff-col after"><h4>Après</h4><p>{_esc(after)}</p></div>
          </div>
        </div>""")
    if not cards:
        return '<p class="empty">Aucune séance n\'a nécessité de révision sur ce run.</p>'
    return "\n".join(cards)


def _render_drift_table(run_log: dict) -> str:
    counts = _collect_drift_rule_counts(run_log)
    flags = []
    for session in run_log["sessions"]:
        for it in session["iterations"]:
            flags.extend(it.get("run_drift_flags", []))

    rows = ""
    if counts:
        for (label, sid), n in sorted(counts.items()):
            rows += f"<tr><td>{_esc(label)}</td><td>{_esc(sid)}</td><td>{n}</td></tr>"
    else:
        rows = '<tr><td colspan="3" class="empty">Aucune correction déclenchée sur ce run.</td></tr>'

    flags_html = ""
    if flags:
        items = "".join(f"<li>{_esc(f)}</li>" for f in sorted(set(flags)))
        flags_html = f'<div class="callout warning"><strong>Anomalies de trajectoire signalées :</strong><ul>{items}</ul></div>'

    return f"""
    <table class="drift-table">
      <thead><tr><th>Règle déclenchée</th><th>Élève</th><th>Occurrences</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
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
<title>La Classe Fantôme — Rapport de run {_esc(run_log["run_id"])}</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb; --page: #f9f9f7;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
    --gridline: #e1e0d9; --border: rgba(11,11,11,0.10);
    --status-good: #0ca30c; --status-warning: #fab219; --status-critical: #d03b3b;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --gridline: #2c2c2a; --border: rgba(255,255,255,0.10);
      --status-good: #0ca30c; --status-warning: #fab219; --status-critical: #e66767;
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --gridline: #2c2c2a; --border: rgba(255,255,255,0.10);
    --status-good: #0ca30c; --status-warning: #fab219; --status-critical: #e66767;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--page); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--text-primary); }}
  .viz-root {{ max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; }}
  h1 {{ font-size: 28px; margin-bottom: 4px; }}
  .subtitle {{ color: var(--text-secondary); margin-top: 0; }}
  .meta {{ color: var(--text-muted); font-size: 13px; margin-bottom: 32px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 40px; flex-wrap: wrap; }}
  .stat-tile {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; flex: 1; min-width: 140px; }}
  .stat-tile .label {{ color: var(--text-secondary); font-size: 13px; }}
  .stat-tile .value {{ font-size: 32px; font-weight: 600; margin-top: 4px; }}
  section {{ margin-bottom: 48px; }}
  h2 {{ font-size: 20px; border-bottom: 1px solid var(--gridline); padding-bottom: 8px; }}
  .chart {{ width: 100%; height: auto; background: var(--surface-1); border-radius: 12px; border: 1px solid var(--border); }}
  .chart-card {{ background: var(--surface-1); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; }}
  .chart-card .chart--attached {{ border: none; border-radius: 0; display: block; }}
  .gridline {{ stroke: var(--gridline); stroke-width: 1; }}
  .axis-label {{ fill: var(--text-muted); font-size: 11px; }}
  .direct-label {{ fill: var(--text-secondary); font-size: 12px; font-weight: 600; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 16px; padding: 10px 12px 4px; font-size: 13px; color: var(--text-secondary); }}
  .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .line {{ stroke-width: 2; }}
  .agent-box {{ fill: var(--surface-1); stroke-width: 2; }}
  .agent-label {{ fill: var(--text-primary); font-size: 13px; font-weight: 600; }}
  .edge-label {{ font-size: 11px; }}
  .diff-card {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }}
  .diff-columns {{ display: flex; gap: 16px; }}
  .diff-col {{ flex: 1; padding: 12px; border-radius: 8px; }}
  .diff-col.before {{ background: rgba(211,59,59,0.06); }}
  .diff-col.after {{ background: rgba(12,163,12,0.06); }}
  .diff-col h4 {{ margin: 0 0 8px; color: var(--text-secondary); font-size: 12px; text-transform: uppercase; }}
  .revision-note {{ color: var(--text-secondary); font-size: 14px; }}
  table.drift-table {{ width: 100%; border-collapse: collapse; background: var(--surface-1); border-radius: 12px; overflow: hidden; }}
  table.drift-table th, table.drift-table td {{ text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--gridline); font-size: 14px; }}
  table.drift-table th {{ color: var(--text-secondary); font-weight: 600; }}
  .empty {{ color: var(--text-muted); font-style: italic; }}
  .callout {{ margin-top: 16px; padding: 12px 16px; border-radius: 8px; }}
  .callout.warning {{ background: rgba(250,178,25,0.12); border: 1px solid var(--status-warning); }}
  .callout.warning ul {{ margin: 8px 0 0; padding-left: 20px; }}
  footer {{ color: var(--text-muted); font-size: 13px; border-top: 1px solid var(--gridline); padding-top: 16px; }}
</style>
</head>
<body>
<div class="viz-root">

  <h1>La Classe Fantôme</h1>
  <p class="subtitle">La Classe Fantôme ne teste pas un contenu, elle teste sa demi-vie.</p>
  <p class="meta">Run <code>{_esc(run_log["run_id"])}</code> — objectif : {_esc(run_log["objective"])}</p>

  <div class="stats">
    <div class="stat-tile"><div class="label">Séances simulées</div><div class="value">{n_sessions}</div></div>
    <div class="stat-tile"><div class="label">Cycles de révision (contenu)</div><div class="value">{n_revisions}</div></div>
    <div class="stat-tile"><div class="label">Corrections DriftWatcher (plausibilité)</div><div class="value">{n_corrections}</div></div>
    <div class="stat-tile"><div class="label">Concepts suivis</div><div class="value">{len(success_series)}</div></div>
  </div>

  <section>
    <h2>Architecture agentique</h2>
    <p>Deux canaux de signal jamais confondus : le Diagnostician déclenche une révision de <strong>contenu</strong> ;
       le DriftWatcher ne modifie jamais le contenu, il valide la plausibilité d'une <strong>réaction d'élève</strong>.</p>
    {_svg_architecture_diagram()}
  </section>

  <section>
    <h2>Courbe de rétention par concept</h2>
    <p>Taux de réussite mesuré à chaque séance où le concept est retesté — la preuve empirique de ce que la classe retient dans le temps.</p>
    {_svg_retention_chart(success_series)}
  </section>

  <section>
    <h2>Trajectoire mémoire par élève</h2>
    <p>Nombre de concepts maîtrisés / fragiles / oubliés, séance par séance, pour chaque élève-agent.</p>
    {_svg_memory_trajectory(trajectory)}
  </section>

  <section>
    <h2>Contenu avant / après révision</h2>
    {_render_diff_cards(run_log)}
  </section>

  <section>
    <h2>DriftWatcher — règles déclenchées</h2>
    {_render_drift_table(run_log)}
  </section>

  <footer>
    Limites connues (élèves-agents non validés contre de vrais apprenants, biais d'auto-évaluation) :
    voir <code>docs/architecture.md</code>, section "Limites et protocole de validation".
  </footer>

</div>
</body>
</html>
"""


def save_html_report(run_log: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html_report(run_log))
