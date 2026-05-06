# Sistema Multi-Agente — Análisis de Cumplimiento Medida 83 IFT

**Institución:** Comisión Reguladora de Telecomunicaciones (CRT)  
**Dependencia:** Dirección General de Vigilancia de Regulación Asimétrica (DG-VRA)  
**Contexto académico:** Proyecto de maestría — artefacto de IA generativa aplicada a regulación de telecomunicaciones

---

## ¿Qué hace este sistema?

Analiza el cumplimiento de la **Medida Octogésima Tercera (Medida 83)** del IFT, que prohíbe al Agente Económico Preponderante (Telcel/América Móvil) contactar con fines comerciales a suscriptores que portaron su número fuera de sus redes, durante los primeros **60 días naturales** posteriores a la portabilidad.

El sistema identifica **indicadores potenciales de incumplimiento** mediante pares ida-vuelta: el mismo número telefónico porta DESDE Telcel y REGRESA a Telcel en 60 días o menos.

### Pipeline de tres agentes + evaluador

```
[AgenteDatos]         → 12 consultas SQL + estadísticos (HHI, regresión lineal, proyección)
        ↓
[AgenteRegulatorio]   → Secciones 1-2: marco jurídico, recuperado con RAG sobre docs normativos
        ↓
[AgenteRedactor]      → Secciones 3-9: narrativa institucional DG-VRA/CRT (2 llamadas LLM)
        ↓
[LLM Judge]           → Evaluación automática de calidad (5 dimensiones, puntaje 0-10)
        ↓
[Word Generator]      → Informe .docx con tablas de datos y 4 gráficas matplotlib
```

El documento Word generado incluye portada institucional con folio, 9 secciones de análisis regulatorio, tablas de datos, 4 gráficas, y 3 escenarios de propuesta de resolución (Escenario A: modificar / B: mantener / C: eliminar la medida) más la recomendación institucional DG-VRA.

---

## Prerrequisitos

| Requisito | Versión mínima | Notas |
|-----------|---------------|-------|
| Python | 3.10+ | Probado en 3.12 y 3.14 |
| pip | cualquiera | Incluido con Python |
| Cuenta Groq | gratuita | Sin tarjeta de crédito requerida |

> **Groq es completamente gratuito.** Registra una cuenta en console.groq.com, genera una API key, y listo. El modelo `llama-3.1-8b-instant` está disponible sin costo.

---

## Instalación en 3 pasos

### Paso 1 — Instalar dependencias

```bash
pip install -r requirements.txt
```

Si usas entorno virtual (recomendado para evitar conflictos):

```bash
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Paso 2 — Configurar API key

Copia el archivo de ejemplo y edítalo con cualquier editor de texto:

```bash
# Windows:
copy .env.example .env

# macOS/Linux:
cp .env.example .env
```

Abre `.env` y reemplaza el valor placeholder:

```env
GROQ_API_KEY=gsk_tu_api_key_aqui
```

Para obtener tu API key gratuita:
1. Ve a https://console.groq.com
2. Crea una cuenta (sin tarjeta de crédito)
3. Ve a **API Keys → Create API Key**
4. Copia la key y pégala en `.env`

### Paso 3 — Ejecutar

```bash
python main.py
```

La primera ejecución genera automáticamente la base de datos SQLite con ~55,000 registros sintéticos de portabilidad. El informe Word se guarda en la carpeta `docs/`.

---

## Modos de ejecución

```bash
# Pipeline completo (recomendado para primera prueba — incluye evaluación de calidad)
python main.py

# Sin evaluación LLM Judge (más rápido, ~40% menos tiempo)
python main.py --no-judge

# Pregunta personalizada de análisis
python main.py --question "Analiza la concentración de mercado en el período enero-junio 2024"

# Combinaciones válidas:
python main.py --no-judge --question "Pregunta personalizada"
```

### Escenarios de prueba (`--reset-db`)

El flag `--reset-db` acepta una semilla (1, 2 o 3) que genera datos estadísticamente distintos, produciendo informes y scores del Judge diferentes en cada caso. Útil para verificar que el sistema responde correctamente a diferentes condiciones de mercado.

```bash
# Escenario 1 — Moderado (baseline)
# ~28% tasa de indicadores | HHI moderado | retornos distribuidos entre días 1-60
python main.py --reset-db 1

# Escenario 2 — Alta concentración
# ~42% tasa de indicadores | HHI alto | retornos muy rápidos (mayoría en días 1-14)
# AT&T como operador receptor dominante → mayor preocupación regulatoria
python main.py --reset-db 2

# Escenario 3 — Baja concentración
# ~14% tasa de indicadores | HHI bajo | retornos tardíos (mayoría en días 31-60)
# Mercado distribuido entre operadores → menor presión regulatoria
python main.py --reset-db 3
```

> **Para el evaluador:** correr los tres escenarios produce tres informes Word distintos en `output/documentos/`, con diferente análisis estadístico, diferente HHI, diferente narrativa del LLM y diferente score del Judge. Esto demuestra que el sistema no es estático: responde a los datos que recibe.

---

## Estructura del proyecto

```
medida_83 - artefacto/
│
├── main.py                    # Punto de entrada — orquesta el pipeline completo
├── config.py                  # Configuración global (rutas, modelos, constantes institucionales)
├── requirements.txt           # Dependencias Python (8 paquetes)
├── .env.example               # Plantilla de variables de entorno
├── .env                       # Tu API key (NO subir a git — ya está en .gitignore)
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
│   ├── rag_builder.py         # Indexa PDFs normativos con TF-IDF (sin servidor externo)
│   └── retriever.py           # Recupera fragmentos relevantes (k=4 por consulta)
│
├── utils/
│   ├── llm_client.py          # Cliente Groq con reintento automático por rate limit
│   ├── context.py             # RunContext y AgentResult (estado compartido del pipeline)
│   └── word_generator.py      # Genera el .docx con tablas, gráficas y portada institucional
│
├── data/
│   ├── portaciones.db         # Base SQLite (se genera automáticamente en primera ejecución)
│   └── docs/regulatorio/      # Coloca aquí PDFs normativos para el RAG (opcional)
│
├── docs/                      # Informes Word generados (salida del sistema)
└── logs/                      # Logs de cada ejecución con timestamp
```

---

## Arquitectura y decisiones de diseño

### Roles de cada agente

| Agente | Fuente de conocimiento | Salida |
|--------|----------------------|--------|
| AgenteDatos | SQLite con 12 consultas SQL parametrizadas | Cifras brutas, HHI, regresión lineal, proyección 3 meses |
| AgenteRegulatorio | RAG TF-IDF sobre PDFs + marco normativo embebido | Secciones 1-2: antecedentes jurídicos y facultades DG-VRA |
| AgenteRedactor | Outputs de los dos agentes anteriores | Secciones 3-9: análisis completo con 3 escenarios de resolución |

### Modelo LLM

- **Proveedor:** Groq (inferencia ultrarrápida en nube)
- **Modelo:** `llama-3.1-8b-instant`
- **Por qué Groq:** Latencia <2s por llamada, plan gratuito generoso, sin necesidad de GPU local ni Ollama

### Formato de comunicación entre agentes

Los agentes NO usan JSON para la salida del LLM (los modelos pequeños rompen el JSON con comillas internas). En su lugar usan marcadores de sección en texto plano:

```
===S1===
Texto de la sección 1 sin necesidad de escapar nada...

===S2===
Texto de la sección 2...
```

El `word_generator.py` parsea este formato con `re.split(r'===([A-Z0-9_]+)===', content)`.

### Base de datos sintética

El script `db/init_db.py` genera una réplica sintética del modelo de datos de portabilidad del IFT:
- **~50,000** eventos de portación (período 2023-2024)
- **~40%** portaciones con Telcel como operador donador (proporción real aproximada de mercado)
- **~28%** de esas portaciones regresan a Telcel en ≤60 días → indicadores potenciales
- Distribución temporal realista por rangos de días: 1-7, 8-14, 15-21, 22-30, 31-45, 46-60

---

## Documento Word generado

El informe sigue el formato institucional DG-VRA/CRT con folio `DG-VRA-YYYYMMDD-HHMM`:

| # | Sección | Contenido |
|---|---------|-----------|
| — | Portada | Folio, fecha, dependencia, clasificación de reserva |
| — | Aviso HITL | Advertencia obligatoria: validación humana requerida antes de efectos regulatorios |
| 1 | Antecedentes y Marco Jurídico | Origen normativo de la Medida 83, contexto de preponderancia, limitaciones del análisis |
| 2 | Facultades de la DG-VRA | Fundamento reglamentario, competencias de fiscalización |
| 3 | Objeto y Metodología | Qué se mide, por qué son indicadores indirectos, necesidad de validación humana |
| 4 | Calidad de Datos | Completitud de la base, nulos, robustez del análisis |
| 5 | Concentración de Mercado | HHI calculado, clasificación (comp./moderado/alta), distribución por operador |
| 6 | Análisis de Portabilidad | Universo regulatorio, indicadores por operador, distribución por rango de días, tendencia mensual |
| 7 | Análisis Estadístico | Regresión lineal, R², p-valor, proyección 3 meses con intervalo de confianza |
| 8 | Análisis de Impacto Regulatorio | Metodología OCDE: problema, objetivos, impactos, balance costo-beneficio |
| 9 | Conclusiones y Propuesta | Escenario A (modificar) / B (mantener) / C (eliminar) + Recomendación DG-VRA |

**4 gráficas matplotlib embebidas:**
- Gráfica 1: Tendencia mensual de indicadores potenciales + línea de regresión
- Gráfica 2: Distribución por rango de días de retorno (barras verticales)
- Gráfica 3: Indicadores por operador receptor (barras horizontales)
- Gráfica 4: Proyección 3 meses con banda de intervalo de confianza (±15%)

---

## LLM-as-a-Judge

El módulo `judge/llm_judge.py` evalúa automáticamente la calidad del informe generado usando el mismo LLM a **temperatura=0** (respuestas deterministas):

| Dimensión | Peso | Descripción |
|-----------|------|-------------|
| Precisión técnica | 25% | ¿Los datos citados corresponden a los calculados por AgenteDatos? |
| Rigor jurídico | 25% | ¿Se usa lenguaje epistémico adecuado ("podría indicar", "sugiere")? |
| Completitud | 20% | ¿Están presentes todas las secciones requeridas? |
| Coherencia | 15% | ¿Hay contradicciones entre secciones? |
| Claridad | 15% | ¿La prosa es inteligible para un regulador no técnico? |

Puntaje ≥7.0 = **APROBADO**. El resultado aparece en la consola al finalizar y queda registrado en el log de la ejecución.

---

## Características opcionales

### RAG con documentos normativos propios

Coloca archivos PDF en `data/docs/regulatorio/` (resoluciones IFT, disposiciones LFTR, reglas de portabilidad, etc.) y ejecuta:

```bash
python rag/rag_builder.py
```

El AgenteRegulatorio recuperará automáticamente los 4 fragmentos más relevantes para cada consulta usando TF-IDF. Si la carpeta está vacía, funciona con el marco normativo embebido en el código.

### Plantilla Word personalizada

Si tienes una plantilla `.docx` con estilos institucionales definidos, indícala en `.env`:

```env
WORD_TEMPLATE=ruta/a/tu/plantilla.docx
```

### Docker (opcional)

```bash
docker build -t medida83 .
docker run -e GROQ_API_KEY=gsk_tu_key medida83
```

---

## Solución de problemas frecuentes

| Error en consola | Causa probable | Solución |
|-----------------|---------------|----------|
| `ModuleNotFoundError: groq` | Dependencias no instaladas en el Python que usa VS Code | Ejecuta `python -c "import groq"` en la terminal del proyecto. Si falla, `pip install -r requirements.txt` con ese mismo Python |
| `GROQ_API_KEY not set` | Archivo `.env` faltante o con el placeholder sin reemplazar | Verifica que `.env` exista (no solo `.env.example`) y tenga tu key real |
| `rate_limit_exceeded` | Límite de tokens por minuto del plan gratuito Groq | El cliente reintenta automáticamente hasta 3 veces con espera de 60s; si persiste, espera 1 minuto y vuelve a ejecutar |
| Base de datos vacía o inexistente | Primera ejecución o BD corrupta | Ejecuta `python main.py --reset-db` |
| Secciones faltantes en el Word | El LLM truncó la respuesta por límite de tokens | Normal ocasionalmente en modelos pequeños; el sistema usa texto de respaldo por sección. Vuelve a ejecutar |
| `matplotlib` no encontrado | Dependencia no instalada | `pip install matplotlib numpy` |
| El Word tiene texto raro entre comillas | Versión antigua del código (bug corregido) | Asegúrate de tener la versión actual de `agents/agente_redactor.py` y `utils/word_generator.py` |

### Verificar que todo está instalado correctamente

```bash
python -c "import groq, sklearn, docx, matplotlib, numpy, dotenv; print('Todas las dependencias OK')"
```

---

## Variables de entorno (`.env`)

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `GROQ_API_KEY` | **Sí** | — | API key de Groq (gratuita en console.groq.com) |
| `LLM_PROVIDER` | No | `groq` | Proveedor LLM: `groq` o `huggingface` |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` | Modelo Groq a usar |
| `HF_TOKEN` | Solo si HF | — | Token de HuggingFace (alternativa a Groq) |
| `HF_MODEL` | No | `mistralai/Mistral-7B-Instruct-v0.2` | Modelo HuggingFace |
| `WORD_TEMPLATE` | No | — | Ruta a plantilla .docx personalizada |

---

## Dependencias (requirements.txt)

| Paquete | Versión mín. | Uso en el sistema |
|---------|-------------|-------------------|
| `groq` | 0.9.0 | Cliente de la API Groq para llamadas LLM |
| `python-docx` | 1.0.0 | Generación del documento Word institucional |
| `scikit-learn` | 1.3.0 | TF-IDF vectorizer para el sistema RAG |
| `matplotlib` | 3.7.0 | 4 gráficas embebidas en el documento Word |
| `numpy` | 1.24.0 | Operaciones numéricas para regresión y proyección |
| `python-dotenv` | 1.0.0 | Carga de variables de entorno desde `.env` |
| `pypdf` | 4.0.0 | Extracción de texto de PDFs normativos para RAG |
| `huggingface_hub` | 0.23.0 | Soporte alternativo de modelos HuggingFace |

---

## Conceptos académicos demostrados

Este artefacto implementa los siguientes conceptos de IA aplicada y LLMOps:

| Concepto | Implementación |
|----------|---------------|
| **Sistemas multi-agente** | 3 agentes especializados con estado compartido via `RunContext` |
| **RAG (Retrieval-Augmented Generation)** | TF-IDF sobre corpus jurídico, sin embeddings externos ni vector DB |
| **LLM-as-a-Judge** | Evaluación automática de calidad con LLM a temperatura=0 |
| **Prompt engineering** | Marcadores `===KEY===` para evitar fallos de parseo JSON en modelos pequeños |
| **LLMOps básico** | Logging estructurado por timestamp, reintentos automáticos, trazabilidad completa |
| **Análisis estadístico automatizado** | Regresión lineal pura Python (sin scipy), HHI de mercado, proyección con IC ±15% |
| **Análisis de Impacto Regulatorio** | Sección 8 implementa metodología OCDE: problema → objetivos → impactos → costo-beneficio |

> El sistema usa **únicamente datos sintéticos** generados programáticamente mediante `db/init_db.py`. No contiene datos reales de portabilidad del IFT ni información confidencial.
