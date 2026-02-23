"""
agente_regulatorio.py — Agente de análisis regulatorio (texto VERDE).

Proporciona el marco legal y normativo de la Medida 83 del IFT.
Usa RAG sobre documentos regulatorios (PDFs en data/docs/regulatorio/).

El agente recibe:
- La pregunta original de análisis
- Los hallazgos cuantitativos del Agente Datos

Y produce:
- Citas textuales de la Medida 83 y artículos relacionados
- Interpretación del alcance y propósito de la prohibición
- Contextualización legal de los hallazgos cuantitativos
- Análisis de si los niveles de incumplimiento son sancionables

Usa una cadena LCEL simple (prompt → llm → parser) ya que es una tarea
de generación de texto, no de uso de herramientas externas.
"""

import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from agents.base_agent import BaseAgent, AgentResult
from rag.rag_regulatorio import get_regulatorio_retriever

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres el Agente Regulatorio, especialista en normativa de portabilidad numérica móvil del IFT (Instituto Federal de Telecomunicaciones) de México.

=== DOCUMENTOS REGULATORIOS RECUPERADOS ===
{regulatory_context}
=== FIN DE DOCUMENTOS REGULATORIOS ===

=== HALLAZGOS CUANTITATIVOS DEL AGENTE DATOS ===
{datos_result}
=== FIN DE HALLAZGOS ===

Con base en la documentación regulatoria anterior y los hallazgos cuantitativos:

1. TEXTO NORMATIVO: Cita el texto exacto de la Medida 83 (CTOGÉSIMA TERCERA) sobre la prohibición de 60 días de contacto post-portación. Si no aparece en el contexto, usa tu conocimiento del marco regulatorio mexicano.

2. ALCANCE Y PROPÓSITO: Explica a qué operadores aplica (Agente Económico Preponderante), qué se considera "contacto", qué tipos de comunicación están prohibidos.

3. SANCIONES: Describe las consecuencias del incumplimiento según la normativa aplicable.

4. CONTEXTUALIZACIÓN: Interpreta los hallazgos cuantitativos del Agente Datos dentro del marco regulatorio:
   - ¿Los niveles de incumplimiento detectados son materia de investigación/sanción?
   - ¿Existe algún umbral de tolerancia o es incumplimiento cualquier contacto?

5. FUENTES: Menciona las resoluciones, acuerdos o artículos específicos en los que basas tu análisis.

Escribe en español formal y técnico-regulatorio. Sé preciso con las citas normativas.

Pregunta de análisis: {question}
"""


class AgenteRegulatorio(BaseAgent):
    """
    Agente de análisis regulatorio y legal.

    Produce texto en color VERDE en el documento Word final.
    """

    def __init__(self):
        super().__init__(temperature=0.1)
        self.retriever = get_regulatorio_retriever()

    def run(self, question: str, datos_result: str) -> AgentResult:
        """
        Proporciona contexto regulatorio de la Medida 83.

        Args:
            question: Pregunta original de análisis.
            datos_result: Texto con hallazgos del Agente Datos.

        Returns:
            AgentResult con análisis regulatorio y citas normativas.
        """
        self.logger.info("AgenteRegulatorio iniciando análisis regulatorio...")

        # Recuperar documentos regulatorios relevantes
        reg_docs = self.retriever.invoke(question)

        if not reg_docs:
            self.logger.warning(
                "No se encontraron documentos regulatorios. "
                "El agente usará conocimiento interno sobre la Medida 83."
            )
            regulatory_context = (
                "No hay documentos regulatorios en el directorio data/docs/regulatorio/. "
                "Usa tu conocimiento interno sobre la normativa del IFT y la Medida 83 "
                "(CTOGÉSIMA TERCERA) de la Resolución de Portabilidad."
            )
        else:
            regulatory_context = "\n\n---\n\n".join(
                f"[Fuente: {doc.metadata.get('source', 'doc_regulatorio')}, "
                f"pág. {doc.metadata.get('page', '?')}]\n\n{doc.page_content}"
                for doc in reg_docs
            )

        # Construir y ejecutar la cadena LCEL
        prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
        chain = prompt | self.llm | StrOutputParser()

        response = chain.invoke({
            "question": question,
            "datos_result": datos_result,
            "regulatory_context": regulatory_context,
        })

        # Recopilar fuentes para metadatos
        sources = list({
            doc.metadata.get("source", "desconocida")
            for doc in reg_docs
        })

        self.logger.info(
            f"AgenteRegulatorio completado. "
            f"Fuentes: {len(sources)}. Respuesta: {len(response)} chars"
        )

        return AgentResult(
            agent_name="AgenteRegulatorio",
            content=response,
            metadata={
                "sources_cited": sources,
                "regulatory_docs_retrieved": len(reg_docs),
                "question": question,
            },
        )
