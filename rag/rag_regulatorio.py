"""
rag_regulatorio.py — RAG sobre documentos regulatorios del IFT.

Indexa PDFs en data/docs/regulatorio/, que deben incluir:
- La resolución IFT con la Medida 83 completa
- El documento de metodología de análisis de portabilidad
- Cualquier otro documento regulatorio relevante (acuerdos, modificaciones)

El Agente Regulatorio usa este retriever para:
- Citar el texto exacto de la Medida 83
- Explicar el alcance y contexto normativo
- Identificar sanciones y procedimientos de verificación
- Contextualizar los hallazgos cuantitativos dentro del marco legal

Para agregar documentos: coloca PDFs en data/docs/regulatorio/
"""

import logging
from langchain_core.vectorstores import VectorStoreRetriever
from rag.rag_builder import build_or_load_vectorstore, get_retriever
import config

logger = logging.getLogger(__name__)

COLLECTION_NAME = "regulatorio"


def get_regulatorio_retriever(
    force_reingest: bool = False,
    k: int = 5,
) -> VectorStoreRetriever:
    """
    Retorna un retriever sobre documentos regulatorios del IFT.

    Args:
        force_reingest: Si True, re-procesa todos los PDFs de regulatorio/.
            Usar cuando se agreguen nuevos documentos regulatorios.
        k: Número de fragmentos a recuperar (5 para documentos legales,
           donde múltiples artículos relacionados pueden ser relevantes).

    Returns:
        VectorStoreRetriever listo para invocar.

    Ejemplo de uso:
        retriever = get_regulatorio_retriever()
        docs = retriever.invoke("¿Cuál es la sanción por violar la Medida 83?")
    """
    vectorstore = build_or_load_vectorstore(
        collection_name=COLLECTION_NAME,
        persist_directory=config.CHROMA_REGULATORIO_DIR,
        docs_directory=config.DOCS_REGULATORIO_DIR,
        file_extension=".pdf",
        force_reingest=force_reingest,
    )
    return get_retriever(vectorstore, k=k, search_type="similarity")
