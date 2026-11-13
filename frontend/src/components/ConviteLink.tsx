import React, { useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { BTN_SEC } from './formUi'
import { formatDataHora, montarLinkConvite } from '../utils/convites'

interface ConviteLinkProps {
  token: string
  expiraEm: string
}

/** Caixa com o link recém-criado. O token só existe agora; não é guardado em lugar nenhum. */
export const ConviteLink: React.FC<ConviteLinkProps> = ({ token, expiraEm }) => {
  const [copiado, setCopiado] = useState(false)
  const campo = useRef<HTMLInputElement>(null)
  const link = montarLinkConvite(token)

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(link)
    } catch {
      // sem permissão da área de transferência: seleciona o texto para copiar à mão
      campo.current?.select()
      return
    }
    setCopiado(true)
    setTimeout(() => setCopiado(false), 2000)
  }

  return (
    <div className="p-4 rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/20 space-y-2">
      <div className="flex items-center gap-2">
        <input
          ref={campo}
          readOnly
          value={link}
          onFocus={(e) => e.currentTarget.select()}
          aria-label="Link do convite"
          className="flex-1 min-w-0 px-3 py-2 rounded-lg text-xs font-mono bg-white dark:bg-[#150c18] border border-[#dcd4e2] dark:border-[#3d2948] text-[#2d0a33] dark:text-white"
        />
        <button type="button" onClick={copiar} className={BTN_SEC}>
          {copiado ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
          {copiado ? 'Copiado' : 'Copiar'}
        </button>
      </div>
      <p className="text-xs text-emerald-800 dark:text-emerald-300">
        Este link só aparece agora e vale até {formatDataHora(expiraEm)}. Envie para a pessoa por WhatsApp ou e-mail.
      </p>
    </div>
  )
}
