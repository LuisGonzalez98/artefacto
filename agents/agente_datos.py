"""
agente_datos.py — Agente de análisis de datos de portabilidad (texto AZUL).

Combina dos capacidades:
1. RAG sobre documentación del esquema (rag_datos.py): proporciona contexto
   de negocio para que el SQL Agent comprenda el dominio de portabilidad.
2. SQL Agent de LangChain: formula y ejecuta queries SQL contra PostgreSQL
   para obtener métricas reales de cumplimiento de la Medida 83.

Flujo:
    question → schema RAG → contexto enriquecido → SQL Agent → respuesta con datos

El SQL Agent usa el patrón ReAct (zero-shot-react-description) que es más
robusto con modelos locales (llama3.1) que el modo openai-tools, ya que
no depende de la capacidad de tool-calling estructurado del modelo.

Temperatura 0.0: la generación de SQL debe ser determinista para evitar
errores de sintaxis o resultados inconsistentes entre ejecuciones.
"""

import logging
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit

from agents.base_agent import BaseAgent, AgentResult
from rag.rag_datos import get_schema_retriever
from db.postgres_client import get_sql_database

logger = logging.getLogger(__name__)

# Prompt del sistema que se inyecta al SQL Agent.
# {schema_context} se reemplaza con los fragmentos recuperados por el RAG.
# {question} es la pregunta de análisis del orquestador.
SYSTEM_PROMPT_TEMPLATE = """Eres el Agente Datos, especialista en análisis cuantitativo de portabilidad numérica móvil.

Tu objetivo es analizar el cumplimiento de la Medida 83 del IFT, que establece:
"El Agente Económico Preponderante no podrá contactar al Usuario Final que haya sido
portado desde su red durante los 60 días naturales posteriores a la ejecución de la portabilidad."

=== DOCUMENTACIÓN DEL ESQUEMA DE BASE DE DATOS ===
{schema_context}
=== FIN DE DOCUMENTACIÓN ===

Con base en la documentación anterior y las tablas disponibles en la base de datos:

1. Identifica las tablas y columnas relevantes para el análisis de Medida 83
2. Formula consultas SQL que calculen:
   - Total de portaciones en el periodo de análisis
   - Casos donde se realizó contacto dentro de los 60 días prohibidos
   - Porcentaje de incumplimiento por concesionario/operador
   - Evolución temporal del incumplimiento
3. Ejecuta las consultas y presenta los resultados con números concretos
4. Si no hay datos de contacto post-portación disponibles, indica qué datos
   sí están disponibles y calcula las métricas posibles
5. Documenta brevemente cada query ejecutada

Instrucciones adicionales:
- Usa fechas en formato ISO (YYYY-MM-DD)
- Si una consulta falla, ajústala y reintenta con la sintaxis correcta
- Reporta resultados en español con unidades claras (usuarios, días, porcentajes)

Pregunta de análisis: {question}
"""


class AgenteDatos(BaseAgent):
    """
    Agente de análisis de datos de portabilidad.

    Produce texto en color AZUL en el documento Word final.
    """

    def __init__(self):
        # temperature=0.0 para generación determinista de SQL
        super().__init__(temperature=0.0)
        self.schema_retriever = get_schema_retriever()
        self.db = get_sql_database()

    def run(self, question: str) -> AgentResult:
        """
        Analiza datos de portabilidad relacionados con la Medida 83.

        Args:
            question: Pregunta de análisis formulada por el orquestador.

        Returns:
            AgentResult con hallazgos cuantitativos y queries ejecutadas.
        """
        self.logger.info(f"AgenteDatos iniciando análisis: {question[:100]}...")

        # Paso 1: Recuperar contexto de esquema via RAG
        schema_docs = self.schema_retriever.invoke(question)
        schema_context = "\n\n".join(
            f"[Fuente: {doc.metadata.get('source', 'schema_docs')}]\n{doc.page_content}"
            for doc in schema_docs
        )

        if not schema_context.strip():
            schema_context = (
                "No hay documentación de esquema disponible. "
                "Infiere el esquema directamente de las tablas disponibles en la BD."
            )
            self.logger.warning(
                "No se encontraron documentos en schema_docs/. "
                "El agente operará solo con el DDL de la BD."
            )

        # Paso 2: Construir pregunta enriquecida con contexto de esquema
        augmented_question = SYSTEM_PROMPT_TEMPLATE.format(
            schema_context=schema_context,
            question=question,
        )

        # Paso 3: Crear y ejecutar el SQL Agent
        # zero-shot-react-description usa el patrón ReAct (más robusto con LLMs locales)
        toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        sql_agent = create_sql_agent(
            llm=self.llm,
            toolkit=toolkit,
            agent_type="zero-shot-react-description",
            verbose=True,
            max_iterations=15,       # Permitir varios intentos de corrección de SQL
            max_execution_time=180,  # Timeout de 3 minutos
            handle_parsing_errors=True,
            early_stopping_method="generate",
        )

        self.logger.info("Ejecutando SQL Agent...")
        result = sql_agent.invoke({"input": augmented_question})
        output_text = result.get("output", str(result))

        self.logger.info(f"AgenteDatos completado. Respuesta: {len(output_text)} chars")

        return AgentResult(
            agent_name="AgenteDatos",
            content=output_text,
            metadata={
                "schema_docs_retrieved": len(schema_docs),
                "question": question,
                "schema_sources": [
                    doc.metadata.get("source", "desconocida") for doc in schema_docs
                ],
            },
        )
