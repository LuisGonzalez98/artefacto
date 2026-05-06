from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentResult:
    agent_name: str
    content: str
    succeeded: bool
    error: str = ""
    metadata: dict = field(default_factory=dict)  # datos estructurados (stats, cifras clave)


@dataclass
class RunContext:
    question: str
    run_timestamp: datetime = field(default_factory=datetime.now)
    datos_result: AgentResult = None
    regulatorio_result: AgentResult = None
    redactor_result: AgentResult = None
    judge_result: dict = None
    agent_timings: dict = field(default_factory=dict)

    @property
    def all_agents_succeeded(self) -> bool:
        results = [self.datos_result, self.regulatorio_result, self.redactor_result]
        return all(r is not None and r.succeeded for r in results)

    @property
    def agents_with_errors(self) -> list:
        mapping = {
            "AgenteDatos": self.datos_result,
            "AgenteRegulatorio": self.regulatorio_result,
            "AgenteRedactor": self.redactor_result,
        }
        return [name for name, r in mapping.items() if r and not r.succeeded]
