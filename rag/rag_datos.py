"""
rag_datos.py — RAG sobre documentación del esquema de la BD de portabilidad.

Este RAG NO indexa los datos crudos de PostgreSQL.
Indexa archivos .txt en data/docs/schema_docs/ que describen:
- El DDL (CREATE TABLE) de las tablas relevantes
- El significado de cada columna en el contexto de portabilidad móvil
- La lógica de negocio de la Medida 83 (ventana de 60 días)
- Ejemplos de queries SQL válidos contra la BD real

Este contexto se inyecta en el prompt del SQL Agent antes de que genere
consultas, dándole comprensión del dominio de negocio más allá del DDL crudo.

Para agregar contexto: coloca archivos .txt en data/docs/schema_docs/
Formato sugerido: un archivo por tabla, más uno con la lógica de Medida 83.
"""

import logging
from langchain_core.vectorstores import VectorStoreRetriever
from rag.rag_builder import build_or_load_vectorstore, get_retriever
import config

logger = logging.getLogger(__name__)

COLLECTION_NAME = "schema_docs"


def get_schema_retriever(
    force_reingest: bool = False,
    k: int = 3,
) -> VectorStoreRetriever:
    """
    Retorna un retriever sobre documentación del esquema de BD.

    Args:
        force_reingest: Si True, re-procesa todos los archivos de schema_docs/.
        k: Número de fragmentos a recuperar por consulta (3 suele ser suficiente
           para contexto de esquema; más puede saturar el prompt del SQL agent).

    Returns:
        VectorStoreRetriever listo para invocar con una pregunta de negocio.

    Ejemplo de uso:
        retriever = get_schema_retriever()
        docs = retriever.invoke("¿Cómo identificar contactos prohibidos por Medida 83?")
        context = "\\n\\n".join(d.page_content for d in docs)
    """
    vectorstore = build_or_load_vectorstore(
        collection_name=COLLECTION_NAME,
        persist_directory=config.CHROMA_DATOS_DIR,
        docs_directory=config.DOCS_SCHEMA_DIR,
        file_extension=".txt",
        force_reingest=force_reingest,
    )
    return get_retriever(vectorstore, k=k, search_type="similarity")
