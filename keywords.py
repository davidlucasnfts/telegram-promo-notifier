"""
Lógica pura de filtro de palavras-chave.

Sem dependências de rede, Telegram ou variáveis de ambiente — testável de forma
unitária e reutilizável em outros contextos.
"""

import re
import unicodedata
from pathlib import Path

DEFAULT_KEYWORDS_FILE = Path("keywords.txt")


def normalize(text: str) -> str:
    """Minusculas, sem acentos, espaços repetidos colapsados e bordas limpas."""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", no_accents).lower().strip()


def load_keywords(path: Path | None = None) -> list[str]:
    """Carrega palavras-chave de um arquivo, ignorando comentários e linhas vazias."""
    target = path or DEFAULT_KEYWORDS_FILE
    if not target.exists():
        return []
    return [
        line.strip()
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def save_keywords(keywords: list[str], path: Path | None = None) -> None:
    """Salva palavras-chave ordenadas e sem duplicatas (case/acento insensitivo)."""
    target = path or DEFAULT_KEYWORDS_FILE
    seen: set[str] = set()
    cleaned: list[str] = []
    for kw in keywords:
        key = normalize(kw)
        if key and key not in seen:
            seen.add(key)
            cleaned.append(kw)
    cleaned.sort(key=str.lower)
    target.write_text("\n".join(cleaned) + "\n", encoding="utf-8")


def _kw_pattern(keyword: str) -> "re.Pattern[str]":
    """
    Regex da palavra-chave: ignora acento/case, espaços e hífens entre as
    partes ('air fryer' casa com 'airfryer' e 'air-fryer') e exige limites de
    palavra ('ssd' não casa com 'ssdex').
    """
    parts = [re.escape(p) for p in normalize(keyword).split()]
    return re.compile(r"(?<!\w)" + r"[\s-]*".join(parts) + r"(?!\w)")


def find_matches(text: str, keywords: list[str]) -> list[str]:
    """Retorna as palavras-chave encontradas no texto (ignora acentos/case)."""
    haystack = normalize(text)
    return [kw for kw in keywords if _kw_pattern(kw).search(haystack)]
