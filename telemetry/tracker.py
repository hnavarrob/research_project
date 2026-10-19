"""Tracker de telemetría cognitiva para el sistema dialéctico.

Captura eventos de interacción del usuario y los persiste en SQLite
para análisis posterior en el dashboard de investigación.

Métricas capturadas:
  - Dwell Time: tiempo de reflexión del usuario (segundos)
  - Volumen Léxico: cantidad de palabras en borrador y defensa
  - Profundidad Léxica: ratio palabras únicas / total
  - Resultado de evaluación por agente
  - Tasa de abandono (sesiones no completadas)
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from telemetry.storage import TelemetryDB

logger = logging.getLogger(__name__)


class TelemetryTracker:
    """Captura y persiste eventos de telemetría cognitiva."""

    def __init__(self, db: TelemetryDB | None = None):
        self._db = db or TelemetryDB()
        self._session_id: str | None = None
        self._condition: str | None = None
        self._friction_start: datetime | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def condition(self) -> str | None:
        return self._condition

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Sesión
    # ------------------------------------------------------------------
    def start_session(self, modalidad: str, objeto: str, presupuesto: float,
                      total_secciones: int = 4,
                      condition: str | None = None) -> str:
        """Inicia una sesión de estructuración."""
        self._session_id = str(uuid.uuid4())[:8]
        self._condition = condition
        self._db.insert_session(
            session_id=self._session_id,
            modalidad=modalidad,
            objeto=objeto,
            presupuesto=presupuesto,
            inicio=self._now(),
            total_secciones=total_secciones,
            condition=condition,
        )
        logger.info("Telemetry: sesión %s iniciada (condition=%s).",
                    self._session_id, condition)
        return self._session_id

    def end_session(self, completada: bool, secciones_completadas: int) -> None:
        """Finaliza la sesión."""
        if self._session_id:
            self._db.update_session_end(
                session_id=self._session_id,
                fin=self._now(),
                completada=completada,
                secciones_completadas=secciones_completadas,
            )
            logger.info("Telemetry: sesión %s finalizada (completada=%s).",
                        self._session_id, completada)

    # ------------------------------------------------------------------
    # Eventos de fricción
    # ------------------------------------------------------------------
    def start_friction_timer(self) -> None:
        """Marca el inicio del período de reflexión (cuando aparece la observación)."""
        self._friction_start = datetime.now(timezone.utc)

    def record_dwell_time(self, seccion: str, agente: str) -> float | None:
        """Registra el dwell time (tiempo de reflexión) y lo retorna en segundos."""
        if not self._session_id or not self._friction_start:
            return None

        dwell_seconds = (datetime.now(timezone.utc) - self._friction_start).total_seconds()
        self._db.insert_event(
            session_id=self._session_id,
            seccion=seccion,
            fase="friccion",
            agente=agente,
            tipo_evento="dwell_time_seconds",
            timestamp=self._now(),
            valor_numerico=round(dwell_seconds, 2),
            condition=self._condition,
        )
        self._friction_start = None
        logger.info("Telemetry: dwell_time=%.1fs (sección=%s, agente=%s)",
                     dwell_seconds, seccion, agente)
        return dwell_seconds

    # ------------------------------------------------------------------
    # Métricas léxicas
    # ------------------------------------------------------------------
    def record_text_metrics(self, seccion: str, fase: str, texto: str,
                            agente: str | None = None) -> dict:
        """Registra métricas léxicas de un texto (borrador o defensa)."""
        if not self._session_id:
            return {}

        palabras = texto.split()
        total_palabras = len(palabras)
        palabras_unicas = len(set(w.lower() for w in palabras))
        profundidad = palabras_unicas / total_palabras if total_palabras > 0 else 0.0

        tipo_palabras = f"palabras_{fase}"
        self._db.insert_event(
            session_id=self._session_id,
            seccion=seccion,
            fase=fase,
            agente=agente,
            tipo_evento=tipo_palabras,
            timestamp=self._now(),
            valor_numerico=total_palabras,
            condition=self._condition,
        )
        self._db.insert_event(
            session_id=self._session_id,
            seccion=seccion,
            fase=fase,
            agente=agente,
            tipo_evento="profundidad_lexica",
            timestamp=self._now(),
            valor_numerico=round(profundidad, 4),
            condition=self._condition,
        )

        return {
            "total_palabras": total_palabras,
            "palabras_unicas": palabras_unicas,
            "profundidad_lexica": profundidad,
        }

    # ------------------------------------------------------------------
    # Resultado de evaluación
    # ------------------------------------------------------------------
    def record_evaluation(self, seccion: str, agente: str, aprobada: bool) -> None:
        """Registra el resultado de una evaluación del comité."""
        if not self._session_id:
            return

        self._db.insert_event(
            session_id=self._session_id,
            seccion=seccion,
            fase="evaluacion",
            agente=agente,
            tipo_evento="evaluacion_resultado",
            timestamp=self._now(),
            valor_texto="aprobada" if aprobada else "rechazada",
            condition=self._condition,
        )

    def record_section_complete(self, seccion: str) -> None:
        """Marca una sección como completada."""
        if not self._session_id:
            return

        self._db.insert_event(
            session_id=self._session_id,
            seccion=seccion,
            fase="sintesis",
            agente=None,
            tipo_evento="seccion_completada",
            timestamp=self._now(),
            condition=self._condition,
        )

    def record_tutor_activated(self, seccion: str) -> None:
        """Registra que se activó el tutor (el usuario falló 2 veces)."""
        if not self._session_id:
            return

        self._db.insert_event(
            session_id=self._session_id,
            seccion=seccion,
            fase="friccion",
            agente="tutor",
            tipo_evento="tutor_activado",
            timestamp=self._now(),
            condition=self._condition,
        )
