import re

from app.conformidade import validar_cnpj

NOME_MAX = 200
ID_MAX = 2 ** 63 - 1  # BIGINT
_FORMATO_CNPJ = re.compile(r"^[0-9./\-\s]+$")  # dígitos e a pontuação usual; letras e outros símbolos não passam


def validar_nome(v: str, campo: str = "nome") -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{campo} não pode ser vazio")
    if len(v) > NOME_MAX:
        raise ValueError(f"{campo} excede {NOME_MAX} caracteres")
    return v


def normalizar_cnpj(v: str) -> str:
    """CNPJ com ou sem pontuação -> 14 dígitos, com os dígitos verificadores conferidos."""
    if not _FORMATO_CNPJ.match(v):
        raise ValueError("CNPJ inválido: use só dígitos (a pontuação é opcional)")
    cnpj = validar_cnpj(v)
    if cnpj is None:
        raise ValueError("CNPJ inválido: deve ter 14 dígitos e dígitos verificadores corretos")
    return cnpj


def normalizar_cnpj_opcional(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    return normalizar_cnpj(v)
