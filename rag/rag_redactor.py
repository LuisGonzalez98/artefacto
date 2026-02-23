"""
rag_redactor.py — RAG sobre plantillas y guías de redacción de informes.

Indexa archivos .txt en data/docs/plantillas/, que deben incluir:
- Fragmentos de informes regulatorios anteriores bien redactados
- Guías de estilo para la redacción de informes del IFT
- Estructuras típicas de secciones (antecedentes, metodología, hallazgos)
- Frases y fórmulas de citación regulatoria estándar
- Ejemplos de conclusiones y recomendaciones

El Agente Redactor usa este retriever para:
- Mantener consistencia de estilo con documentos oficiales anteriores
- Usar la estructura correcta de un informe regulatorio
- Citar la normativa con la fórmula correcta
- Producir texto apropiado para lectores técnico-regulatorios

Para agregar plantillas: coloca archivos .txt en data/docs/plantillas/
"""

import logging
from langchain_core.vectorstores import VectorStoreRetriever
from rag.rag_builder import build_or_load_vectorstore, get_retriever
import config

logger = logging.getLogger(__name__)

COLLECTION_NAME = "plantillas"


def get_plantillas_retriever(
    force_reingest: bool = False,
    k: int = 3,
) -> VectorStoreRetriever:
    """
    Retorna un retriever sobre plantillas y guías de redacción.

    Args:
        force_reingest: Si True, re-procesa todos los archivos de plantillas/.
        k: Número de fragmentos a recuperar (3 suele ser suficiente para
           guiar el estilo sin sobrecargar el prompt).

    Returns:
        VectorStoreRetriever listo para invocar.
    """
    vectorstore = build_or_load_vectorstore(
        collection_name=COLLECTION_NAME,
        persist_directory=config.CHROMA_REDACTOR_DIR,
        docs_directory=config.DOCS_PLANTILLAS_DIR,
        file_extension=".txt",
        force_reingest=force_reingest,
    )
    return get_retriever(vectorstore, k=k, search_type="similarity")
