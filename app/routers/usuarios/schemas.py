from pydantic import BaseModel

from app.routers.comum import DataHora


class UsuarioListadoOut(BaseModel):
    id: int
    nome: str
    email: str
    nivel: str
    papel: str
    ativo: bool
    criado_em: DataHora
