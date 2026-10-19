"""Seguimiento del estado mental/cognitivo del sistema multiagente.

Soporta métricas por sección y por agente del comité evaluador.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ConfianzaNivel(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


@dataclass
class MetricasAgente:
    """Métricas de un agente específico del comité."""
    evaluaciones: int = 0
    aprobaciones: int = 0
    rechazos: int = 0

    @property
    def tasa_rechazo(self) -> float:
        return self.rechazos / self.evaluaciones if self.evaluaciones > 0 else 0.0


@dataclass
class MetricasSeccion:
    """Métricas de una sección específica."""
    iteraciones: int = 0
    aprobaciones: int = 0
    rechazos: int = 0
    tutor_activado: bool = False
    timestamp_inicio: datetime | None = None
    timestamp_fin: datetime | None = None
    agentes_participaron: list[str] = field(default_factory=list)

    @property
    def tasa_aprobacion(self) -> float:
        total = self.aprobaciones + self.rechazos
        return self.aprobaciones / total if total > 0 else 0.0

    @property
    def duracion_segundos(self) -> float | None:
        if self.timestamp_inicio and self.timestamp_fin:
            return (self.timestamp_fin - self.timestamp_inicio).total_seconds()
        return None


@dataclass
class EstadoMental:
    """Estado cognitivo agregado del sistema para una sesión de estructuración."""

    seccion_actual: str = "justificacion"
    metricas_por_seccion: dict[str, MetricasSeccion] = field(default_factory=dict)
    metricas_por_agente: dict[str, MetricasAgente] = field(default_factory=dict)
    observaciones_clave: list[str] = field(default_factory=list)

    def _get_seccion(self, seccion: str | None = None) -> MetricasSeccion:
        s = seccion or self.seccion_actual
        if s not in self.metricas_por_seccion:
            self.metricas_por_seccion[s] = MetricasSeccion()
        return self.metricas_por_seccion[s]

    def _get_agente(self, agente: str) -> MetricasAgente:
        if agente not in self.metricas_por_agente:
            self.metricas_por_agente[agente] = MetricasAgente()
        return self.metricas_por_agente[agente]

    def iniciar_seccion(self, seccion: str) -> None:
        """Marca el inicio de una nueva sección."""
        self.seccion_actual = seccion
        ms = self._get_seccion(seccion)
        ms.timestamp_inicio = datetime.now(timezone.utc)

    def registrar_iteracion(self, aprobada: bool, agente: str = "",
                            observacion: str = "", seccion: str | None = None) -> None:
        """Registrar el resultado de una iteración del ciclo dialéctico."""
        ms = self._get_seccion(seccion)
        ms.iteraciones += 1
        if aprobada:
            ms.aprobaciones += 1
        else:
            ms.rechazos += 1
        if agente:
            if agente not in ms.agentes_participaron:
                ms.agentes_participaron.append(agente)
            ma = self._get_agente(agente)
            ma.evaluaciones += 1
            if aprobada:
                ma.aprobaciones += 1
            else:
                ma.rechazos += 1
        if observacion:
            self.observaciones_clave.append(observacion)

    def registrar_tutor(self, seccion: str | None = None) -> None:
        """Registra que se activó el tutor en la sección."""
        ms = self._get_seccion(seccion)
        ms.tutor_activado = True

    def finalizar(self, seccion: str | None = None) -> None:
        """Marca la sección como finalizada."""
        ms = self._get_seccion(seccion)
        ms.timestamp_fin = datetime.now(timezone.utc)

    @property
    def nivel_confianza(self) -> ConfianzaNivel:
        """Confianza global basada en todas las secciones."""
        total_aprob = sum(m.aprobaciones for m in self.metricas_por_seccion.values())
        total_rech = sum(m.rechazos for m in self.metricas_por_seccion.values())
        total = total_aprob + total_rech
        tasa = total_aprob / total if total > 0 else 0.0
        if tasa >= 0.8:
            return ConfianzaNivel.ALTA
        if tasa >= 0.5:
            return ConfianzaNivel.MEDIA
        return ConfianzaNivel.BAJA

    def resumen(self) -> dict:
        """Resumen global para mostrar en el frontend."""
        total_iter = sum(m.iteraciones for m in self.metricas_por_seccion.values())
        total_aprob = sum(m.aprobaciones for m in self.metricas_por_seccion.values())
        total_rech = sum(m.rechazos for m in self.metricas_por_seccion.values())
        total = total_aprob + total_rech
        return {
            "seccion": self.seccion_actual,
            "confianza": self.nivel_confianza.value,
            "iteraciones": total_iter,
            "tasa_aprobacion": f"{(total_aprob / total * 100) if total > 0 else 0:.0f}%",
            "secciones_completadas": sum(
                1 for m in self.metricas_por_seccion.values() if m.timestamp_fin
            ),
        }

    def resumen_agentes(self) -> dict[str, dict]:
        """Resumen por agente para el dashboard."""
        return {
            agente: {
                "evaluaciones": m.evaluaciones,
                "aprobaciones": m.aprobaciones,
                "rechazos": m.rechazos,
                "tasa_rechazo": f"{m.tasa_rechazo:.0%}",
            }
            for agente, m in self.metricas_por_agente.items()
        }
