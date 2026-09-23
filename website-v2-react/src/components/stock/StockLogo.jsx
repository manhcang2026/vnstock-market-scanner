import { useState } from 'react'
import '../../styles/stock-logo.css'

const staticOrigin = String(import.meta.env.VITE_CCC_STATIC_ORIGIN || '').trim().replace(/\/+$/, '')

export default function StockLogo({ symbol, className = '' }) {
  const safeSymbol = String(symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  const src = safeSymbol ? `${staticOrigin}/stock-logos/${safeSymbol}.webp` : ''
  const [failedSrc, setFailedSrc] = useState('')

  return (
    <span className={`stock-logo${className ? ` ${className}` : ''}`}>
      {src && failedSrc !== src ? (
        <img
          src={src}
          alt={`Logo ${safeSymbol}`}
          decoding="async"
          onError={() => setFailedSrc(src)}
        />
      ) : (
        <span className="stock-logo-fallback" role="img" aria-label={`Logo ${safeSymbol || 'cổ phiếu'} chưa có`}>
          {safeSymbol.slice(0, 3) || '—'}
        </span>
      )}
    </span>
  )
}
