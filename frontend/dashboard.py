"""Dashboard de Telemetría Cognitiva — Panel de Investigación.

Ejecutar:
    streamlit run frontend/dashboard.py --server.port 8502

Muestra métricas de investigación:
  - Dwell Time por sección y agente
  - Volumen léxico (borrador vs defensa)
  - Tasa de rechazo por agente
  - Tasa de abandono
  - Historial de sesiones
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from telemetry.storage import TelemetryDB  # noqa: E402

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard de Telemetría Cognitiva",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 Dashboard de Telemetría Cognitiva")
st.markdown("*Panel de investigación — Métricas de fricción epistémica*")
st.markdown("---")


@st.cache_resource
def get_db():
    return TelemetryDB()


db = get_db()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.header("Filtros")
if st.sidebar.button("🔄 Refrescar datos"):
    st.cache_resource.clear()
    st.rerun()

# ---------------------------------------------------------------------------
# KPIs principales
# ---------------------------------------------------------------------------
abandonment = db.get_abandonment_rate()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Sesiones", abandonment["total"])
col2.metric("Completadas", abandonment["completadas"])
col3.metric("Abandonadas", abandonment["abandonadas"])
col4.metric("Tasa de Abandono", abandonment["tasa_abandono"])

st.markdown("---")

# ---------------------------------------------------------------------------
# Tasa de rechazo por agente
# ---------------------------------------------------------------------------
st.subheader("⚖️ Rendimiento por Agente del Comité")

agent_stats = db.get_agent_rejection_stats()
if agent_stats:
    agent_names = {"juridico": "⚖️ Jurídico", "financiero": "💰 Financiero",
                   "tecnico": "🔧 Técnico", "tutor": "📚 Tutor"}

    cols = st.columns(len(agent_stats))
    for i, stat in enumerate(agent_stats):
        agente = stat["agente"] or "desconocido"
        total = stat["total_evaluaciones"]
        rechazos = stat["rechazos"]
        aprobaciones = stat["aprobaciones"]
        tasa = rechazos / total * 100 if total > 0 else 0

        with cols[i]:
            name = agent_names.get(agente, agente)
            st.metric(name, f"{total} evaluaciones")
            st.caption(f"✅ {aprobaciones} aprobadas | ❌ {rechazos} rechazadas")
            st.progress(tasa / 100, text=f"Tasa rechazo: {tasa:.0f}%")
else:
    st.info("Sin datos de evaluación aún. Complete al menos una sesión.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Dwell Time (tiempo de reflexión)
# ---------------------------------------------------------------------------
st.subheader("⏱️ Dwell Time — Tiempo de Reflexión del Usuario")

dwell_data = db.get_dwell_times()
if dwell_data:
    # Agrupar por sección
    secciones_dwell: dict[str, list[float]] = {}
    for row in dwell_data:
        sec = row["seccion"]
        if sec not in secciones_dwell:
            secciones_dwell[sec] = []
        secciones_dwell[sec].append(row["valor_numerico"])

    for sec, times in secciones_dwell.items():
        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)

        with st.expander(f"📌 {sec} ({len(times)} mediciones)"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Promedio", f"{avg_time:.1f}s")
            c2.metric("Máximo", f"{max_time:.1f}s")
            c3.metric("Mínimo", f"{min_time:.1f}s")

            st.markdown("**Evolución por iteración:**")
            chart_data = {"Iteración": list(range(1, len(times) + 1)),
                         "Segundos": times}
            st.line_chart(chart_data, x="Iteración", y="Segundos")
else:
    st.info("Sin datos de dwell time aún.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Métricas léxicas
# ---------------------------------------------------------------------------
st.subheader("📝 Volumen y Profundidad Léxica")

word_data = db.get_word_counts()
if word_data:
    borradores = [r for r in word_data if r["tipo_evento"] == "palabras_borrador"]
    defensas = [r for r in word_data if r["tipo_evento"] == "palabras_defensa"]
    profundidades = [r for r in word_data if r["tipo_evento"] == "profundidad_lexica"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Palabras en borradores:**")
        if borradores:
            vals = [r["valor_numerico"] for r in borradores]
            st.metric("Promedio", f"{sum(vals)/len(vals):.0f} palabras")
        else:
            st.caption("Sin datos")

    with col2:
        st.markdown("**Palabras en defensas:**")
        if defensas:
            vals = [r["valor_numerico"] for r in defensas]
            st.metric("Promedio", f"{sum(vals)/len(vals):.0f} palabras")
        else:
            st.caption("Sin datos")

    if profundidades:
        st.markdown("**Profundidad léxica (palabras únicas / total):**")
        vals = [r["valor_numerico"] for r in profundidades]
        avg = sum(vals) / len(vals)
        st.metric("Promedio", f"{avg:.2%}")
        st.caption(
            "Un valor más alto indica vocabulario más diverso/técnico. "
            "Valores típicos: 0.50-0.70 para texto técnico."
        )
else:
    st.info("Sin datos léxicos aún.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Cuestionario NASA-TLX (6 subescalas + cruce A vs B)
# ---------------------------------------------------------------------------
st.subheader("🧠 Carga Cognitiva Autopercibida (NASA-TLX)")

tlx_stats = db.get_nasa_tlx_stats()
tlx_global = tlx_stats.get("global", {})
tlx_count = tlx_global.get("count") or 0

if tlx_count > 0:
    st.caption(f"Respuestas registradas: {tlx_count}")
    subscales = [
        ("mental", "Demanda Mental"),
        ("fisica", "Demanda Física"),
        ("temporal", "Demanda Temporal"),
        ("rendimiento", "Rendimiento"),
        ("esfuerzo", "Esfuerzo"),
        ("frustracion", "Frustración"),
    ]
    t_cols = st.columns(6)
    for idx, (key, label) in enumerate(subscales):
        val = tlx_global.get(key)
        t_cols[idx].metric(label, f"{val:.1f}" if val is not None else "0.0")

    by_cond = tlx_stats.get("by_condition", [])
    if by_cond:
        st.markdown("**Cruce por condición experimental (A vs B):**")
        cond_table = []
        for row in by_cond:
            cond_table.append({
                "Condición": row["condition"],
                "N": row["count"],
                "Mental": round(row["mental"] or 0.0, 1),
                "Física": round(row["fisica"] or 0.0, 1),
                "Temporal": round(row["temporal"] or 0.0, 1),
                "Rendimiento": round(row["rendimiento"] or 0.0, 1),
                "Esfuerzo": round(row["esfuerzo"] or 0.0, 1),
                "Frustración": round(row["frustracion"] or 0.0, 1),
            })
        st.dataframe(cond_table, use_container_width=True, hide_index=True)
else:
    st.info("Sin respuestas del cuestionario NASA-TLX aún.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Historial de sesiones
# ---------------------------------------------------------------------------
st.subheader("📋 Historial de Sesiones")

sessions = db.get_all_sessions()
if sessions:
    for session in sessions:
        status = "✅" if session["completada"] else "❌"
        cond_label = session.get("condition") or "-"
        with st.expander(
            f"{status} Sesión {session['id']} [Condición: {cond_label}] — {session['modalidad']} "
            f"({session['secciones_completadas']}/{session['total_secciones']} secciones)"
        ):
            st.markdown(f"**Objeto:** {session['objeto']}")
            st.markdown(f"**Presupuesto:** ${session['presupuesto']:,.0f} COP")
            st.markdown(f"**Condición:** {cond_label} | **NASA-TLX completado:** {'Sí' if session.get('tlx_completed') else 'No'}")
            st.markdown(f"**Inicio:** {session['inicio']}")
            st.markdown(f"**Fin:** {session['fin'] or 'En curso / Abandonada'}")

            # Eventos de esta sesión
            events = db.get_events_for_session(session["id"])
            if events:
                st.markdown(f"**{len(events)} eventos registrados:**")
                for ev in events:
                    icon = "⏱️" if "dwell" in ev["tipo_evento"] else "📝" if "palabras" in ev["tipo_evento"] else "🔍"
                    valor = ev["valor_numerico"] if ev["valor_numerico"] else ev["valor_texto"] or ""
                    st.caption(
                        f"{icon} [{ev['seccion']}] {ev['tipo_evento']}: {valor} "
                        f"(agente: {ev['agente'] or '-'})"
                    )
else:
    st.info("No hay sesiones registradas aún. Use la aplicación principal primero.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Exportación CSV
# ---------------------------------------------------------------------------
st.subheader("📥 Exportar Datos a CSV")

conn = db._get_conn()
export_cols = st.columns(3)

_csv_tables = [
    ("sessions", "Descargar sessions.csv", "sessions.csv"),
    ("events", "Descargar events.csv", "events.csv"),
    ("nasa_tlx", "Descargar nasa_tlx.csv", "nasa_tlx.csv"),
]

for col, (table_name, btn_label, filename) in zip(export_cols, _csv_tables):
    with col:
        df_table = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        if df_table.empty:
            st.warning(f"La tabla `{table_name}` está vacía.")
        else:
            csv_bytes = df_table.to_csv(index=False, sep=",", header=True).encode("utf-8")
            st.download_button(
                label=btn_label,
                data=csv_bytes,
                file_name=filename,
                mime="text/csv",
                key=f"dl_{table_name}",
            )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "Dashboard de investigación para el proyecto de Fricción Epistémica en GovTech. "
    "Los datos se almacenan en `telemetry.db` (SQLite)."
)
