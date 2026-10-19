"""Nodos del grafo dialéctico con Comité Evaluador Multi-Agente.

Nodos:
  - retrieval_node:     busca contexto en ChromaDB con filtro por dominio
  - committee_node:     agente del comité genera observación (jurídico/financiero/técnico)
  - tutor_node:         da pistas normativas cuando el usuario falla 2 veces
  - evaluate_node:      decide APROBADO/RECHAZADO
  - synthesis_node:     genera texto final de la sección
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, OllamaLLM

from config.prompts import (
    get_committee_juridico_prompt,
    get_committee_financiero_prompt,
    get_committee_tecnico_prompt,
    get_tutor_prompt,
    get_evaluation_prompt,
    get_synthesis_prompt,
)

if TYPE_CHECKING:
    from agents.state import DialecticState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependencias inyectadas
# ---------------------------------------------------------------------------
_llm: OllamaLLM | None = None
_db: Chroma | None = None
_retrievers: dict[str, object] = {}

# Mapeo agente → dominio de data
AGENT_DOMAIN_MAP = {
    "juridico": "juridico",
    "financiero": "financiero",
    "tecnico": "tecnico",
}

# Mapeo agente → función de prompt
AGENT_PROMPT_MAP = {
    "juridico": get_committee_juridico_prompt,
    "financiero": get_committee_financiero_prompt,
    "tecnico": get_committee_tecnico_prompt,
}

# Secuencia de agentes para round-robin
COMMITTEE_SEQUENCE = ["juridico", "financiero", "tecnico"]


def init_dependencies(llm: OllamaLLM, retriever, db: Chroma | None = None) -> None:
    """Inicializar LLM, retriever general y (opcionalmente) la DB para filtros.

    Si `db` se proporciona, se crean retrievers filtrados por dominio.
    Si no, se usa el retriever general para todos los agentes.
    """
    global _llm, _db, _retrievers  # noqa: PLW0603
    _llm = llm
    _db = db

    # Retriever general (sin filtro)
    _retrievers["general"] = retriever

    # Retrievers filtrados por dominio
    if db is not None:
        for agent_name, domain in AGENT_DOMAIN_MAP.items():
            try:
                _retrievers[agent_name] = db.as_retriever(
                    search_kwargs={"k": 5, "filter": {"dominio": domain}},
                )
                logger.info("Retriever filtrado creado para '%s' (dominio=%s).",
                           agent_name, domain)
            except Exception as e:
                logger.warning(
                    "No se pudo crear retriever filtrado para '%s': %s. "
                    "Usando retriever general.", agent_name, e,
                )
                _retrievers[agent_name] = retriever
    else:
        # Sin DB, todos usan el retriever general
        for agent_name in AGENT_DOMAIN_MAP:
            _retrievers[agent_name] = retriever


def _require_deps():
    if _llm is None:
        raise RuntimeError("Llamar init_dependencies() antes de ejecutar nodos.")
    return _llm


def _get_retriever(agent: str = "general"):
    """Obtiene el retriever para un agente. Fallback al general."""
    return _retrievers.get(agent, _retrievers.get("general"))


# ---------------------------------------------------------------------------
# Nodo 1: Retrieval
# ---------------------------------------------------------------------------
def retrieval_node(state: DialecticState) -> dict:
    """Recupera contexto normativo. Usa el retriever del agente actual si existe."""
    _require_deps()
    agente = state.get("agente_actual", "general")
    retriever = _get_retriever(agente)

    if retriever is None:
        return {"contexto_normativo": "", "fuentes": [],
                "errores": state.get("errores", []) + ["Sin retriever disponible"]}

    query = f"{state.get('borrador_usuario', '')} {state['config']['modalidad']} {state.get('seccion_nombre', '')}"

    try:
        docs = retriever.invoke(query)
        contexto = "\n\n".join(doc.page_content for doc in docs)
        fuentes = list({doc.metadata.get("source", "desconocido") for doc in docs})
        logger.info("Retrieval (%s): %d docs, %d fuentes.", agente, len(docs), len(fuentes))
        return {"contexto_normativo": contexto, "fuentes": fuentes}
    except Exception as e:
        logger.error("Error en retrieval (%s): %s", agente, e)
        return {"errores": state.get("errores", []) + [f"Retrieval falló: {e}"],
                "contexto_normativo": "", "fuentes": []}


# ---------------------------------------------------------------------------
# Nodo 2: Committee — agente del comité genera observación
# ---------------------------------------------------------------------------
def committee_node(state: DialecticState) -> dict:
    """El agente actual del comité genera una observación crítica."""
    llm = _require_deps()
    agente = state.get("agente_actual", "juridico")
    prompt_fn = AGENT_PROMPT_MAP.get(agente, get_committee_juridico_prompt)

    prompt = prompt_fn(
        seccion=state.get("seccion_nombre", "General"),
        modalidad=state["config"]["modalidad"],
        objeto=state["config"]["objeto"],
        borrador=state.get("borrador_usuario", ""),
        contexto_normativo=state.get("contexto_normativo", ""),
    )

    try:
        observacion = llm.invoke(prompt)
        observaciones = state.get("observaciones_auditor", []) + [observacion]
        historial = state.get("historial_agentes", []) + [agente]
        iteracion = state.get("iteracion_actual", 0) + 1
        logger.info("Committee [%s] iteración %d: observación generada.", agente, iteracion)
        return {
            "observaciones_auditor": observaciones,
            "historial_agentes": historial,
            "iteracion_actual": iteracion,
        }
    except Exception as e:
        logger.error("Error en committee [%s]: %s", agente, e)
        return {"errores": state.get("errores", []) + [f"Committee [{agente}] falló: {e}"]}


# ---------------------------------------------------------------------------
# Nodo 3: Tutor — pista normativa
# ---------------------------------------------------------------------------
def tutor_node(state: DialecticState) -> dict:
    """Da una pista normativa al usuario sin redactar la respuesta."""
    llm = _require_deps()
    observaciones = state.get("observaciones_auditor", [])
    defensas = state.get("defensas_usuario", [])

    prompt = get_tutor_prompt(
        seccion=state.get("seccion_nombre", "General"),
        objeto=state["config"]["objeto"],
        borrador=state.get("borrador_usuario", ""),
        observacion_previa=observaciones[-1] if observaciones else "",
        defensa_previa=defensas[-1] if defensas else "",
        contexto_normativo=state.get("contexto_normativo", ""),
    )

    try:
        pista = llm.invoke(prompt)
        # La pista se agrega como una observación especial del tutor
        observaciones_new = state.get("observaciones_auditor", []) + [f"📚 PISTA DEL TUTOR:\n{pista}"]
        historial = state.get("historial_agentes", []) + ["tutor"]
        iteracion = state.get("iteracion_actual", 0) + 1
        logger.info("Tutor activado en iteración %d.", iteracion)
        return {
            "observaciones_auditor": observaciones_new,
            "historial_agentes": historial,
            "iteracion_actual": iteracion,
            "tutor_activado": True,
        }
    except Exception as e:
        logger.error("Error en tutor: %s", e)
        return {"errores": state.get("errores", []) + [f"Tutor falló: {e}"]}


# ---------------------------------------------------------------------------
# Nodo 4: Evaluate
# ---------------------------------------------------------------------------
def evaluate_node(state: DialecticState) -> dict:
    """Evalúa si la defensa del usuario es técnicamente suficiente."""
    llm = _require_deps()
    defensas = state.get("defensas_usuario", [])
    iteracion = state.get("iteracion_actual", 0)
    max_iter = state.get("max_iteraciones", 3)

    if iteracion >= max_iter:
        logger.info("Límite de iteraciones (%d). Aprobación automática.", max_iter)
        return {"friccion_aprobada": True}

    if not defensas:
        return {"friccion_aprobada": False}

    observaciones = state.get("observaciones_auditor", [])
    if not observaciones:
        return {"friccion_aprobada": False}

    prompt = get_evaluation_prompt(
        observacion=observaciones[-1],
        defensa=defensas[-1],
        contexto_normativo=state.get("contexto_normativo", ""),
    )

    try:
        resultado = llm.invoke(prompt).strip().upper()
        aprobada = "APROBADO" in resultado
        logger.info("Evaluación iteración %d: %s",
                     iteracion, "APROBADA" if aprobada else "RECHAZADA")
        return {"friccion_aprobada": aprobada}
    except Exception as e:
        logger.error("Error en evaluate: %s", e)
        return {"friccion_aprobada": True,
                "errores": state.get("errores", []) + [f"Evaluate falló: {e}"]}


# ---------------------------------------------------------------------------
# Nodo 5: Synthesis
# ---------------------------------------------------------------------------
def synthesis_node(state: DialecticState) -> dict:
    """Genera el texto final consolidando todos los aportes del ciclo."""
    llm = _require_deps()
    defensas = state.get("defensas_usuario", [])
    defensa_consolidada = "\n".join(defensas) if defensas else ""

    prompt = get_synthesis_prompt(
        seccion=state.get("seccion_nombre", "General"),
        objeto=state["config"]["objeto"],
        borrador_usuario=state.get("borrador_usuario", ""),
        defensa_usuario=defensa_consolidada,
    )

    try:
        texto = llm.invoke(prompt)
        logger.info("Síntesis generada: %d caracteres.", len(texto))
        return {"texto_final": texto}
    except Exception as e:
        logger.error("Error en synthesis: %s", e)
        return {"texto_final": "Error al generar la síntesis. Intente nuevamente.",
                "errores": state.get("errores", []) + [f"Synthesis falló: {e}"]}


# ---------------------------------------------------------------------------
# Helpers para el frontend
# ---------------------------------------------------------------------------
def get_next_agent(iteracion: int, agentes_disponibles: list[str]) -> str:
    """Determina el siguiente agente del comité en round-robin."""
    if not agentes_disponibles:
        return "juridico"
    idx = iteracion % len(agentes_disponibles)
    return agentes_disponibles[idx]


def should_activate_tutor(iteracion: int, max_iteraciones: int) -> bool:
    """Determina si se debe activar el tutor (en la penúltima iteración tras rechazo)."""
    return iteracion >= 2 and iteracion < max_iteraciones
