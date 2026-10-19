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
        """Crea las tablas si no existen y ejecuta migraciones no destructivas."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              TEXT PRIMARY KEY,
                session_id      TEXT,
                modalidad       TEXT,
                objeto          TEXT,
                presupuesto     REAL,
                inicio          TEXT NOT NULL,
                fin             TEXT,
                completada      INTEGER DEFAULT 0,
                secciones_completadas INTEGER DEFAULT 0,
                total_secciones INTEGER DEFAULT 4,
                condition       TEXT,
                tlx_completed   INTEGER DEFAULT 0
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
                condition       TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS nasa_tlx (
                session_id   TEXT,
                mental       REAL,
                fisica       REAL,
                temporal     REAL,
                rendimiento  REAL,
                esfuerzo     REAL,
                frustracion  REAL,
                submitted_at TEXT,
                PRIMARY KEY(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_session
                ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_tipo
                ON events(tipo_evento);
        """)

        # Migraciones no destructivas para bases de datos existentes
        session_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "condition" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN condition TEXT")
        if "session_id" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN session_id TEXT")
        if "tlx_completed" not in session_cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN tlx_completed INTEGER DEFAULT 0"
            )
        conn.execute(
            "UPDATE sessions SET session_id = id WHERE session_id IS NULL"
        )
        conn.execute(
            "UPDATE sessions SET tlx_completed = 0 WHERE tlx_completed IS NULL"
        )

        event_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(events)").fetchall()
        }
        if "condition" not in event_cols:
            conn.execute("ALTER TABLE events ADD COLUMN condition TEXT")

        conn.commit()
        logger.info("Telemetry DB inicializada en '%s'.", self.db_path)

    def insert_session(self, session_id: str, modalidad: str, objeto: str,
                       presupuesto: float, inicio: str, total_secciones: int = 4,
                       condition: str | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO sessions
               (id, session_id, modalidad, objeto, presupuesto, inicio, total_secciones, condition, tlx_completed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (session_id, session_id, modalidad, objeto, presupuesto, inicio, total_secciones, condition),
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
                     valor_texto: str | None = None,
                     condition: str | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO events
               (session_id, seccion, fase, agente, tipo_evento, timestamp,
                valor_numerico, valor_texto, condition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, seccion, fase, agente, tipo_evento, timestamp,
             valor_numerico, valor_texto, condition),
        )
        conn.commit()

    def insert_nasa_tlx(
        self,
        session_id: str,
        mental: float,
        fisica: float,
        temporal: float,
        rendimiento: float,
        esfuerzo: float,
        frustracion: float,
        submitted_at: str,
    ) -> None:
        """Inserta o actualiza respuestas NASA-TLX y marca tlx_completed=1 en sessions."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO nasa_tlx
               (session_id, mental, fisica, temporal, rendimiento, esfuerzo, frustracion, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                float(mental),
                float(fisica),
                float(temporal),
                float(rendimiento),
                float(esfuerzo),
                float(frustracion),
                submitted_at,
            ),
        )
        conn.execute(
            "UPDATE sessions SET tlx_completed = 1 WHERE id = ? OR session_id = ?",
            (session_id, session_id),
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
        completadas = d["completadas"] or 0
        return {
            "total": total,
            "completadas": completadas,
            "abandonadas": total - completadas,
            "tasa_abandono": f"{((total - completadas) / total * 100) if total > 0 else 0:.1f}%",
        }

    def get_nasa_tlx_stats(self) -> dict:
        """Retorna promedios globales de las 6 subescalas NASA-TLX y cruce A vs B."""
        conn = self._get_conn()
        global_row = conn.execute(
            """SELECT COUNT(*) as count,
                      AVG(mental) as mental,
                      AVG(fisica) as fisica,
                      AVG(temporal) as temporal,
                      AVG(rendimiento) as rendimiento,
                      AVG(esfuerzo) as esfuerzo,
                      AVG(frustracion) as frustracion
               FROM nasa_tlx"""
        ).fetchone()
        by_cond_rows = conn.execute(
            """SELECT COALESCE(s.condition, 'Sin condición') as condition,
                      COUNT(*) as count,
                      AVG(n.mental) as mental,
                      AVG(n.fisica) as fisica,
                      AVG(n.temporal) as temporal,
                      AVG(n.rendimiento) as rendimiento,
                      AVG(n.esfuerzo) as esfuerzo,
                      AVG(n.frustracion) as frustracion
               FROM nasa_tlx n
               LEFT JOIN sessions s ON n.session_id = s.id
               GROUP BY COALESCE(s.condition, 'Sin condición')
               ORDER BY condition"""
        ).fetchall()
        return {
            "global": dict(global_row) if global_row else {},
            "by_condition": [dict(r) for r in by_cond_rows],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
