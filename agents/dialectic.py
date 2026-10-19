"""Grafo dialéctico con Comité Evaluador Multi-Agente.

Flujo:
    retrieval → committee[agente_actual] → [human_input] → evaluate
        ↓ aprobada                          ↑ rechazada (< 2 intentos)
     synthesis → END                        ↓ rechazada (≥ 2 intentos)
                                         tutor → [human_input] → evaluate
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from agents.nodes import (
    committee_node,
    evaluate_node,
    init_dependencies,
    retrieval_node,
    synthesis_node,
    tutor_node,
)
from agents.state import DialecticState

logger = logging.getLogger(__name__)

__all__ = [
    "build_dialectic_graph",
    "init_dependencies",
]


def _route_after_evaluation(state: DialecticState) -> str:
    """Decide el siguiente nodo después de la evaluación.

    - Aprobada → synthesis
    - Rechazada + ≥ 2 intentos → tutor
    - Rechazada + < 2 intentos → committee (otro agente)
    """
    if state.get("friccion_aprobada", False):
        return "synthesis"

    iteracion = state.get("iteracion_actual", 0)
    max_iter = state.get("max_iteraciones", 3)

    # Si ya se alcanzó el límite, forzar síntesis
    if iteracion >= max_iter:
        return "synthesis"

    # Si lleva 2+ rechazos y no se ha activado el tutor, activar
    if iteracion >= 2 and not state.get("tutor_activado", False):
        return "tutor"

    return "committee"


def _route_by_condition(state: DialecticState) -> str:
    """Enrutamiento de entrada según la condición experimental.

    - "A" (sin fricción)      → synthesis directo (sin comité, defensa ni tutor)
    - "B" (fricción, default) → retrieval → committee (flujo actual)
    """
    if state.get("condition") == "A":
        return "synthesis"
    return "retrieval"


def build_dialectic_graph() -> StateGraph:
    """Construye y compila el grafo dialéctico con comité evaluador."""
    graph = StateGraph(DialecticState)

    # Registrar nodos
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("committee", committee_node)
    graph.add_node("tutor", tutor_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("synthesis", synthesis_node)

    # Flujo: entrada condicional por condición experimental (A/B)
    graph.set_conditional_entry_point(
        _route_by_condition,
        {
            "synthesis": "synthesis",
            "retrieval": "retrieval",
        },
    )
    graph.add_edge("retrieval", "committee")

    # Después de committee y tutor, el control regresa al frontend
    # (human-in-the-loop). El frontend invoca "evaluate" con la defensa.

    graph.add_conditional_edges(
        "evaluate",
        _route_after_evaluation,
        {
            "synthesis": "synthesis",
            "committee": "committee",
            "tutor": "tutor",
        },
    )

    # Después del tutor, el control regresa al frontend nuevamente.
    # El frontend invoca "evaluate" con la nueva defensa.

    graph.add_edge("synthesis", END)

    return graph.compile()
