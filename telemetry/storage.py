"""Persistencia SQLite para la telemetría cognitiva.

Dos tablas:
  - sessions: una fila por sesión de estructuración completa
  - events:   una fila por cada evento medible (dwell time, palabras, etc.)
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "telemetry.db"


class TelemetryDB:
    """Conexión y operaciones sobre la base de datos de telemetría."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_tables(self) -> None:
        """Crea las tablas si no existen."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              TEXT PRIMARY KEY,
                modalidad       TEXT,
                objeto          TEXT,
                presupuesto     REAL,
                inicio          TEXT NOT NULL,
                fin             TEXT,
                completada      INTEGER DEFAULT 0,
                secciones_completadas INTEGER DEFAULT 0,
                total_secciones INTEGER DEFAULT 4
            );

            CREATE TABLE IF NOT EXISTS events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                seccion         TEXT NOT NULL,
                fase            TEXT NOT NULL,
                agente          TEXT,
                tipo_evento     TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                valor_numerico  REAL,
                valor_texto     TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_session
                ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_tipo
                ON events(tipo_evento);
        """)
        conn.commit()
        logger.info("Telemetry DB inicializada en '%s'.", self.db_path)

    def insert_session(self, session_id: str, modalidad: str, objeto: str,
                       presupuesto: float, inicio: str, total_secciones: int = 4) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO sessions
               (id, modalidad, objeto, presupuesto, inicio, total_secciones)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, modalidad, objeto, presupuesto, inicio, total_secciones),
        )
        conn.commit()

    def update_session_end(self, session_id: str, fin: str,
                           completada: bool, secciones_completadas: int) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE sessions SET fin=?, completada=?, secciones_completadas=?
               WHERE id=?""",
            (fin, int(completada), secciones_completadas, session_id),
        )
        conn.commit()

    def insert_event(self, session_id: str, seccion: str, fase: str,
                     agente: str | None, tipo_evento: str, timestamp: str,
                     valor_numerico: float | None = None,
                     valor_texto: str | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO events
               (session_id, seccion, fase, agente, tipo_evento, timestamp,
                valor_numerico, valor_texto)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, seccion, fase, agente, tipo_evento, timestamp,
             valor_numerico, valor_texto),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Queries para el dashboard
    # ------------------------------------------------------------------
    def get_all_sessions(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM sessions ORDER BY inicio DESC").fetchall()
        return [dict(r) for r in rows]

    def get_events_for_session(self, session_id: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_dwell_times(self) -> list[dict]:
        """Retorna todos los eventos de tipo dwell_time."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT e.*, s.modalidad, s.objeto
               FROM events e JOIN sessions s ON e.session_id = s.id
               WHERE e.tipo_evento = 'dwell_time_seconds'
               ORDER BY e.timestamp""",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_word_counts(self) -> list[dict]:
        """Retorna eventos de conteo de palabras."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT e.*, s.modalidad
               FROM events e JOIN sessions s ON e.session_id = s.id
               WHERE e.tipo_evento IN ('palabras_borrador', 'palabras_defensa',
                                        'profundidad_lexica')
               ORDER BY e.timestamp""",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_agent_rejection_stats(self) -> list[dict]:
        """Estadísticas de rechazo por agente."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT agente,
                      COUNT(*) as total_evaluaciones,
                      SUM(CASE WHEN valor_texto='rechazada' THEN 1 ELSE 0 END) as rechazos,
                      SUM(CASE WHEN valor_texto='aprobada' THEN 1 ELSE 0 END) as aprobaciones
               FROM events
               WHERE tipo_evento = 'evaluacion_resultado'
               GROUP BY agente""",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_abandonment_rate(self) -> dict:
        """Tasa de abandono: sesiones no completadas / total."""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN completada=1 THEN 1 ELSE 0 END) as completadas
               FROM sessions""",
        ).fetchone()
        d = dict(row)
        total = d["total"]
        completadas = d["completadas"]
        return {
            "total": total,
            "completadas": completadas,
            "abandonadas": total - completadas,
            "tasa_abandono": f"{((total - completadas) / total * 100) if total > 0 else 0:.1f}%",
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
