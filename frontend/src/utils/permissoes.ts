import type { UsuarioAtual } from '../services/api'

type Usuario = Pick<UsuarioAtual, 'nivel'> | null | undefined

/** Plataforma e prestador enviam lotes; o tomador é somente leitura. */
export const podeEnviar = (usuario: Usuario): boolean =>
  usuario?.nivel === 'plataforma' || usuario?.nivel === 'prestador'

/** Revisão, correção de tipo/campos, cancelar, reprocessar e excluir seguem a mesma regra do envio. */
export const podeEditar = (usuario: Usuario): boolean => podeEnviar(usuario)

/** Conformidade por empresa (/empresas e /conformidade) é exclusiva da plataforma. */
export const veConformidade = (usuario: Usuario): boolean => usuario?.nivel === 'plataforma'

/** Organizações (tomador, prestador, contrato) também é exclusivo da plataforma. */
export const veOrganizacoes = (usuario: Usuario): boolean => usuario?.nivel === 'plataforma'
