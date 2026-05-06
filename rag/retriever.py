"""
rag/retriever.py — Recuperador de documentos basado en TF-IDF.

Lee archivos .txt y .pdf de un directorio, los divide en chunks y recupera
los más relevantes por similitud de coseno contra la query.

No requiere servidor de embeddings ni base de datos vectorial externa.
Usa scikit-learn (TF-IDF) y pypdf para lectura de PDFs.

Si el directorio está vacío, retrieve() devuelve "" y los agentes
usan su contexto embebido como fallback.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning("scikit-learn no disponible — RAG usará fallback de primeros chunks")

try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False
    logger.warning("pypdf no disponible — solo se leerán archivos .txt")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


class SimpleRetriever:
    """
    Recuperador TF-IDF sobre un directorio de documentos (.txt y .pdf).

    Carga y vectoriza los documentos en la primera llamada a retrieve()
    (lazy loading). Siguientes llamadas reutilizan el índice en memoria.
    """

    def __init__(self, docs_dir: Path):
        self.docs_dir = Path(docs_dir)
        self._chunks: list[str] = []
        self._vectorizer = None
        self._matrix = None
        self._loaded = False

    def retrieve(self, query: str, k: int = 3) -> str:
        """
        Devuelve los top-k chunks más relevantes para la query, concatenados.
        Retorna "" si el directorio no existe o está vacío.
        """
        self._load()
        if not self._chunks:
            return ""

        if _HAS_SKLEARN and self._matrix is not None:
            query_vec = self._vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self._matrix).flatten()
            indices = scores.argsort()[-k:][::-1]
            top = [self._chunks[i] for i in indices if scores[i] > 0.01]
        else:
            top = self._chunks[:k]

        return "\n\n---\n\n".join(top) if top else ""

    def _load(self):
        if self._loaded:
            return
        self._loaded = True

        if not self.docs_dir.exists():
            return

        raw_texts = []
        archivos = sorted(self.docs_dir.iterdir())
        docs_leidos = []
        for path in archivos:
            if path.suffix.lower() == ".pdf":
                pages = self._read_pdf(path)
                if pages:
                    raw_texts.extend(pages)
                    docs_leidos.append(f"{path.name} ({len(pages)} paginas)")
            elif path.suffix.lower() == ".txt":
                text = self._read_txt(path)
                if text:
                    raw_texts.extend(text)
                    docs_leidos.append(f"{path.name}")

        if docs_leidos:
            print(f"    Documentos leidos:")
            for d in docs_leidos:
                print(f"      * {d}")
        else:
            print(f"    Sin documentos PDF/TXT en {self.docs_dir.name}/")

        if not raw_texts:
            return

        for text in raw_texts:
            for i in range(0, max(1, len(text)), CHUNK_SIZE - CHUNK_OVERLAP):
                chunk = text[i: i + CHUNK_SIZE].strip()
                if len(chunk) > 50:
                    self._chunks.append(chunk)

        if self._chunks and _HAS_SKLEARN:
            self._vectorizer = TfidfVectorizer(max_features=8000)
            self._matrix = self._vectorizer.fit_transform(self._chunks)
            print(f"    Indice TF-IDF construido: {len(self._chunks)} chunks | vocab={self._matrix.shape[1]:,} terminos")

        logger.info(
            f"RAG cargado: {len(self._chunks)} chunks desde {self.docs_dir.name}/"
        )

    def _read_pdf(self, path: Path) -> list[str]:
        if not _HAS_PYPDF:
            return []
        try:
            reader = PdfReader(str(path))
            pages = [p.extract_text() or "" for p in reader.pages]
            return [t for t in pages if t.strip()]
        except Exception as e:
            logger.warning(f"No se pudo leer {path.name}: {e}")
            return []

    def _read_txt(self, path: Path) -> list[str]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return [text] if text.strip() else []
        except Exception as e:
            logger.warning(f"No se pudo leer {path.name}: {e}")
            return []
