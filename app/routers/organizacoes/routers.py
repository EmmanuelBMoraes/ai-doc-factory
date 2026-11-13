from typing import Annotated

from fastapi import APIRouter, Query

from app.routers.organizacoes import actions
from app.routers.organizacoes.schemas import (
    ContratoOut, IdBanco, NovoContrato, NovoPrestador, NovoTomador, PrestadorOut, TomadorOut)

router = APIRouter(tags=["Organizações"])


@router.post("/tomadores", status_code=201, response_model=TomadorOut)
def criar_tomador(corpo: NovoTomador):
    return actions.criar_tomador(corpo)


@router.get("/tomadores", response_model=list[TomadorOut])
def listar_tomadores():
    return actions.listar_tomadores()


@router.post("/prestadores", status_code=201, response_model=PrestadorOut)
def criar_prestador(corpo: NovoPrestador):
    return actions.criar_prestador(corpo)


@router.get("/prestadores", response_model=list[PrestadorOut])
def listar_prestadores():
    return actions.listar_prestadores()


@router.post("/contratos", status_code=201, response_model=ContratoOut)
def criar_contrato(corpo: NovoContrato):
    return actions.criar_contrato(corpo)


@router.get("/contratos", response_model=list[ContratoOut])
def listar_contratos(tomador_id: Annotated[IdBanco | None, Query()] = None,
                     prestador_id: Annotated[IdBanco | None, Query()] = None):
    """Filtros opcionais por tomador e por prestador."""
    return actions.listar_contratos(tomador_id, prestador_id)
