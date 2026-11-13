from typing import Literal

from pydantic import BaseModel, field_validator

from app.routers.comum import DataHora
from app.routers.convites.schemas import validar_email
from app.routers.organizacoes import validations
from app.routers.organizacoes.schemas import IdBanco


class NovaTerceirizada(BaseModel):
    cnpj: str
    razao_social: str
    email: str  # de quem receberá o convite de administrador da terceirizada (se ela ainda não tiver acesso)
    tomador_id: IdBanco | None = None  # só a plataforma informa; o admin do tomador usa o próprio

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        return validations.normalizar_cnpj(v)

    @field_validator("razao_social")
    @classmethod
    def _razao_social(cls, v: str) -> str:
        return validations.validar_nome(v, "razao_social")

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validar_email(v)


class ContratoCriadoOut(BaseModel):
    id: int
    ativo: bool


class PrestadorCadastradoOut(BaseModel):
    id: int
    cnpj: str
    razao_social: str  # a já cadastrada, quando o CNPJ existia


class ConviteTerceirizadaOut(BaseModel):
    id: int
    email: str
    expira_em: DataHora
    token: str  # só aparece nesta resposta


class TerceirizadaOut(BaseModel):
    contrato: ContratoCriadoOut
    prestador: PrestadorCadastradoOut
    acesso: Literal["convite_criado", "convite_pendente", "ja_tem_acesso"]
    convite: ConviteTerceirizadaOut | None = None
