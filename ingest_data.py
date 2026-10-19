"""Pipeline de ingestión para documentos normativos de contratación pública.

Carga PDFs desde data/, los divide en chunks optimizados para textos legales,
y los almacena en ChromaDB con embeddings de Ollama.

Uso:
    python ingest_data.py              # Ingesta incremental
    python ingest_data.py --reset      # Borra la DB y reingesta todo
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import sys
import unicodedata
from pathlib import Path

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data"
CHROMA_PATH = BASE_DIR / "chroma_db"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# Separadores optimizados para legislación colombiana
LEGAL_SEPARATORS = [
    "\nARTÍCULO",
    "\nArtículo",
    "\nPARÁGRAFO",
    "\nParágrafo",
    "\nCAPÍTULO",
    "\nTÍTULO",
    "\nSECCIÓN",
    "\n\n",
    "\n",
    ". ",
    " ",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------
def _generate_chunk_id(source: str, page: int, index: int) -> str:
    """Genera un ID determinístico para un chunk basado en fuente, página e índice."""
    raw = f"{source}:{page}:{index}"
    return hashlib.md5(raw.encode()).hexdigest()


def _clean_text(text: str) -> str:
    """Limpia texto extraído de PDFs mal formados.

    Elimina bytes nulos, caracteres de control binarios y otros artefactos
    que causan el error 'Post /tokenize: EOF' en el tokenizador de Ollama.
    """
    if not text:
        return ""

    # 1. Normalizar unicode (NFC): unifica representaciones de caracteres
    text = unicodedata.normalize("NFC", text)

    # 2. Eliminar bytes nulos y caracteres de control no imprimibles
    #    Conserva: tabulaciones (\x09), saltos de línea (\x0a, \x0d), espacio (\x20+)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 3. Eliminar caracteres de sustitución unicode (□, caracteres corruptos)
    text = re.sub(r"[\ufffd\ufffe\uffff]", "", text)

    # 4. Eliminar secuencias de caracteres no imprimibles de rangos privados
    text = re.sub(r"[\ue000-\uf8ff]", "", text)

    # 5. Colapsar espacios en blanco excesivos (preservar saltos de línea simples)
    text = re.sub(r"[ \t]+", " ", text)          # múltiples espacios → uno
    text = re.sub(r"\n{3,}", "\n\n", text)         # más de 2 saltos → 2

    return text.strip()


def _clean_chunks(chunks: list) -> list:
    """Aplica _clean_text a todos los chunks y filtra los que quedan vacíos."""
    cleaned = []
    for chunk in chunks:
        clean_content = _clean_text(chunk.page_content)
        if clean_content and len(clean_content) > 10:
            chunk.page_content = clean_content
            cleaned.append(chunk)
    return cleaned


def _enrich_metadata(documents: list) -> list:
    """Enriquece la metadata de cada documento con información de la fuente.

    Añade:
      - tipo_norma: Ley, Decreto, Guía, Otro
      - nombre_corto: nombre del archivo sin extensión
      - dominio: subdirectorio padre (juridico, financiero, tecnico, general)
    """
    for doc in documents:
        source = doc.metadata.get("source", "")
        source_path = Path(source)
        filename = source_path.stem

        # Clasificar el tipo de norma por el nombre del archivo
        lower = filename.lower()
        if "ley" in lower:
            doc.metadata["tipo_norma"] = "Ley"
        elif "decreto" in lower:
            doc.metadata["tipo_norma"] = "Decreto"
        elif "guia" in lower or "manual" in lower:
            doc.metadata["tipo_norma"] = "Guía"
        else:
            doc.metadata["tipo_norma"] = "Otro"

        doc.metadata["nombre_corto"] = filename

        # Derivar dominio del subdirectorio padre
        # data/juridico/Ley_80.pdf → dominio = "juridico"
        parent_name = source_path.parent.name
        if parent_name in ("juridico", "financiero", "tecnico", "general"):
            doc.metadata["dominio"] = parent_name
        else:
            doc.metadata["dominio"] = "general"

    return documents


def _check_ollama_available() -> bool:
    """Verifica que Ollama esté corriendo y el modelo de embeddings disponible."""
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        embeddings.embed_query("test")
        return True
    except Exception as e:
        logger.error(
            "No se pudo conectar con Ollama. Asegúrese de que Ollama esté "
            "corriendo y que el modelo 'nomic-embed-text' esté descargado.\n"
            "  → Ejecute: ollama pull nomic-embed-text\n"
            "  Error: %s",
            e,
        )
        return False


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def ingest(*, reset: bool = False) -> None:
    """Ejecutar el pipeline de ingestión.

    Args:
        reset: Si True, elimina la base de datos existente antes de reingestar.
    """
    # 0. Verificar dependencias
    if not DATA_PATH.exists():
        logger.error(
            "La carpeta '%s' no existe. Créela y agregue los PDFs.", DATA_PATH
        )
        return

    if not _check_ollama_available():
        return

    # 1. Reset opcional
    if reset and CHROMA_PATH.exists():
        logger.warning("Eliminando base de datos existente en '%s'...", CHROMA_PATH)
        shutil.rmtree(CHROMA_PATH)

    # 2. Cargar PDFs
    logger.info("Cargando documentos desde '%s'...", DATA_PATH)
    loader = PyPDFDirectoryLoader(str(DATA_PATH))
    documents = loader.load()

    if not documents:
        logger.warning("No se encontraron documentos PDF en '%s'.", DATA_PATH)
        return

    unique_sources = {d.metadata.get("source") for d in documents}
    logger.info(
        "✅ Cargadas %d páginas de %d documentos.",
        len(documents),
        len(unique_sources),
    )

    # 3. Enriquecer metadata
    documents = _enrich_metadata(documents)

    # 4. Chunking con separadores legales
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=LEGAL_SEPARATORS,
        length_function=len,
    )
    chunks = splitter.split_documents(documents)

    # 4b. Limpiar y filtrar chunks — elimina bytes nulos, control chars y
    #     texto corrupto de PDFs mal formados (causa "tokenize EOF" en Ollama)
    original_count = len(chunks)
    chunks = _clean_chunks(chunks)
    filtered_count = original_count - len(chunks)
    if filtered_count > 0:
        logger.warning(
            "⚠️ Filtrados %d chunks corruptos o demasiado cortos.", filtered_count
        )

    # Asignar IDs determinísticos para idempotencia
    chunk_ids = []
    for i, chunk in enumerate(chunks):
        page = chunk.metadata.get("page", 0)
        source = chunk.metadata.get("source", "unknown")
        chunk_id = _generate_chunk_id(source, page, i)
        chunk.metadata["chunk_id"] = chunk_id
        chunk_ids.append(chunk_id)

    logger.info(
        "✅ Generados %d chunks válidos (size=%d, overlap=%d).",
        len(chunks),
        CHUNK_SIZE,
        CHUNK_OVERLAP,
    )

    # 5. Almacenar en ChromaDB (idempotente: usa IDs determinísticos)
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    logger.info("⏳ Creando/actualizando base de datos vectorial...")

    # Procesar en lotes para evitar 400 Bad Request por batches muy grandes
    BATCH_SIZE = 500

    if CHROMA_PATH.exists() and not reset:
        # Modo incremental: agregar solo chunks nuevos
        db = Chroma(
            persist_directory=str(CHROMA_PATH), embedding_function=embeddings
        )
        existing_ids = set(db.get()["ids"])
        new_chunks = [
            c for c, cid in zip(chunks, chunk_ids) if cid not in existing_ids
        ]
        new_ids = [cid for cid in chunk_ids if cid not in existing_ids]

        if new_chunks:
            for batch_start in range(0, len(new_chunks), BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, len(new_chunks))
                batch_chunks = new_chunks[batch_start:batch_end]
                batch_ids = new_ids[batch_start:batch_end]
                db.add_documents(batch_chunks, ids=batch_ids)
                logger.info(
                    "  → Lote %d-%d de %d procesado.",
                    batch_start + 1,
                    batch_end,
                    len(new_chunks),
                )
            logger.info(
                "✅ Agregados %d chunks nuevos (%d ya existían).",
                len(new_chunks),
                len(chunks) - len(new_chunks),
            )
        else:
            logger.info("✅ Todos los chunks ya existen. Sin cambios.")
    else:
        # Creación completa en lotes
        db = None
        total_ok = 0
        total_err = 0
        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(chunks))
            batch_chunks = chunks[batch_start:batch_end]
            batch_ids = chunk_ids[batch_start:batch_end]

            try:
                if db is None:
                    # Primer lote: crear la DB
                    db = Chroma.from_documents(
                        batch_chunks,
                        embeddings,
                        persist_directory=str(CHROMA_PATH),
                        ids=batch_ids,
                    )
                else:
                    # Lotes siguientes: agregar a la DB existente
                    db.add_documents(batch_chunks, ids=batch_ids)

                total_ok += len(batch_chunks)
                logger.info(
                    "  → Lote %d-%d de %d procesado. ✅",
                    batch_start + 1,
                    batch_end,
                    len(chunks),
                )
            except Exception as e:
                total_err += len(batch_chunks)
                logger.warning(
                    "  → Lote %d-%d falló (%s). Reintentando chunk a chunk...",
                    batch_start + 1,
                    batch_end,
                    e,
                )
                # Reintento chunk a chunk para aislar el/los corruptos
                if db is None:
                    db = Chroma(
                        persist_directory=str(CHROMA_PATH),
                        embedding_function=embeddings,
                    )
                for chunk, cid in zip(batch_chunks, batch_ids):
                    try:
                        db.add_documents([chunk], ids=[cid])
                        total_ok += 1
                        total_err -= 1
                    except Exception as inner_e:
                        logger.warning(
                            "    ✗ Chunk '%s' (pág %s) descartado: %s",
                            chunk.metadata.get("nombre_corto", "?"),
                            chunk.metadata.get("page", "?"),
                            inner_e,
                        )

        logger.info(
            "✅ Base de datos creada: %d chunks almacenados, %d descartados.",
            total_ok,
            total_err,
        )



if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    ingest(reset=reset_flag)