import React, { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { apiService, type Contrato, type TerceirizadaCadastrada } from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'
import { ESTADO_ACESSO } from '../utils/convites'
import { BTN, BTN_SEC, CARD, ErroBox, INPUT, LABEL, Selo, TD, TH } from '../components/formUi'
import { ConviteLink } from '../components/ConviteLink'

interface TerceirizadasPageProps {
  onBack: () => void
}

interface LinkGerado {
  token: string
  expiraEm: string
  titulo: string
}

const TerceirizadasPage: React.FC<TerceirizadasPageProps> = ({ onBack }) => {
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [cnpj, setCnpj] = useState('')
  const [razao, setRazao] = useState('')
  const [email, setEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<TerceirizadaCadastrada | null>(null)

  const [reenviando, setReenviando] = useState<number | null>(null)
  const [emailReenvio, setEmailReenvio] = useState('')
  const [reenvioError, setReenvioError] = useState<string | null>(null)
  const [enviandoConvite, setEnviandoConvite] = useState(false)
  const [linkReenvio, setLinkReenvio] = useState<LinkGerado | null>(null)

  const carregar = useCallback(async () => {
    try {
      setContratos(await apiService.getContratos())
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Erro ao carregar terceirizadas')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => void carregar(), 0)
    return () => clearTimeout(timer)
  }, [carregar])

  const cadastrar = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setResultado(null)
    if (!isCnpjValido(cnpj)) {
      setFormError('CNPJ inválido: confira os dígitos.')
      return
    }
    setSaving(true)
    try {
      const r = await apiService.cadastrarTerceirizada({ cnpj, razao_social: razao.trim(), email: email.trim() })
      setResultado(r)
      setCnpj('')
      setRazao('')
      setEmail('')
      await carregar()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao cadastrar terceirizada')
    } finally {
      setSaving(false)
    }
  }

  const abrirReenvio = (c: Contrato) => {
    setReenviando(c.prestador_id)
    setEmailReenvio('')
    setReenvioError(null)
    setLinkReenvio(null)
  }

  const enviarConvite = async (e: React.FormEvent, c: Contrato) => {
    e.preventDefault()
    setReenvioError(null)
    setEnviandoConvite(true)
    try {
      const conv = await apiService.criarConvite({
        email: emailReenvio.trim(),
        nivel: 'prestador',
        papel: 'admin',
        prestador_id: c.prestador_id,
      })
      setLinkReenvio({ token: conv.token, expiraEm: conv.expira_em, titulo: c.prestador_razao_social })
      setReenviando(null)
      await carregar()
    } catch (err) {
      setReenvioError(err instanceof Error ? err.message : 'Erro ao enviar convite')
    } finally {
      setEnviandoConvite(false)
    }
  }

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button onClick={onBack} className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer">
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Terceirizadas</span>
      </nav>

      <form onSubmit={cadastrar} className={`${CARD} p-5 space-y-4`} aria-label="Cadastrar terceirizada">
        <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Cadastrar terceirizada</h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="terc-cnpj" className={LABEL}>CNPJ</label>
            <input id="terc-cnpj" className={INPUT} value={cnpj} required placeholder="00.000.000/0000-00"
              inputMode="numeric" onChange={(e) => setCnpj(maskCnpj(e.target.value))} />
          </div>
          <div>
            <label htmlFor="terc-razao" className={LABEL}>Razão social</label>
            <input id="terc-razao" className={INPUT} value={razao} required
              onChange={(e) => setRazao(e.target.value)} />
          </div>
          <div>
            <label htmlFor="terc-email" className={LABEL}>E-mail de quem vai administrar</label>
            <input id="terc-email" type="email" className={INPUT} value={email} required
              onChange={(e) => setEmail(e.target.value)} />
          </div>
        </div>
        <ErroBox message={formError} />
        <button type="submit" disabled={saving || !cnpj || !razao.trim() || !email.trim()} className={BTN}>
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar terceirizada
        </button>

        {resultado && (
          <div className="space-y-2" data-testid="resultado-terceirizada">
            <p className="text-sm font-semibold text-[#2d0a33] dark:text-white">
              {resultado.prestador.razao_social} ({formatCnpj(resultado.prestador.cnpj)})
            </p>
            {resultado.acesso === 'convite_criado' && resultado.convite && (
              <ConviteLink token={resultado.convite.token} expiraEm={resultado.convite.expira_em} />
            )}
            {resultado.acesso === 'convite_pendente' && (
              <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">
                Já existe um convite em aberto para esta terceirizada.
              </p>
            )}
            {resultado.acesso === 'ja_tem_acesso' && (
              <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">
                Esta terceirizada já usa o sistema e passa a ver o contrato com vocês.
              </p>
            )}
          </div>
        )}
      </form>

      {linkReenvio && (
        <div className={`${CARD} p-5 space-y-3`}>
          <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Convite para {linkReenvio.titulo}</h3>
          <ConviteLink token={linkReenvio.token} expiraEm={linkReenvio.expiraEm} />
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
        </div>
      ) : (
        <>
          <ErroBox message={loadError} />
          <div className={`${CARD} overflow-hidden`}>
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <th className={TH}>Razão social</th><th className={TH}>CNPJ</th>
                  <th className={TH}>Contrato</th><th className={TH}>Acesso</th><th className={TH}></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                {contratos.map((c) => (
                  <React.Fragment key={c.id}>
                    <tr>
                      <td className={`${TD} font-bold`}>{c.prestador_razao_social}</td>
                      <td className={`${TD} font-mono`}>{formatCnpj(c.prestador_cnpj)}</td>
                      <td className={TD}><Selo tom={c.ativo ? 'verde' : 'cinza'}>{c.ativo ? 'Ativo' : 'Inativo'}</Selo></td>
                      <td className={TD}>
                        <Selo tom={c.acesso_prestador === 'ativo' ? 'verde' : c.acesso_prestador === 'convite_pendente' ? 'ambar' : 'cinza'}>
                          {ESTADO_ACESSO[c.acesso_prestador ?? 'sem_acesso']}
                        </Selo>
                      </td>
                      <td className={TD}>
                        {c.acesso_prestador === 'sem_acesso' && c.ativo && (
                          <button type="button" className={BTN_SEC} onClick={() => abrirReenvio(c)}>
                            Enviar novo convite
                          </button>
                        )}
                      </td>
                    </tr>
                    {reenviando === c.prestador_id && (
                      <tr>
                        <td className={TD} colSpan={5}>
                          <form onSubmit={(e) => void enviarConvite(e, c)} className="flex flex-wrap items-end gap-3"
                            aria-label="Enviar novo convite">
                            <div className="flex-1 min-w-[16rem]">
                              <label htmlFor="reenvio-email" className={LABEL}>
                                E-mail de quem vai administrar {c.prestador_razao_social}
                              </label>
                              <input id="reenvio-email" type="email" className={INPUT} value={emailReenvio} required
                                onChange={(e) => setEmailReenvio(e.target.value)} />
                            </div>
                            <button type="submit" disabled={enviandoConvite || !emailReenvio.trim()} className={BTN}>
                              {enviandoConvite && <Loader2 className="w-4 h-4 animate-spin" />}Gerar link
                            </button>
                            <button type="button" className={BTN_SEC} onClick={() => setReenviando(null)}>Cancelar</button>
                          </form>
                          <div className="mt-3"><ErroBox message={reenvioError} /></div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {contratos.length === 0 && (
                  <tr><td className={TD} colSpan={5}>Nenhuma terceirizada cadastrada.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default TerceirizadasPage
