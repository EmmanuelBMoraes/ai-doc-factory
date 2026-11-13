from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.routers import r  # noqa: F401  (reexportado: conexão Redis compartilhada)
from app.escopo import acesso_a_dados
from app.routers.auth.actions import exigir_plataforma, exigir_usuario
from app.routers.auth.routers import router as auth
from app.routers.busca.routers import router as busca
from app.routers.documentos.routers import router as documentos
from app.routers.empresas.routers import router as empresas
from app.routers.lotes.routers import router as lotes
from app.routers.organizacoes.routers import router as organizacoes
from app.routers.organizacoes.routers import router_leitura as contratos_leitura
from app.routers.revisao.routers import router as revisao
from app.routers.saude.routers import router as saude
from app.routers.tipos.routers import router as tipos

app = FastAPI(title="Document AI Factory")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Abertas: /health (healthcheck do compose) e /auth/login. Todo o resto exige token.
# /auth/me se protege sozinha (qualquer usuário autenticado). Matriz de acesso (app/escopo.py):
#   - lotes, busca, documentos, revisao, GET /contratos: qualquer nível, filtrado pelo escopo; tomador só lê;
#   - tipos: qualquer usuário logado;
#   - empresas (conformidade) e criação de tomador/prestador/contrato: só plataforma.
# Router novo SEM dependência fica aberto: a varredura de tests/test_autenticacao.py e tests/test_isolamento.py cobra isso.
app.include_router(saude)
app.include_router(auth)
for router in (lotes, busca, documentos, revisao, contratos_leitura):
    app.include_router(router, dependencies=[Depends(acesso_a_dados)])
app.include_router(tipos, dependencies=[Depends(exigir_usuario)])
for router in (empresas, organizacoes):
    app.include_router(router, dependencies=[Depends(exigir_plataforma)])
