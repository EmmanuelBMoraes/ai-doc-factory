from fastapi import APIRouter, Depends

from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.usuarios import actions
from app.routers.usuarios.schemas import UsuarioListadoOut

router = APIRouter(tags=["Usuários"])  # autenticada (api.py); escopo por organização na action


@router.get("/usuarios", response_model=list[UsuarioListadoOut])
def listar_usuarios(usuario: UsuarioContexto = Depends(exigir_usuario)):
    return actions.listar(usuario)
