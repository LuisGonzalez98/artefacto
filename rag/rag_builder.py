"""
rag_builder.py — Fábrica compartida de vectorstores ChromaDB.

Todos los módulos RAG del proyecto usan esta fábrica para:
- Crear y persistir colecciones ChromaDB por agente
- Cargar documentos (PDF o texto) y dividirlos en chunks
- Retornar un retriever listo para usar en cadenas LangChain

Diseñada para ser cross-platform (Mac + Windows):
- Todos los paths se convierten a str() antes de pasar a ChromaDB
- use_multithreading=False para estabilidad en Windows
- Idempotente: si la colección ya existe, no re-ingesta documentos

Nota sobre modelos de embeddings:
- Usa OllamaEmbeddings con nomic-embed-text (corre localmente, sin API key)
- El modelo debe estar disponible: ollama pull nomic-embed-text
"""

import logging
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.vectorstores import VectorStoreRetriever

import config

logger = logging.getLogger(__name__)


def get_embeddings() -> OllamaEmbeddings:
    """
    Retorna el modelo de embeddings configurado (Ollama local).

    Requiere que Ollama esté corriendo y el modelo esté disponible:
        ollama pull nomic-embed-text
    """
    return OllamaEmbeddings(
        base_url=config.OLLAMA_BASE_URL,
        model=config.OLLAMA_EMBED_MODEL,
    )


def build_or_load_vectorstore(
    collection_name: str,
    persist_directory: Path,
    docs_directory: Path,
    file_extension: str = ".txt",
    force_reingest: bool = False,
) -> Chroma:
    """
    Construye o carga una colección ChromaDB persistente.

    Si la colección ya existe y tiene documentos:
        - Si force_reingest=False, la carga sin re-procesar (rápido).
        - Si force_reingest=True, elimina documentos y re-ingesta.

    Si la colección no existe o está vacía:
        - Carga documentos de docs_directory
        - Los divide en chunks según config.CHUNK_SIZE / CHUNK_OVERLAP
        - Los ingesta y persiste en persist_directory

    Args:
        collection_name: Nombre único de la colección en ChromaDB.
        persist_directory: Carpeta donde ChromaDB guarda los datos.
        docs_directory: Carpeta que contiene los documentos fuente.
        file_extension: Extensión de archivos a cargar (".txt" o ".pdf").
        force_reingest: Si True, re-procesa todos los documentos aunque ya existan.

    Returns:
        Objeto Chroma listo para consultas.
    """
    # Crear directorio de persistencia si no existe
    persist_directory.mkdir(parents=True, exist_ok=True)

    embeddings = get_embeddings()

    # Nota: str() es necesario; ChromaDB no acepta Path objects en todas las versiones
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
    )

    # Verificar si ya hay documentos en la colección
    existing_count = vectorstore._collection.count()
    if existing_count > 0 and not force_reingest:
        logger.info(
            f"Colección '{collection_name}' ya tiene {existing_count} fragmentos. "
            "Usando colección existente. Usa force_reingest=True para re-ingestar."
        )
        return vectorstore

    if force_reingest and existing_count > 0:
        logger.info(f"force_reingest=True: limpiando colección '{collection_name}'...")
        vectorstore.delete_collection()
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=str(persist_directory),
        )

    # Verificar que el directorio de documentos existe y tiene archivos
    if not docs_directory.exists():
        logger.warning(
            f"Directorio de documentos no existe: {docs_directory}\n"
            f"El RAG '{collection_name}' operará sin contexto documental.\n"
            f"Crea el directorio y agrega archivos {file_extension} para habilitarlo."
        )
        return vectorstore

    matching_files = list(docs_directory.rglob(f"*{file_extension}"))
    if not matching_files:
        logger.warning(
            f"No se encontraron archivos {file_extension} en {docs_directory}.\n"
            f"El RAG '{collection_name}' operará sin contexto documental."
        )
        return vectorstore

    logger.info(
        f"Ingestando {len(matching_files)} archivo(s) {file_extension} "
        f"desde {docs_directory} → colección '{collection_name}'..."
    )

    # Cargar documentos
    raw_docs = _load_documents(docs_directory, file_extension)
    if not raw_docs:
        logger.warning(f"No se pudieron cargar documentos de {docs_directory}")
        return vectorstore

    logger.info(f"Cargados {len(raw_docs)} documentos. Dividiendo en chunks...")

    # Dividir en chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(raw_docs)
    logger.info(f"Generados {len(chunks)} chunks → ingestando en ChromaDB...")

    # Ingestar en lotes para evitar problemas de memoria con colecciones grandes
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        vectorstore.add_documents(batch)
        logger.info(f"  Ingestados chunks {i + 1}–{min(i + batch_size, len(chunks))}")

    logger.info(f"Colección '{collection_name}' lista con {len(chunks)} chunks.")
    return vectorstore


def get_retriever(
    vectorstore: Chroma,
    k: int = 4,
    search_type: str = "similarity",
) -> VectorStoreRetriever:
    """
    Retorna un retriever configurado sobre el vectorstore dado.

    Args:
        vectorstore: Colección ChromaDB ya construida.
        k: Número de fragmentos a recuperar por consulta.
        search_type: "similarity" (coseno) o "mmr" (diversidad máxima).

    Returns:
        VectorStoreRetriever listo para usar en cadenas LCEL.
    """
    return vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs={"k": k},
    )


def _load_documents(docs_directory: Path, file_extension: str) -> list:
    """
    Carga documentos de un directorio según la extensión.

    - .pdf → PyPDFLoader (extrae texto página por página)
    - Otros → TextLoader con encoding UTF-8 (con fallback a latin-1)

    use_multithreading=False por compatibilidad con Windows.
    """
    glob_pattern = f"**/*{file_extension}"

    if file_extension.lower() == ".pdf":
        loader_cls = PyPDFLoader
        loader_kwargs = {}
    else:
        loader_cls = TextLoader
        # encoding="utf-8" funciona en Mac/Linux; en Windows puede requerir "utf-8-sig"
        loader_kwargs = {"encoding": "utf-8"}

    try:
        loader = DirectoryLoader(
            str(docs_directory),
            glob=glob_pattern,
            loader_cls=loader_cls,
            loader_kwargs=loader_kwargs if loader_kwargs else None,
            show_progress=True,
            use_multithreading=False,  # Más estable en Windows
            silent_errors=True,        # No crashear por un archivo corrupto
        )
        return loader.load()
    except Exception as e:
        logger.error(f"Error cargando documentos de {docs_directory}: {e}")
        # Fallback: intentar cargar uno por uno
        docs = []
        for filepath in docs_directory.rglob(f"*{file_extension}"):
            try:
                if file_extension.lower() == ".pdf":
                    single_loader = PyPDFLoader(str(filepath))
                else:
                    single_loader = TextLoader(str(filepath), encoding="utf-8")
                docs.extend(single_loader.load())
            except Exception as file_err:
                logger.warning(f"  No se pudo cargar {filepath}: {file_err}")
        return docs
