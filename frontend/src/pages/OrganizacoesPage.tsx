import React, { useCallback, useEffect, useState } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'
import {
  apiService,
  type Contrato,
  type Prestador,
  type Tomador,
} from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'

type Aba = 'tomadores' | 'prestadores' | 'contratos'

const CARD =
  'rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-sm'
const INPUT =
  'w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-[#150c18] border border-[#dcd4e2] dark:border-[#3d2948] text-[#2d0a33] dark:text-white placeholder-[#8f8298] focus:outline-none focus:ring-1 focus:ring-[#9333ea]'
const LABEL = 'block text-xs font-semibold text-[#2d0a33] dark:text-white mb-1'
const BTN =
  'px-5 py-2 rounded-xl text-sm font-bold text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] disabled:opacity-50 flex items-center gap-2 transition-all cursor-pointer'
const TH =
  'px-5 py-3 text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider'
const TD = 'px-5 py-3 text-sm text-[#2d0a33] dark:text-[#f8f5fc]'

const ErroBox: React.FC<{ message: string | null }> = ({ message }) =>
  message ? (
    <div
      role="alert"
      className="p-3 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/50 flex items-center gap-2 text-red-600 dark:text-red-400"
    >
      <AlertCircle className="w-4 h-4 shrink-0" />
      <span className="text-xs font-medium">{message}</span>
    </div>
  ) : null

const Situacao: React.FC<{ ativo: boolean }> = ({ ativo }) => (
  <span
    className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold ${
      ativo
        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    }`}
  >
    {ativo ? 'Ativo' : 'Inativo'}
  </span>
)

function formatData(iso: string | null): string {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

interface OrganizacoesPageProps {
  onBack: () => void
}

const OrganizacoesPage: React.FC<OrganizacoesPageProps> = ({ onBack }) => {
  const [aba, setAba] = useState<Aba>('contratos')
  const [tomadores, setTomadores] = useState<Tomador[]>([])
  const [prestadores, setPrestadores] = useState<Prestador[]>([])
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [tomNome, setTomNome] = useState('')
  const [tomCnpj, setTomCnpj] = useState('')
  const [prestCnpj, setPrestCnpj] = useState('')
  const [prestRazao, setPrestRazao] = useState('')
  const [ctTomador, setCtTomador] = useState('')
  const [ctPrestador, setCtPrestador] = useState('')
  const [ctInicio, setCtInicio] = useState('')
  const [ctFim, setCtFim] = useState('')

  const carregar = useCallback(async () => {
    try {
      const [t, p, c] = await Promise.all([
        apiService.getTomadores(),
        apiService.getPrestadores(),
        apiService.getContratos(),
      ])
      setTomadores(t)
      setPrestadores(p)
      setContratos(c)
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Erro ao carregar organizações')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => void carregar(), 0)
    return () => clearTimeout(timer)
  }, [carregar])

  const trocarAba = (nova: Aba) => {
    setAba(nova)
    setFormError(null)
  }

  const enviar = async (e: React.FormEvent, acao: () => Promise<void>) => {
    e.preventDefault()
    setFormError(null)
    setSaving(true)
    try {
      await acao()
      await carregar()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const salvarTomador = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (tomCnpj && !isCnpjValido(tomCnpj)) throw new Error('CNPJ inválido: confira os dígitos.')
      await apiService.createTomador({ nome: tomNome, cnpj: tomCnpj || null })
      setTomNome('')
      setTomCnpj('')
    })

  const salvarPrestador = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (!isCnpjValido(prestCnpj)) throw new Error('CNPJ inválido: confira os dígitos.')
      await apiService.createPrestador({ cnpj: prestCnpj, razao_social: prestRazao })
      setPrestCnpj('')
      setPrestRazao('')
    })

  const salvarContrato = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (!ctTomador || !ctPrestador) throw new Error('Escolha o tomador e o prestador.')
      if (ctInicio && ctFim && ctFim < ctInicio) {
        throw new Error('A vigência final não pode ser anterior à inicial.')
      }
      await apiService.createContrato({
        tomador_id: Number(ctTomador),
        prestador_id: Number(ctPrestador),
        vigencia_inicio: ctInicio || null,
        vigencia_fim: ctFim || null,
      })
      setCtInicio('')
      setCtFim('')
    })

  const abas: { id: Aba; label: string; n: number }[] = [
    { id: 'contratos', label: 'Contratos', n: contratos.length },
    { id: 'tomadores', label: 'Tomadores', n: tomadores.length },
    { id: 'prestadores', label: 'Prestadores', n: prestadores.length },
  ]

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button
          onClick={onBack}
          className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer"
        >
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Organizações</span>
      </nav>

      <div className="flex items-center gap-2">
        {abas.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => trocarAba(a.id)}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
              aba === a.id
                ? 'bg-[#f4e8f7] text-[#5c1363] dark:bg-[#34163d] dark:text-[#f38df9]'
                : 'text-[#6e6378] dark:text-[#a093a8] hover:text-[#2d0a33] dark:hover:text-white'
            }`}
          >
            {a.label} ({a.n})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
        </div>
      ) : (
        <>
          <ErroBox message={loadError} />

          {aba === 'tomadores' && (
            <>
              <form onSubmit={salvarTomador} className={`${CARD} p-5 space-y-4`} aria-label="Novo tomador">
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Novo tomador</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="tom-nome" className={LABEL}>Nome</label>
                    <input id="tom-nome" className={INPUT} value={tomNome} required
                      onChange={(e) => setTomNome(e.target.value)} />
                  </div>
                  <div>
                    <label htmlFor="tom-cnpj" className={LABEL}>CNPJ (opcional)</label>
                    <input id="tom-cnpj" className={INPUT} value={tomCnpj} placeholder="00.000.000/0000-00"
                      inputMode="numeric" onChange={(e) => setTomCnpj(maskCnpj(e.target.value))} />
                  </div>
                </div>
                <ErroBox message={formError} />
                <button type="submit" disabled={saving || !tomNome.trim()} className={BTN}>
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar tomador
                </button>
              </form>
              <div className={`${CARD} overflow-hidden`}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Nome</th><th className={TH}>CNPJ</th><th className={TH}>Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {tomadores.map((t) => (
                      <tr key={t.id}>
                        <td className={`${TD} font-bold`}>{t.nome}</td>
                        <td className={`${TD} font-mono`}>{formatCnpj(t.cnpj) || '—'}</td>
                        <td className={TD}><Situacao ativo={t.ativo} /></td>
                      </tr>
                    ))}
                    {tomadores.length === 0 && (
                      <tr><td className={TD} colSpan={3}>Nenhum tomador cadastrado.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {aba === 'prestadores' && (
            <>
              <form onSubmit={salvarPrestador} className={`${CARD} p-5 space-y-4`} aria-label="Novo prestador">
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Novo prestador</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="prest-razao" className={LABEL}>Razão social</label>
                    <input id="prest-razao" className={INPUT} value={prestRazao} required
                      onChange={(e) => setPrestRazao(e.target.value)} />
                  </div>
                  <div>
                    <label htmlFor="prest-cnpj" className={LABEL}>CNPJ</label>
                    <input id="prest-cnpj" className={INPUT} value={prestCnpj} required
                      placeholder="00.000.000/0000-00" inputMode="numeric"
                      onChange={(e) => setPrestCnpj(maskCnpj(e.target.value))} />
                  </div>
                </div>
                <ErroBox message={formError} />
                <button type="submit" disabled={saving || !prestRazao.trim() || !prestCnpj} className={BTN}>
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar prestador
                </button>
              </form>
              <div className={`${CARD} overflow-hidden`}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Razão social</th><th className={TH}>CNPJ</th><th className={TH}>Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {prestadores.map((p) => (
                      <tr key={p.id}>
                        <td className={`${TD} font-bold`}>{p.razao_social}</td>
                        <td className={`${TD} font-mono`}>{formatCnpj(p.cnpj)}</td>
                        <td className={TD}><Situacao ativo={p.ativo} /></td>
                      </tr>
                    ))}
                    {prestadores.length === 0 && (
                      <tr><td className={TD} colSpan={3}>Nenhum prestador cadastrado.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {aba === 'contratos' && (
            <>
              <form onSubmit={salvarContrato} className={`${CARD} p-5 space-y-4`} aria-label="Novo contrato">
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Novo contrato</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="ct-tomador" className={LABEL}>Tomador</label>
                    <select id="ct-tomador" className={INPUT} value={ctTomador} required
                      onChange={(e) => setCtTomador(e.target.value)}>
                      <option value="">Selecione</option>
                      {tomadores.filter((t) => t.ativo).map((t) => (
                        <option key={t.id} value={t.id}>{t.nome}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="ct-prestador" className={LABEL}>Prestador</label>
                    <select id="ct-prestador" className={INPUT} value={ctPrestador} required
                      onChange={(e) => setCtPrestador(e.target.value)}>
                      <option value="">Selecione</option>
                      {prestadores.filter((p) => p.ativo).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.razao_social} ({formatCnpj(p.cnpj)})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="ct-inicio" className={LABEL}>Vigência início (opcional)</label>
                    <input id="ct-inicio" type="date" className={INPUT} value={ctInicio}
                      onChange={(e) => setCtInicio(e.target.value)} />
                  </div>
                  <div>
                    <label htmlFor="ct-fim" className={LABEL}>Vigência fim (opcional)</label>
                    <input id="ct-fim" type="date" className={INPUT} value={ctFim}
                      onChange={(e) => setCtFim(e.target.value)} />
                  </div>
                </div>
                <ErroBox message={formError} />
                <button type="submit" disabled={saving || !ctTomador || !ctPrestador} className={BTN}>
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar contrato
                </button>
              </form>
              <div className={`${CARD} overflow-hidden`}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Tomador</th><th className={TH}>Prestador</th>
                      <th className={TH}>CNPJ</th><th className={TH}>Vigência</th><th className={TH}>Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {contratos.map((c) => (
                      <tr key={c.id}>
                        <td className={`${TD} font-bold`}>{c.tomador_nome}</td>
                        <td className={TD}>{c.prestador_razao_social}</td>
                        <td className={`${TD} font-mono`}>{formatCnpj(c.prestador_cnpj)}</td>
                        <td className={TD}>{formatData(c.vigencia_inicio)} a {formatData(c.vigencia_fim)}</td>
                        <td className={TD}><Situacao ativo={c.ativo} /></td>
                      </tr>
                    ))}
                    {contratos.length === 0 && (
                      <tr><td className={TD} colSpan={5}>Nenhum contrato cadastrado.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

export default OrganizacoesPage
