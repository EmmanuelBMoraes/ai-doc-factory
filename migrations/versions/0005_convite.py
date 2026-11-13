"""convite: link de uso único para criar usuário (o token em claro nunca é gravado)

Revision ID: 0005_convite
Revises: 0004_lote_contrato

`token_hash` é o sha256 (hex) do token; o token só existe na resposta de POST /convites. O CHECK de vínculo é o
mesmo de `usuario`. `usuario_id` aponta para o usuário criado ao aceitar (SET NULL: apagar o usuário não apaga o
histórico do convite). Downgrade apaga a tabela e, com ela, os convites.
"""
from alembic import op

revision = "0005_convite"
down_revision = "0004_lote_contrato"
branch_labels = None
depends_on = None

# Os valores de `nivel` e `papel` precisam bater com NIVEIS_ACESSO e PAPEIS em app/config.py.
SCHEMA = r"""
CREATE TABLE convite (
    id              BIGSERIAL PRIMARY KEY,
    token_hash      CHAR(64) NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    email           TEXT NOT NULL,
    nivel           TEXT NOT NULL CONSTRAINT convite_nivel_check
                    CHECK (nivel IN ('plataforma', 'tomador', 'prestador')),
    papel           TEXT NOT NULL CONSTRAINT convite_papel_check CHECK (papel IN ('admin', 'membro')),
    tomador_id      BIGINT REFERENCES tomador(id) ON DELETE RESTRICT,
    prestador_id    BIGINT REFERENCES prestador(id) ON DELETE RESTRICT,
    criado_por      BIGINT REFERENCES usuario(id) ON DELETE SET NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em       TIMESTAMPTZ NOT NULL,
    usado_em        TIMESTAMPTZ,
    usuario_id      BIGINT REFERENCES usuario(id) ON DELETE SET NULL,
    CONSTRAINT convite_nivel_vinculo_check CHECK (
        (nivel = 'plataforma' AND tomador_id IS NULL     AND prestador_id IS NULL) OR
        (nivel = 'tomador'    AND tomador_id IS NOT NULL AND prestador_id IS NULL) OR
        (nivel = 'prestador'  AND prestador_id IS NOT NULL AND tomador_id IS NULL)
    )
);
CREATE UNIQUE INDEX convite_token_hash_uniq ON convite (token_hash);
CREATE INDEX convite_email_idx ON convite (lower(email));
CREATE INDEX convite_tomador_idx ON convite (tomador_id);
CREATE INDEX convite_prestador_idx ON convite (prestador_id);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE convite")
