"""
agente_redactor.py — Agente redactor del informe final (texto ROJO).

Recibe los outputs de los otros dos agentes y los sintetiza en una
narrativa formal apropiada para un informe regulatorio oficial.

El agente usa RAG sobre plantillas de redacción (data/docs/plantillas/)
para mantener consistencia de estilo con documentos oficiales.

Temperatura 0.3 (ligeramente más alta que los otros agentes) para producir
prosa más fluida y menos repetitiva, manteniendo la fidelidad a los hechos.

Estructura del informe producido:
1. Antecedentes y base legal
2. Metodología de análisis
3. Hallazgos principales (con cifras del Agente Datos)
4. Marco regulatorio aplicable (del Agente Regulatorio)
5. Conclusiones y recomendaciones
"""

import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents.base_agent import BaseAgent, AgentResult
from rag.rag_redactor import get_plantillas_retriever

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres el Agente Redactor, especialista en la producción de informes regulatorios formales del sector de telecomunicaciones en México.

=== FRAGMENTOS DE PLANTILLAS Y GUÍAS DE ESTILO ===
{template_context}
=== FIN DE PLANTILLAS ===

=== ANÁLISIS DE DATOS (Agente Datos) ===
{datos_result}
=== FIN DE ANÁLISIS DE DATOS ===

=== CONTEXTO REGULATORIO (Agente Regulatorio) ===
{regulatorio_result}
=== FIN DE CONTEXTO REGULATORIO ===

Redacta la sección narrativa del Informe de Cumplimiento de la Medida 83 con la siguiente estructura:

**I. ANTECEDENTES Y BASE LEGAL**
Describe brevemente la Medida 83 y su propósito. Cita la normativa aplicable usando las referencias del Agente Regulatorio.

**II. METODOLOGÍA DE ANÁLISIS**
Explica cómo se analizaron los datos de portabilidad para verificar el cumplimiento de la ventana de 60 días. Menciona las fuentes de datos utilizadas.

**III. HALLAZGOS PRINCIPALES**
Presenta con precisión los datos cuantitativos del Agente Datos:
- Cifras totales de portaciones en el periodo analizado
- Número y porcentaje de casos de contacto prohibido
- Desglose por operador/concesionario si está disponible
- Tendencia temporal del incumplimiento

**IV. MARCO REGULATORIO Y CONSECUENCIAS**
Integra el análisis del Agente Regulatorio sobre las implicaciones legales de los hallazgos.

**V. CONCLUSIONES Y RECOMENDACIONES**
Síntesis ejecutiva del cumplimiento de la Medida 83 y recomendaciones concretas.

Instrucciones de estilo:
- Español formal, estilo técnico-regulatorio (como los documentos oficiales del IFT)
- Usa referencias cruzadas: "De conformidad con la Medida 83..." / "Como se señala en la sección anterior..."
- Integra las cifras del Agente Datos con las citas del Agente Regulatorio de forma fluida
- El texto debe ser autocontenido: un lector sin contexto adicional debe comprenderlo
- Longitud objetivo: 500-700 palabras en el cuerpo del informe
- No repitas literalmente los textos de los agentes; sintetiza e integra

Pregunta que originó el análisis: {question}
"""


class AgenteRedactor(BaseAgent):
    """
    Agente de redacción del informe narrativo final.

    Produce texto en color ROJO en el documento Word final.
    """

    def __init__(self):
        # Temperatura ligeramente más alta para prosa más fluida
        super().__init__(temperature=0.3)
        self.retriever = get_plantillas_retriever()

    def run(
        self,
        question: str,
        datos_result: str,
        regulatorio_result: str,
    ) -> AgentResult:
        """
        Redacta el informe narrativo integrando los outputs de otros agentes.

        Args:
            question: Pregunta original de análisis.
            datos_result: Texto con hallazgos cuantitativos del Agente Datos.
            regulatorio_result: Texto con análisis regulatorio del Agente Regulatorio.

        Returns:
            AgentResult con el informe narrativo completo.
        """
        self.logger.info("AgenteRedactor iniciando redacción del informe...")

        # Recuperar fragmentos de plantilla relevantes
        template_docs = self.retriever.invoke(question)

        if not template_docs:
            self.logger.warning(
                "No se encontraron plantillas de redacción. "
                "El agente usará estilo regulatorio estándar."
            )
            template_context = (
                "No hay plantillas disponibles. Usa el estilo regulatorio formal "
                "estándar del IFT: lenguaje técnico-jurídico, párrafos densos, "
                "citas normativas en formato 'De conformidad con [artículo]...'."
            )
        else:
            template_context = "\n\n---\n\n".join(
                doc.page_content for doc in template_docs
            )

        # Construir y ejecutar cadena LCEL
        prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
        chain = prompt | self.llm | StrOutputParser()

        response = chain.invoke({
            "question": question,
            "datos_result": datos_result,
            "regulatorio_result": regulatorio_result,
            "template_context": template_context,
        })

        self.logger.info(
            f"AgenteRedactor completado. Informe: {len(response)} chars"
        )

        return AgentResult(
            agent_name="AgenteRedactor",
            content=response,
            metadata={
                "template_docs_used": len(template_docs),
                "temperature": 0.3,
                "question": question,
            },
        )
