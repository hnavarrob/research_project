"""Plataforma de Contratación Estatal — Interfaz Streamlit Multi-Sección.

Flujo multi-sección con comité evaluador, tutor y telemetría cognitiva.
"""

from __future__ import annotations

import html
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402
from langchain_chroma import Chroma  # noqa: E402
from langchain_ollama import OllamaEmbeddings, OllamaLLM  # noqa: E402

from agents.dialectic import _route_by_condition  # noqa: E402
from agents.mental_state import EstadoMental  # noqa: E402
from agents.nodes import (  # noqa: E402
    COMMITTEE_SEQUENCE,
    committee_node,
    evaluate_node,
    get_next_agent,
    init_dependencies,
    retrieval_node,
    should_activate_tutor,
    synthesis_node,
    tutor_node,
)
from config.sections import SECCIONES, get_secciones_con_friccion  # noqa: E402
from telemetry.tracker import TelemetryTracker  # noqa: E402
from telemetry.storage import TelemetryDB  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -- Iconos de agentes --
AGENT_ICONS = {
    "juridico": "⚖️",
    "financiero": "💰",
    "tecnico": "🔧",
    "tutor": "📚",
}
AGENT_NAMES = {
    "juridico": "Auditor Jurídico",
    "financiero": "Auditor Financiero",
    "tecnico": "Auditor Técnico",
    "tutor": "Tutor Normativo",
}

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Plataforma de Contratación Estatal",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    .success-box {
        padding: 1rem; border-radius: 8px;
        background-color: #1e3a2f; border: 1px solid #2e5a4f;
        margin-top: 1rem; white-space: pre-wrap;
    }
    .agent-badge {
        display: inline-block; padding: 0.3rem 0.8rem; border-radius: 16px;
        font-weight: 600; margin-bottom: 0.5rem;
    }
    .agent-juridico { background-color: #2d3748; border: 1px solid #4a5568; }
    .agent-financiero { background-color: #2d3748; border: 1px solid #d69e2e; }
    .agent-tecnico { background-color: #2d3748; border: 1px solid #38a169; }
    .agent-tutor { background-color: #2d3748; border: 1px solid #805ad5; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sistema (cacheado)
# ---------------------------------------------------------------------------
CHROMA_PATH = PROJECT_ROOT / "chroma_db"


@st.cache_resource
def load_system():
    try:
        llm = OllamaLLM(model="llama3", timeout=120)
        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        db = Chroma(persist_directory=str(CHROMA_PATH), embedding_function=embeddings)
        retriever = db.as_retriever(search_kwargs={"k": 5})
        init_dependencies(llm, retriever, db=db)
        return llm, retriever, db
    except Exception as e:
        st.error(f"❌ Error al conectar con Ollama: {e}")
        st.stop()


llm, retriever, db = load_system()

# ---------------------------------------------------------------------------
# Telemetría
# ---------------------------------------------------------------------------
@st.cache_resource
def get_telemetry():
    telemetry_db = TelemetryDB()
    return TelemetryTracker(db=telemetry_db)

tracker = get_telemetry()

# ---------------------------------------------------------------------------
# Estado de sesión
# ---------------------------------------------------------------------------
SECCIONES_FRICCION = get_secciones_con_friccion()


def _init_session():
    defaults = {
        "condition": None,
        "step": "setup",
        "seccion_index": 0,
        "borrador_usuario": "",
        "pregunta_adversario": "",
        "texto_final": "",
        "defensas": [],
        "observaciones": [],
        "contexto_normativo": "",
        "fuentes": [],
        "iteracion": 0,
        "max_iteraciones": 3,
        "agente_actual": "juridico",
        "tutor_activado": False,
        "estado_mental": EstadoMental(),
        "secciones_completadas": {},
        "telemetry_session_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_session()


def _get_current_section():
    idx = st.session_state.seccion_index
    if idx < len(SECCIONES_FRICCION):
        return SECCIONES_FRICCION[idx]
    return None


def _reset_section_state():
    """Resetea el estado para una nueva sección (mantiene datos globales)."""
    st.session_state.borrador_usuario = ""
    st.session_state.pregunta_adversario = ""
    st.session_state.texto_final = ""
    st.session_state.defensas = []
    st.session_state.observaciones = []
    st.session_state.contexto_normativo = ""
    st.session_state.fuentes = []
    st.session_state.iteracion = 0
    st.session_state.agente_actual = "juridico"
    st.session_state.tutor_activado = False
    st.session_state.step = "ideacion"


def _build_graph_state():
    seccion = _get_current_section()
    return {
        "config": {
            "modalidad": st.session_state.get("modalidad", ""),
            "objeto": st.session_state.get("objeto", ""),
            "presupuesto": st.session_state.get("presupuesto", 0.0),
        },
        "condition": st.session_state.get("condition") or "B",
        "seccion_actual": seccion.id if seccion else "",
        "seccion_nombre": seccion.nombre if seccion else "",
        "borrador_usuario": st.session_state.borrador_usuario,
        "contexto_normativo": st.session_state.contexto_normativo,
        "fuentes": st.session_state.fuentes,
        "agente_actual": st.session_state.agente_actual,
        "observaciones_auditor": st.session_state.observaciones,
        "defensas_usuario": st.session_state.defensas,
        "iteracion_actual": st.session_state.iteracion,
        "max_iteraciones": st.session_state.max_iteraciones,
        "tutor_activado": st.session_state.tutor_activado,
    }


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("Plataforma de Contratación Estatal")
st.markdown("#### Estructuración y Validación Técnica Contractual")
st.markdown("---")

# Selector de condición experimental al inicio, antes de cualquier interacción
_cond_options = ["A — sin fricción", "B — con fricción"]
_current_cond = st.session_state.get("condition")
_cond_index = (
    0 if _current_cond == "A"
    else 1 if _current_cond == "B"
    else None
)
_cond_selected = st.radio(
    "Condición experimental",
    _cond_options,
    index=_cond_index,
    disabled=(st.session_state.step != "setup"),
)
if st.session_state.step == "setup":
    if _cond_selected is not None:
        st.session_state["condition"] = "A" if _cond_selected.startswith("A") else "B"
    else:
        st.session_state["condition"] = None

if st.session_state.get("condition") not in ("A", "B"):
    st.warning("Seleccione una condición experimental (A o B) para continuar.")
    st.stop()

# ==========================================
# PANTALLA 1: SETUP
# ==========================================
if st.session_state.step == "setup":
    st.info("""
    **Bienvenido a la plataforma de Estructuración Asistida.**

    El sistema le guiará a través de **4 secciones** de su documento de Estudios Previos.
    En cada sección, un **comité de 3 auditores especializados** (Jurídico, Financiero y Técnico)
    cuestionará su propuesta para elevar el rigor técnico y normativo.

    1. **Ideación:** Usted ingresa las ideas base.
    2. **Auditoría (Comité):** Los auditores cuestionan desde diferentes perspectivas.
    3. **Síntesis:** El sistema consolida sus aportes en redacción formal.
    """)

    with st.form("contract_setup_form"):
        modalidad = st.selectbox(
            "Modalidad de Selección Normativa",
            ["Licitación Pública", "Contratación Directa"],
        )
        objeto = st.text_area(
            "Objeto del Contrato",
            placeholder="Ej: ADQUISICIÓN Y PUESTA EN FUNCIONAMIENTO DE UN ERP...",
        )
        presupuesto = st.number_input(
            "Presupuesto Oficial Estimado (COP)",
            min_value=0.0, step=1_000_000.0, format="%f",
        )

        if st.form_submit_button("Iniciar Estructuración"):
            if st.session_state.get("condition") not in ("A", "B"):
                st.error("Debe seleccionar la condición experimental antes de avanzar.")
            elif not objeto.strip():
                st.error("El objeto del contrato es obligatorio.")
            else:
                st.session_state.modalidad = modalidad
                st.session_state.objeto = objeto
                st.session_state.presupuesto = presupuesto
                st.session_state.step = "ideacion"
                st.session_state.seccion_index = 0

                # Iniciar telemetría
                sid = tracker.start_session(
                    modalidad=modalidad, objeto=objeto,
                    presupuesto=presupuesto,
                    total_secciones=len(SECCIONES_FRICCION),
                    condition=st.session_state["condition"],
                )
                st.session_state.telemetry_session_id = sid

                # Iniciar estado mental para la primera sección
                seccion = SECCIONES_FRICCION[0]
                st.session_state.estado_mental.iniciar_seccion(seccion.id)
                st.session_state.agente_actual = seccion.agentes_friccion[0] if seccion.agentes_friccion else "juridico"

                st.rerun()

# ==========================================
# PANTALLAS POST-SETUP
# ==========================================
else:
    seccion_actual = _get_current_section()

    # --- Sidebar: progreso y parámetros ---
    with st.expander("Ver Parámetros y Progreso", expanded=False):
        st.markdown(
            f"**Condición:** {st.session_state.condition} | "
            f"**Modalidad:** {st.session_state.modalidad} | "
            f"**Presupuesto:** \\${st.session_state.presupuesto:,.0f} COP"
        )
        st.markdown(f"**Objeto:** {st.session_state.objeto}")

        # Progreso de secciones
        total_sec = len(SECCIONES_FRICCION)
        completadas = len(st.session_state.secciones_completadas)
        st.progress(completadas / total_sec,
                     text=f"Secciones: {completadas}/{total_sec}")

        # Estado mental
        resumen = st.session_state.estado_mental.resumen()
        st.markdown(
            f"**Confianza:** {resumen['confianza']} | "
            f"**Iteraciones totales:** {resumen['iteraciones']} | "
            f"**Tasa aprobación:** {resumen['tasa_aprobacion']}"
        )

        if st.button("Reiniciar Proyecto", key="reset_btn"):
            if st.session_state.telemetry_session_id:
                tracker.end_session(completada=False,
                                    secciones_completadas=completadas)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- Verificar si hay sección actual ---
    if seccion_actual is None:
        # Todas las secciones completadas → pantalla final
        st.session_state.step = "resumen_final"

    # --- Header de sección ---
    if st.session_state.step != "resumen_final":
        idx = st.session_state.seccion_index
        st.markdown(f"### Sección {idx + 1} de {len(SECCIONES_FRICCION)}: {seccion_actual.nombre}")
        st.caption(seccion_actual.descripcion)

    # ==========================================
    # FASE 1: IDEACIÓN
    # ==========================================
    if st.session_state.step == "ideacion":
        st.markdown(seccion_actual.instruccion_usuario)
        borrador = st.text_area("Su idea base:", height=150, key="borrador_input")

        if st.button("Someter al Comité Evaluador"):
            if not borrador.strip():
                st.warning("Debe ingresar una idea base para continuar.")
            else:
                st.session_state.borrador_usuario = borrador

                # Telemetría: métricas del borrador
                tracker.record_text_metrics(
                    seccion=seccion_actual.id, fase="borrador", texto=borrador)

                state = _build_graph_state()
                state["borrador_usuario"] = borrador
                next_entry = _route_by_condition(state)

                if next_entry == "synthesis":
                    # Condición A (Cero fricción): borrador → synthesis_node directo
                    with st.spinner("Sintetizando documento formal..."):
                        try:
                            synth_result = synthesis_node(state)
                            st.session_state.texto_final = synth_result["texto_final"]
                            st.session_state.estado_mental.finalizar(seccion_actual.id)
                            tracker.record_section_complete(seccion_actual.id)
                            st.session_state.step = "sintesis"
                        except Exception as e:
                            logger.error("Error en síntesis directa (Condición A): %s", e)
                            st.error(f"Error: {e}. Verifique que Ollama esté corriendo.")
                            st.session_state.step = "ideacion"
                else:
                    # Condición B (Fricción estructurada): flujo actual completo
                    st.session_state.step = "friccion"
                    with st.spinner("El comité está analizando su propuesta..."):
                        try:
                            # Retrieval
                            state.update(retrieval_node(state))

                            # Committee (primer agente)
                            state.update(committee_node(state))

                            st.session_state.pregunta_adversario = state["observaciones_auditor"][-1]
                            st.session_state.observaciones = state["observaciones_auditor"]
                            st.session_state.contexto_normativo = state.get("contexto_normativo", "")
                            st.session_state.fuentes = state.get("fuentes", [])

                            # Telemetría: iniciar timer de reflexión
                            tracker.start_friction_timer()

                        except Exception as e:
                            logger.error("Error en auditoría: %s", e)
                            st.error(f"Error: {e}. Verifique que Ollama esté corriendo.")
                            st.session_state.step = "ideacion"

                st.rerun()

    # ==========================================
    # FASE 2: FRICCIÓN — Comité Evaluador
    # ==========================================
    elif st.session_state.step == "friccion":
        iteracion = st.session_state.iteracion + 1
        max_iter = st.session_state.max_iteraciones
        st.progress(iteracion / max_iter, text=f"Iteración {iteracion} de {max_iter}")

        # Fuentes consultadas
        if st.session_state.fuentes:
            with st.expander("📚 Fuentes normativas consultadas"):
                for fuente in st.session_state.fuentes:
                    st.markdown(f"- {Path(fuente).name}")

        # Badge del agente
        agente = st.session_state.agente_actual
        icon = AGENT_ICONS.get(agente, "🏛️")
        name = AGENT_NAMES.get(agente, agente.title())
        st.markdown(
            f'<span class="agent-badge agent-{agente}">{icon} {name}</span>',
            unsafe_allow_html=True,
        )

        # Observación
        st.markdown(f"**Observación del {name}:**")
        st.info(st.session_state.pregunta_adversario)

        # Defensa
        defensa = st.text_area(
            "Escriba su justificación o respuesta a la observación:",
            height=150, key="defensa_input",
        )

        if st.button("Enviar Respuesta al Comité"):
            if not defensa.strip():
                st.warning("Debe responder a la observación.")
            else:
                st.session_state.defensas.append(defensa)
                st.session_state.iteracion += 1

                # Telemetría
                dwell = tracker.record_dwell_time(
                    seccion=seccion_actual.id, agente=agente)
                tracker.record_text_metrics(
                    seccion=seccion_actual.id, fase="defensa",
                    texto=defensa, agente=agente)

                with st.spinner("El comité está evaluando su respuesta..."):
                    try:
                        state = _build_graph_state()
                        eval_result = evaluate_node(state)
                        aprobada = eval_result.get("friccion_aprobada", False)

                        # Estado mental + telemetría
                        estado_mental = st.session_state.estado_mental
                        estado_mental.registrar_iteracion(
                            aprobada=aprobada, agente=agente,
                            observacion=st.session_state.pregunta_adversario,
                            seccion=seccion_actual.id,
                        )
                        tracker.record_evaluation(
                            seccion=seccion_actual.id, agente=agente,
                            aprobada=aprobada)

                        if aprobada:
                            # → Síntesis
                            estado_mental.finalizar(seccion_actual.id)
                            st.session_state.step = "sintesis"

                            with st.spinner("Sintetizando documento formal..."):
                                synth_result = synthesis_node(state)
                                st.session_state.texto_final = synth_result["texto_final"]

                            tracker.record_section_complete(seccion_actual.id)
                        else:
                            # ¿Activar tutor?
                            iter_actual = st.session_state.iteracion
                            if should_activate_tutor(iter_actual, max_iter) and not st.session_state.tutor_activado:
                                # Tutor
                                tutor_result = tutor_node(state)
                                st.session_state.pregunta_adversario = tutor_result["observaciones_auditor"][-1]
                                st.session_state.observaciones = tutor_result["observaciones_auditor"]
                                st.session_state.agente_actual = "tutor"
                                st.session_state.tutor_activado = True
                                estado_mental.registrar_tutor(seccion_actual.id)
                                tracker.record_tutor_activated(seccion_actual.id)
                            else:
                                # Siguiente agente del comité
                                agentes_seccion = seccion_actual.agentes_friccion
                                next_agent = get_next_agent(iter_actual, agentes_seccion)
                                st.session_state.agente_actual = next_agent
                                state["agente_actual"] = next_agent

                                # Retrieval con filtro del nuevo agente
                                state.update(retrieval_node(state))
                                st.session_state.contexto_normativo = state.get("contexto_normativo", "")

                                adv_result = committee_node(state)
                                st.session_state.pregunta_adversario = adv_result["observaciones_auditor"][-1]
                                st.session_state.observaciones = adv_result["observaciones_auditor"]

                            # Reiniciar timer
                            tracker.start_friction_timer()

                    except Exception as e:
                        logger.error("Error en consolidación: %s", e)
                        st.error(f"Error al procesar: {e}")

                st.rerun()

    # ==========================================
    # FASE 3: SÍNTESIS de la sección actual
    # ==========================================
    elif st.session_state.step == "sintesis":
        st.success(f"✅ Sección «{seccion_actual.nombre}» aprobada por el comité.")

        # Métricas
        resumen = st.session_state.estado_mental.resumen()
        cols = st.columns(3)
        cols[0].metric("Confianza", resumen["confianza"].upper())
        cols[1].metric("Iteraciones", resumen["iteraciones"])
        cols[2].metric("Tasa Aprobación", resumen["tasa_aprobacion"])

        # Texto final
        texto_escapado = html.escape(st.session_state.texto_final)
        st.markdown(
            f'<div class="success-box">{texto_escapado}</div>',
            unsafe_allow_html=True,
        )

        # Guardar sección completada
        st.session_state.secciones_completadas[seccion_actual.id] = st.session_state.texto_final

        # Botones
        col1, col2 = st.columns(2)

        has_next = st.session_state.seccion_index < len(SECCIONES_FRICCION) - 1

        with col1:
            st.download_button(
                label=f"📥 Descargar «{seccion_actual.nombre}»",
                data=st.session_state.texto_final,
                file_name=f"{seccion_actual.id}.txt",
                mime="text/plain",
            )

        with col2:
            if has_next:
                if st.button("✅ Aprobar y continuar a la siguiente sección"):
                    st.session_state.seccion_index += 1
                    next_sec = SECCIONES_FRICCION[st.session_state.seccion_index]
                    st.session_state.estado_mental.iniciar_seccion(next_sec.id)
                    st.session_state.agente_actual = (
                        next_sec.agentes_friccion[0]
                        if next_sec.agentes_friccion else "juridico"
                    )
                    _reset_section_state()
                    st.rerun()
            else:
                if st.button("🏁 Finalizar — Ver documento completo"):
                    st.session_state.step = "resumen_final"
                    if st.session_state.telemetry_session_id:
                        tracker.end_session(
                            completada=True,
                            secciones_completadas=len(st.session_state.secciones_completadas),
                        )
                    st.rerun()

    # ==========================================
    # PANTALLA FINAL: Resumen y descarga
    # ==========================================
    elif st.session_state.step == "resumen_final":
        st.balloons()
        st.success("🏁 ¡Documento de Estudios Previos completado!")

        # Métricas finales
        resumen = st.session_state.estado_mental.resumen()
        cols = st.columns(4)
        cols[0].metric("Secciones", f"{resumen['secciones_completadas']}/{len(SECCIONES_FRICCION)}")
        cols[1].metric("Confianza", resumen["confianza"].upper())
        cols[2].metric("Iteraciones", resumen["iteraciones"])
        cols[3].metric("Tasa Aprobación", resumen["tasa_aprobacion"])

        # Métricas por agente
        resumen_agentes = st.session_state.estado_mental.resumen_agentes()
        if resumen_agentes:
            with st.expander("📊 Rendimiento por Agente del Comité"):
                for agente, metricas in resumen_agentes.items():
                    icon = AGENT_ICONS.get(agente, "🏛️")
                    st.markdown(
                        f"**{icon} {AGENT_NAMES.get(agente, agente)}:** "
                        f"{metricas['evaluaciones']} evaluaciones, "
                        f"{metricas['rechazos']} rechazos "
                        f"(tasa rechazo: {metricas['tasa_rechazo']})"
                    )

        st.markdown("---")

        # Documento consolidado
        documento_completo = ""
        for seccion in SECCIONES_FRICCION:
            texto = st.session_state.secciones_completadas.get(seccion.id, "")
            if texto:
                documento_completo += f"\n{'='*60}\n"
                documento_completo += f"{seccion.nombre.upper()}\n"
                documento_completo += f"{'='*60}\n\n"
                documento_completo += texto + "\n\n"

        if documento_completo:
            st.markdown("### Documento Consolidado")
            texto_escapado = html.escape(documento_completo)
            st.markdown(
                f'<div class="success-box">{texto_escapado}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("### 🧠 Cuestionario de Carga Cognitiva (NASA-TLX)")
        st.caption(
            "Antes de descargar su documento, evalúe su experiencia de 0 a 100 en las siguientes dimensiones (opcional):"
        )

        tlx_mental = st.slider(
            "Demanda mental — ¿Cuánta actividad mental y perceptiva te exigió esta tarea (pensar, decidir, calcular, recordar, buscar)?",
            min_value=0, max_value=100, value=50, key="tlx_mental",
        )
        tlx_fisica = st.slider(
            "Demanda física — ¿Cuánta actividad física fue necesaria (escribir, teclear, mover el mouse)?",
            min_value=0, max_value=100, value=50, key="tlx_fisica",
        )
        tlx_temporal = st.slider(
            "Demanda temporal — ¿Qué tanta prisa sentiste? ¿El ritmo fue lento o rápido y agobiante?",
            min_value=0, max_value=100, value=50, key="tlx_temporal",
        )
        tlx_rendimiento = st.slider(
            "Rendimiento — ¿Qué tan exitoso crees que fuiste? ¿Estás satisfecho con tu desempeño?",
            min_value=0, max_value=100, value=50, key="tlx_rendimiento",
        )
        tlx_esfuerzo = st.slider(
            "Esfuerzo — ¿Cuánto tuviste que esforzarte (mental y físicamente) para lograr tu nivel de rendimiento?",
            min_value=0, max_value=100, value=50, key="tlx_esfuerzo",
        )
        tlx_frustracion = st.slider(
            "Frustración — ¿Qué tan inseguro, desanimado, irritado, estresado o molesto te sentiste?",
            min_value=0, max_value=100, value=50, key="tlx_frustracion",
        )

        if st.button("Enviar respuestas"):
            sid = st.session_state.get("telemetry_session_id")
            ok = tracker.record_nasa_tlx(
                mental=tlx_mental,
                fisica=tlx_fisica,
                temporal=tlx_temporal,
                rendimiento=tlx_rendimiento,
                esfuerzo=tlx_esfuerzo,
                frustracion=tlx_frustracion,
                session_id=sid,
            )
            if ok:
                st.session_state["tlx_submitted"] = True
                st.success("✅ Respuestas NASA-TLX registradas correctamente.")
            else:
                st.warning("No se encontró una sesión activa para asociar las respuestas.")

        if documento_completo:
            st.download_button(
                label="📥 Descargar Documento Completo (.md)",
                data=documento_completo,
                file_name="estudios_previos_completo.md",
                mime="text/markdown",
            )

        st.markdown("---")
        st.info(
            "📊 Para ver las métricas de telemetría cognitiva de esta y otras sesiones, "
            "ejecute: `streamlit run frontend/dashboard.py --server.port 8502`"
        )