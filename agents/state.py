"""Estado tipado compartido entre todos los nodos del grafo dialéctico.

Soporta:
  - Flujo multi-sección (seccion_actual, secciones_completadas)
  - Comité evaluador (agente_actual, historial_agentes)
  - Tutor (tutor_activado)
  - Telemetría (timestamp_friccion_inicio)
"""

from __future__ import annotations

from typing import TypedDict


class ContractConfig(TypedDict):
    """Parámetros base del contrato, inmutables durante el flujo."""

    modalidad: str
    objeto: str
    presupuesto: float


class DialecticState(TypedDict, total=False):
    """Estado del grafo LangGraph — cada nodo lee y escribe campos."""

    # Configuración
    config: ContractConfig

    # Condición experimental: "A" = sin fricción, "B" = fricción estructurada
    condition: str

    # Sección actual
    seccion_actual: str            # ID de la sección (ej: "justificacion")
    seccion_nombre: str            # Nombre legible (ej: "Justificación de la Necesidad")

    # Fase Ideación
    borrador_usuario: str

    # Fase RAG
    contexto_normativo: str
    fuentes: list[str]

    # Fase Fricción — Comité Evaluador
    agente_actual: str             # "juridico", "financiero", "tecnico", "tutor"
    historial_agentes: list[str]   # Secuencia de agentes que han evaluado
    observaciones_auditor: list[str]
    defensas_usuario: list[str]
    iteracion_actual: int
    max_iteraciones: int
    friccion_aprobada: bool
    tutor_activado: bool

    # Fase Síntesis
    texto_final: str

    # Multi-sección
    secciones_completadas: dict[str, str]  # {seccion_id: texto_final}

    # Telemetría
    timestamp_friccion_inicio: str  # ISO timestamp para medir dwell time

    # Meta
    errores: list[str]
