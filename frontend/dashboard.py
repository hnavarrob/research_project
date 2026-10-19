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
# Historial de sesiones
# ---------------------------------------------------------------------------
st.subheader("📋 Historial de Sesiones")

sessions = db.get_all_sessions()
if sessions:
    for session in sessions:
        status = "✅" if session["completada"] else "❌"
        with st.expander(
            f"{status} Sesión {session['id']} — {session['modalidad']} "
            f"({session['secciones_completadas']}/{session['total_secciones']} secciones)"
        ):
            st.markdown(f"**Objeto:** {session['objeto']}")
            st.markdown(f"**Presupuesto:** ${session['presupuesto']:,.0f} COP")
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

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "Dashboard de investigación para el proyecto de Fricción Epistémica en GovTech. "
    "Los datos se almacenan en `telemetry.db` (SQLite)."
)
