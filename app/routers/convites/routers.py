from fastapi import APIRouter, Depends

from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.auth.schemas import TokenOut
from app.routers.convites import actions
from app.routers.convites.schemas import (
    AceiteIn, ConviteCriadoOut, ConviteOut, ConvitePublicoOut, NovoConvite)

router = APIRouter(tags=["Convites"])  # autenticada (api.py): quem pode convidar é decidido por pode_convidar
router_plataforma = APIRouter(tags=["Convites"])  # só plataforma (api.py)
router_publico = APIRouter(tags=["Convites"])  # sem login: o token é a credencial


@router.post("/convites", status_code=201, response_model=ConviteCriadoOut)
def criar_convite(corpo: NovoConvite, usuario: UsuarioContexto = Depends(exigir_usuario)):
    """O token vem só nesta resposta; o banco guarda apenas o hash. Quem convidou repassa o link."""
    return actions.criar(corpo, usuario)


@router_plataforma.get("/convites", response_model=list[ConviteOut])
def listar_convites():
    return actions.listar()


@router_publico.get("/convites/{token}", response_model=ConvitePublicoOut)
def consultar_convite(token: str):
    return actions.consultar(token)


@router_publico.post("/convites/{token}/aceitar", response_model=TokenOut)
def aceitar_convite(token: str, corpo: AceiteIn):
    return actions.aceitar(token, corpo)
