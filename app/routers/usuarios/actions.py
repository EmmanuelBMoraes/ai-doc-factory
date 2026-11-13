import psycopg
from fastapi import HTTPException

from app import config
from app.routers.auth.actions import UsuarioContexto


def listar(usuario: UsuarioContexto) -> list[dict]:
    """Plataforma: todos. Admin de tomador/prestador: os da própria organização. Membro: 403."""
    if usuario.nivel == "plataforma":
        onde, args = "TRUE", []
    elif usuario.papel != "admin":
        raise HTTPException(403, "apenas administradores listam usuários")
    elif usuario.nivel == "tomador" and usuario.tomador_id is not None:
        onde, args = "tomador_id = %s", [usuario.tomador_id]
    elif usuario.nivel == "prestador" and usuario.prestador_id is not None:
        onde, args = "prestador_id = %s", [usuario.prestador_id]
    else:
        raise HTTPException(403, "sem permissão para listar usuários")
    with psycopg.connect(config.DATABASE_URL) as conn:
        linhas = conn.execute(f"SELECT id, nome, email, nivel, papel, ativo, criado_em FROM usuario WHERE {onde} "
                              "ORDER BY id", args).fetchall()
    return [dict(zip(("id", "nome", "email", "nivel", "papel", "ativo", "criado_em"), l)) for l in linhas]
