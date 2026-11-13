"""lote pertence a um contrato (opcional); a tabela antiga `empresa` e `lote.empresa_id` são removidas

Revision ID: 0004_lote_contrato
Revises: 0003_nome_padronizado_documento

Upgrade:
- `lote.contrato_id` (NULL = lote sem contrato: os que já existiam e os que a plataforma enviar sem contrato;
  só a plataforma os enxerga). Nenhum tomador, prestador ou contrato é criado para os lotes antigos.
- A unicidade do arquivo deixa de ser global: `lote_sha256_key` (UNIQUE em sha256) dá lugar a dois índices únicos
  parciais, um por contrato e outro para os lotes sem contrato. O mesmo arquivo pode gerar um lote por contrato.
- Remove `lote.empresa_id` (e o índice) e a tabela `empresa`. OS DADOS DE `empresa` (nomes e vínculos com lotes)
  SÃO PERDIDOS.

Downgrade:
- Recria `empresa` VAZIA e `lote.empresa_id` NULO; os dados antigos de `empresa` NÃO são recuperados.
- Restaura o UNIQUE de `sha256` e remove `contrato_id`. Falha, com mensagem, se existirem lotes com o mesmo
  sha256 (em contratos diferentes, ou com e sem contrato): nenhum lote é apagado; resolva à mão e repita.
"""
from alembic import op

revision = "0004_lote_contrato"
down_revision = "0003_nome_padronizado_documento"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE lote ADD COLUMN contrato_id BIGINT REFERENCES contrato(id) ON DELETE RESTRICT;
CREATE INDEX lote_contrato_idx ON lote (contrato_id);

ALTER TABLE lote DROP CONSTRAINT lote_sha256_key;
CREATE UNIQUE INDEX lote_contrato_sha256_uniq ON lote (contrato_id, sha256) WHERE contrato_id IS NOT NULL;
CREATE UNIQUE INDEX lote_sem_contrato_sha256_uniq ON lote (sha256) WHERE contrato_id IS NULL;

DROP INDEX lote_empresa_idx;
ALTER TABLE lote DROP COLUMN empresa_id;
DROP TABLE empresa;
"""

# O driver trata % como marcador de parâmetro: o do RAISE vai dobrado (%%).
DOWNGRADE = r"""
DO $$
DECLARE duplicados bigint;
BEGIN
    SELECT count(*) INTO duplicados
      FROM (SELECT sha256 FROM lote GROUP BY sha256 HAVING count(*) > 1) d;
    IF duplicados > 0 THEN
        RAISE EXCEPTION 'downgrade impossível: %% arquivo(s) (sha256) com mais de um lote (contratos diferentes, ou '
                        'com e sem contrato); apague ou una esses lotes à mão antes de voltar', duplicados;
    END IF;
END $$;

DROP INDEX lote_contrato_sha256_uniq;
DROP INDEX lote_sem_contrato_sha256_uniq;
DROP INDEX lote_contrato_idx;
ALTER TABLE lote DROP COLUMN contrato_id;
ALTER TABLE lote ADD CONSTRAINT lote_sha256_key UNIQUE (sha256);

CREATE TABLE empresa (
    id              BIGSERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX empresa_nome_uniq ON empresa (lower(btrim(nome)));
ALTER TABLE lote ADD COLUMN empresa_id BIGINT REFERENCES empresa(id) ON DELETE SET NULL;
CREATE INDEX lote_empresa_idx ON lote (empresa_id);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
