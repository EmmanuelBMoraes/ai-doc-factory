import React, { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { apiService, type Contrato } from '../services/api'
import { formatCnpj } from '../utils/contratos'
import { CARD, ErroBox, Selo, TD, TH } from '../components/formUi'
import { CadastroTerceirizadaForm } from '../components/CadastroTerceirizadaForm'
import {
  AcessoSelo,
  ConviteGeradoCard,
  ReenvioBotao,
  ReenvioLinha,
} from '../components/ReenvioConvite'
import { useReenvioConvite } from '../hooks/useReenvioConvite'

interface TerceirizadasPageProps {
  onBack: () => void
}

const TerceirizadasPage: React.FC<TerceirizadasPageProps> = ({ onBack }) => {
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

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

  const reenvio = useReenvioConvite(carregar)

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button onClick={onBack} className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer">
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Terceirizadas</span>
      </nav>

      <CadastroTerceirizadaForm titulo="Cadastrar terceirizada" onCadastrada={carregar} />

      <ConviteGeradoCard reenvio={reenvio} />

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
                      <td className={TD}><AcessoSelo contrato={c} /></td>
                      <td className={TD}><ReenvioBotao contrato={c} reenvio={reenvio} /></td>
                    </tr>
                    <ReenvioLinha contrato={c} reenvio={reenvio} colSpan={5} />
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
