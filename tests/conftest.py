"""
conftest.py — Configuración de pytest para el proyecto Medida 83.

Mockea los módulos que requieren infraestructura externa (PostgreSQL, Ollama,
ChromaDB) para que los tests unitarios corran sin dependencias de red/BD.

Los mocks se insertan en sys.modules ANTES de que pytest importe los módulos
del proyecto, gracias al mecanismo de carga anticipada de conftest.py.

Módulos mockeados:
- db / db.postgres_client: no existe aún o requiere PostgreSQL en ejecución.
  El mock expone get_sql_database, test_connection, etc. como MagicMock.

Los módulos RAG y LangChain sí existen y se importan normalmente;
solo los instanciamos con object.__new__() en los tests para evitar
conexiones reales a Ollama o ChromaDB.
"""

import sys
from unittest.mock import MagicMock

# ── Mock db.postgres_client ────────────────────────────────────────────────
# agente_datos.py hace: from db.postgres_client import get_sql_database
# Como db/ no existe aún, mockeamos el módulo completo para que el import
# no falle al cargar agents.orquestador → agents.agente_datos.

_db_mock = MagicMock()
_db_mock.get_sql_database = MagicMock(return_value=MagicMock())
_db_mock.test_connection = MagicMock(return_value=True)
_db_mock.get_table_names = MagicMock(return_value=[])
_db_mock.get_schema_info = MagicMock(return_value="")

sys.modules.setdefault("db", MagicMock())
sys.modules.setdefault("db.postgres_client", _db_mock)
