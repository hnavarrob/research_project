"""Definición de las secciones contractuales para el flujo multi-sección.

Cada sección define qué tipo de input requiere, qué agentes del comité
participan en la fricción, y cómo se muestra en la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeccionContractual:
    """Definición de una sección del documento de Estudios Previos."""

    id: str
    nombre: str
    descripcion: str
    instruccion_usuario: str
    agentes_friccion: list[str] = field(default_factory=lambda: ["juridico", "financiero", "tecnico"])
    requiere_friccion: bool = True


# Las 5 secciones del prototipo (UNSPSC omitida)
SECCIONES: list[SeccionContractual] = [
    SeccionContractual(
        id="justificacion",
        nombre="Justificación de la Necesidad",
        descripcion="Justificación de la necesidad y descripción de la entidad contratante.",
        instruccion_usuario=(
            "Describa brevemente la necesidad que motiva esta contratación. "
            "¿Por qué la entidad requiere este bien o servicio? "
            "¿Qué problema se resuelve o qué objetivo estratégico se cumple?"
        ),
    ),
    SeccionContractual(
        id="objeto_especificaciones",
        nombre="Objeto y Especificaciones Técnicas",
        descripcion="Descripción del objeto contractual y sus especificaciones técnicas detalladas.",
        instruccion_usuario=(
            "Defina el objeto del contrato y las especificaciones técnicas "
            "del bien o servicio a adquirir. Incluya cantidades, características, "
            "estándares de calidad y requisitos funcionales."
        ),
    ),
    SeccionContractual(
        id="valor_presupuesto",
        nombre="Valor Estimado y Apropiación Presupuestal",
        descripcion="Valor total estimado, vigencia, apropiación presupuestal (CDP, rubro).",
        instruccion_usuario=(
            "Indique el valor estimado del contrato, cómo se determinó (estudio de mercado, "
            "históricos, cotizaciones), la vigencia del acuerdo, y los datos de la "
            "apropiación presupuestal (CDP, rubro, descripción, valor)."
        ),
        agentes_friccion=["financiero", "juridico"],
    ),
    SeccionContractual(
        id="forma_pago_ejecucion",
        nombre="Forma de Pago, Plazo y Lugar de Ejecución",
        descripcion="Condiciones de pago, plazo de ejecución y lugar donde se desarrollará el contrato.",
        instruccion_usuario=(
            "Describa la forma de pago propuesta (anticipos, pagos parciales, pago único), "
            "el plazo de ejecución del contrato y el lugar donde se ejecutará."
        ),
        agentes_friccion=["financiero", "juridico", "tecnico"],
    ),
    SeccionContractual(
        id="resumen_final",
        nombre="Resumen y Descarga del Documento",
        descripcion="Consolidación de todas las secciones en un documento descargable.",
        instruccion_usuario="",
        requiere_friccion=False,
    ),
]


def get_seccion_by_id(seccion_id: str) -> SeccionContractual | None:
    """Busca una sección por su ID."""
    for s in SECCIONES:
        if s.id == seccion_id:
            return s
    return None


def get_secciones_con_friccion() -> list[SeccionContractual]:
    """Retorna solo las secciones que requieren ciclo dialéctico."""
    return [s for s in SECCIONES if s.requiere_friccion]
