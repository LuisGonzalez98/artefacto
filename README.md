# Sistema Multi-Agente para Análisis de Cumplimiento Regulatorio en Telecomunicaciones

**Proyecto estrictamente académico** — Este sistema utiliza exclusivamente **datos sintéticos generados programáticamente**. No contiene información real de ningún regulador, operador ni usuario. Su propósito es explorar la factibilidad de aplicar IA generativa y sistemas multi-agente en contextos de supervisión regulatoria de telecomunicaciones.

---

## Descripción

Este artefacto simula el flujo de análisis que podría realizar el área de cumplimiento y supervisión de un regulador de telecomunicaciones al vigilar el cumplimiento de una medida asimétrica dirigida al operador dominante del mercado.

La medida analizada prohíbe al operador preponderante contactar con fines comerciales a suscriptores que portaron su número fuera de su red, durante los primeros 60 días naturales posteriores a la portabilidad. El sistema detecta **indicadores potenciales de incumplimiento** mediante pares ida-vuelta: el mismo número porta DESDE el operador dominante y regresa en 60 días o menos.

### Pipeline de tres agentes + evaluador

```
[AgenteDatos]       → 12 consultas SQL + estadísticos (HHI, regresión lineal, proyección)
        ↓
[AgenteRegulatorio] → Secciones 1-2: marco jurídico con RAG sobre documentos normativos
        ↓
[AgenteRedactor]    → Secciones 3-9: narrativa institucional (2 llamadas LLM)
        ↓
[LLM Judge]         → Evaluación automática de calidad (5 dimensiones, puntaje 0-10)
        ↓
[Word Generator]    → Informe .docx con tablas de datos y 4 gráficas matplotlib
```

El documento Word generado incluye portada, 9 secciones de análisis, tablas, 4 gráficas y 3 escenarios de propuesta de resolución (modificar / mantener / eliminar la medida) más una recomendación institucional.

---

## Naturaleza académica del proyecto

Este sistema es un prototipo de investigación con los siguientes alcances y limitaciones:

- **Datos 100% sintéticos** — La base de datos se genera automáticamente con ~55,000 registros ficticios de portabilidad. No se usan datos reales de ninguna fuente.
- **Sin efectos regulatorios** — Los análisis generados no tienen validez jurídica ni administrativa. Cualquier uso real requeriría validación humana por personal técnico-jurídico calificado.
- **Factibilidad, no producción** — El objetivo es demostrar que la arquitectura multi-agente puede producir análisis regulatorio coherente a partir de datos estructurados, no reemplazar procesos institucionales reales.

---

## Prerrequisitos

| Requisito | Versión mínima | Notas |
|-----------|---------------|-------|
| Python | 3.10+ | Probado en 3.12 y 3.14 |
| pip | cualquiera | Incluido con Python |
| Cuenta Groq | gratuita | Sin tarjeta de crédito requerida |

> **Groq es completamente gratuito.** Registra una cuenta en console.groq.com, genera una API key y listo. El modelo `llama-3.1-8b-instant` está disponible sin costo.

---

## Instalación en 3 pasos

### Paso 1 — Instalar dependencias

```powershell
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

### Paso 2 — Configurar API key

```powershell
copy .env.example .env
```

Abre `.env` y reemplaza el placeholder:

```env
GROQ_API_KEY=gsk_tu_api_key_aqui
```

Obtén tu key gratuita en https://console.groq.com → API Keys → Create API Key.

### Paso 3 — Ejecutar

```powershell
python main.py
```

La primera ejecución genera automáticamente la base de datos SQLite con ~55,000 registros sintéticos. El informe Word se guarda en `output/documentos/`.

---

## Modos de ejecución

```powershell
# Pipeline completo con evaluación de calidad
python main.py

# Sin evaluación LLM Judge (más rápido)
python main.py --no-judge

# Pregunta personalizada
python main.py --question "Analiza la concentración de mercado en el período enero-junio 2024"
```

### Escenarios de prueba

El flag `--reset-db` regenera la base de datos con datos estadísticamente distintos. Útil para verificar que el sistema responde correctamente a diferentes condiciones de mercado.

```powershell
# Escenario 1 — Moderado (baseline)
# ~28% tasa de indicadores | HHI moderado | retornos distribuidos entre días 1-60
python main.py --reset-db 1

# Escenario 2 — Alta concentración
# ~42% tasa de indicadores | HHI alto | retornos muy rápidos (mayoría en días 1-14)
python main.py --reset-db 2

# Escenario 3 — Baja concentración
# ~14% tasa de indicadores | HHI bajo | retornos tardíos (mayoría en días 31-60)
python main.py --reset-db 3
```

> Correr los tres escenarios produce tres informes Word distintos con diferente análisis estadístico, diferente HHI, diferente narrativa del LLM y diferente score del Judge — demostrando que el sistema responde dinámicamente a los datos que recibe.

---

## Estructura del proyecto

```
medida_83 - artefacto/
│
├── main.py                    # Punto de entrada — orquesta el pipeline completo
├── config.py                  # Configuración global (rutas, modelos, constantes)
├── requirements.txt           # Dependencias Python
├── .env.example               # Plantilla de variables de entorno (sin keys reales)
│
├── agents/
│   ├── agente_datos.py        # Agente 1: 12 consultas SQL + HHI + regresión + proyección
│   ├── agente_regulatorio.py  # Agente 2: Marco jurídico con RAG sobre docs normativos
│   └── agente_redactor.py     # Agente 3: Narrativa institucional Secciones 3-9
│
├── db/
│   └── init_db.py             # Generador de base SQLite con ~55,000 registros sintéticos
│
├── judge/
│   └── llm_judge.py           # Evaluador LLM-as-a-Judge (5 dimensiones, temperatura=0)
│
├── rag/
│   ├── rag_builder.py         # Indexa PDFs normativos con TF-IDF
│   └── retriever.py           # Recupera fragmentos relevantes (k=4 por consulta)
│
├── utils/
│   ├── llm_client.py          # Cliente Groq con reintento automático por rate limit
│   ├── context.py             # RunContext y AgentResult (estado compartido del pipeline)
│   ├── word_generator.py      # Genera el .docx con tablas, gráficas y portada
│   └── excel_logger.py        # Registro acumulativo de evaluaciones en CSV y XLSX
│
├── data/
│   ├── portaciones.db         # Base SQLite (generada automáticamente)
│   └── docs/regulatorio/      # PDFs normativos para el RAG (opcional)
│
├── output/
│   ├── documentos/            # Informes Word generados
│   ├── LLM_as_a_judge.csv     # Registro acumulativo de evaluaciones
│   └── LLM_as_a_judge.xlsx    # Mismo registro en formato Excel formateado
└── logs/                      # Logs de cada ejecución con timestamp
```

---

## Documento Word generado

| # | Sección | Contenido |
|---|---------|-----------|
| — | Portada | Folio, fecha, área, clasificación |
| — | Aviso | Advertencia: análisis preliminar, requiere validación humana |
| 1 | Antecedentes y Marco Jurídico | Origen normativo de la medida analizada, contexto de mercado |
| 2 | Facultades del Área | Fundamento reglamentario y competencias de supervisión |
| 3 | Objeto y Metodología | Qué se mide, por qué son indicadores indirectos, limitaciones |
| 4 | Calidad de Datos | Completitud de la base, nulos, robustez del análisis |
| 5 | Concentración de Mercado | HHI calculado, clasificación, distribución por operador |
| 6 | Análisis de Portabilidad | Universo regulatorio, indicadores por operador, tendencia mensual |
| 7 | Análisis Estadístico | Regresión lineal, R², p-valor, proyección 3 meses con IC |
| 8 | Análisis de Impacto Regulatorio | Metodología OCDE: problema, objetivos, impactos, costo-beneficio |
| 9 | Conclusiones y Propuesta | Escenario A (modificar) / B (mantener) / C (eliminar) + Recomendación |

**4 gráficas embebidas:**
- Gráfica 1: Tendencia mensual de indicadores + línea de regresión
- Gráfica 2: Distribución por rango de días de retorno
- Gráfica 3: Indicadores por operador receptor
- Gráfica 4: Proyección 3 meses con intervalo de confianza (±15%)

---

## LLM-as-a-Judge

Evalúa automáticamente la calidad del informe en 5 dimensiones con temperatura=0 (determinista):

| Dimensión | Peso | Descripción |
|-----------|------|-------------|
| Precisión técnica | 25% | ¿Los datos citados son correctos? |
| Rigor jurídico | 25% | ¿Se usa lenguaje epistémico adecuado? |
| Completitud | 20% | ¿Están todas las secciones requeridas? |
| Coherencia | 15% | ¿Hay contradicciones entre secciones? |
| Claridad | 15% | ¿La prosa es inteligible? |

Puntaje ≥7.0 = **APROBADO**. Cada corrida registra una fila en `output/LLM_as_a_judge.xlsx`.

---

## Solución de problemas frecuentes

| Error | Causa | Solución |
|-------|-------|----------|
| `ModuleNotFoundError: groq` | Dependencias no instaladas en el venv activo | Activa el venv y corre `pip install -r requirements.txt` |
| `GROQ_API_KEY not set` | Archivo `.env` faltante o sin key real | Copia `.env.example` como `.env` y agrega tu key |
| `rate_limit_exceeded` | Límite del plan gratuito Groq | El cliente reintenta automáticamente; espera 60s si persiste |
| Base de datos vacía | Primera ejecución o BD corrupta | Corre `python main.py --reset-db 1` |
| `matplotlib` no encontrado | Dependencia faltante | `pip install matplotlib numpy` |

### Verificar instalación

```powershell
python -c "import groq, sklearn, docx, matplotlib, numpy, dotenv, openpyxl; print('OK')"
```

---

## Conceptos académicos demostrados

| Concepto | Implementación |
|----------|---------------|
| **Sistemas multi-agente** | 3 agentes especializados con estado compartido via `RunContext` |
| **RAG** | TF-IDF sobre corpus jurídico, sin embeddings externos ni vector DB |
| **LLM-as-a-Judge** | Evaluación automática con LLM a temperatura=0 |
| **Prompt engineering** | Marcadores `===KEY===` para evitar fallos de parseo JSON en modelos pequeños |
| **LLMOps básico** | Logging por timestamp, reintentos automáticos, registro acumulativo de evaluaciones |
| **Análisis estadístico** | Regresión lineal pura Python, HHI de mercado, proyección con IC ±15% |
| **Análisis de Impacto Regulatorio** | Sección 8 implementa metodología OCDE completa |
