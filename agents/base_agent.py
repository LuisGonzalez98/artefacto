"""
base_agent.py — Clase base abstracta para todos los agentes del sistema.

Define:
- AgentResult: dataclass con la salida estructurada de cualquier agente
- BaseAgent: ABC con LLM compartido y manejo de errores uniforme

Todos los agentes heredan de BaseAgent e implementan run().
El método _safe_run() envuelve run() con manejo de errores para que
el fallo de un agente no detenga el pipeline completo.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from langchain_ollama import ChatOllama

import config


@dataclass
class AgentResult:
    """
    Salida estructurada de un agente.

    Attributes:
        agent_name: Nombre del agente que produjo este resultado.
        content: El texto principal de la respuesta (análisis, narrativa, etc.).
        metadata: Información adicional sobre la ejecución (fuentes, queries, etc.).
        error: Mensaje de error si el agente falló; None si fue exitoso.
    """
    agent_name: str
    content: str
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def __str__(self) -> str:
        status = "OK" if self.succeeded else f"ERROR: {self.error}"
        return f"AgentResult({self.agent_name}, {status}, {len(self.content)} chars)"


class BaseAgent(ABC):
    """
    Clase base abstracta para todos los agentes del pipeline.

    Subclases deben implementar run() y retornar un AgentResult.
    El LLM se instancia una vez en __init__ y se reutiliza en todas las llamadas.

    Patrón de uso recomendado en el orquestador:
        result = agente._safe_run(**kwargs)
        # _safe_run nunca lanza excepción; el error queda en result.error
    """

    def __init__(self, temperature: float = 0.1):
        """
        Args:
            temperature: Temperatura del LLM. Usa 0.0 para tareas deterministas
                (generación de SQL), 0.1-0.3 para análisis, 0.3 para prosa creativa.
        """
        self.llm = ChatOllama(
            base_url=config.OLLAMA_BASE_URL,
            model=config.OLLAMA_MODEL,
            temperature=temperature,
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def run(self, **kwargs) -> AgentResult:
        """
        Ejecuta la lógica principal del agente.

        Subclases deben implementar este método.
        Puede lanzar excepciones; el manejo está en _safe_run().

        Returns:
            AgentResult con el resultado del agente.
        """
        ...

    def _safe_run(self, **kwargs) -> AgentResult:
        """
        Ejecuta run() con manejo de errores.

        Si run() lanza una excepción, retorna un AgentResult con error=str(e)
        en lugar de propagar la excepción. Esto permite que el pipeline
        continúe aunque un agente falle.

        El contenido del AgentResult en caso de error incluye el mensaje
        de error para que el documento Word lo refleje claramente.
        """
        try:
            return self.run(**kwargs)
        except Exception as e:
            self.logger.error(
                f"Agente {self.__class__.__name__} falló: {e}",
                exc_info=True,
            )
            return AgentResult(
                agent_name=self.__class__.__name__,
                content=f"[El agente encontró un error y no pudo completar el análisis]\n\nDetalle: {e}",
                error=str(e),
            )
