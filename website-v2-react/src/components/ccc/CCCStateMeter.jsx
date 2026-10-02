import { useEffect, useRef, useState } from 'react'
import { cccStatePresentation, cccStateSignature, meterSignalLevel } from '../../lib/cccState'
import '../../styles/ccc-state.css'

export default function CCCStateMeter({ signalState, signalLevel, compact = false, showLabel = true, muted = false, animateOnChange = false }) {
  const { label, tone } = cccStatePresentation(signalState)
  const level = meterSignalLevel(signalLevel)
  const signature = cccStateSignature(signalState, signalLevel)
  const previousSignature = useRef(null)
  const [animation, setAnimation] = useState({ signature: null, run: 0 })
  const accessible = level === null
    ? `${label}, chưa có mức trạng thái`
    : `${label}, mức ${level} trên 4`

  useEffect(() => {
    if (!animateOnChange || signature === null) return undefined
    const previous = previousSignature.current
    previousSignature.current = signature
    if (previous === null || previous === signature || muted || level === null || level === 0) return undefined

    const frame = window.requestAnimationFrame(() => {
      setAnimation((current) => ({ signature, run: current.run + 1 }))
    })
    return () => window.cancelAnimationFrame(frame)
  }, [animateOnChange, signature, muted, level])

  useEffect(() => {
    if (animation.signature === null) return undefined
    const timer = window.setTimeout(() => {
      setAnimation((current) => current.run === animation.run ? { ...current, signature: null } : current)
    }, 430)
    return () => window.clearTimeout(timer)
  }, [animation.signature, animation.run])

  const animating = animateOnChange && !muted && animation.signature !== null && animation.signature === signature

  return (
    <span className={`ccc-state-meter ccc-state-tone--${tone}${compact ? ' is-compact' : ''}${muted ? ' is-muted' : ''}${animating ? ' is-animating' : ''}`} role="img" aria-label={accessible}>
      <span key={animation.run} className="ccc-state-meter-blocks" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => <span key={index} className={level !== null && index < level ? 'is-filled' : ''} />)}
      </span>
      {showLabel ? <span className="ccc-state-meter-label" aria-hidden="true">{label}</span> : null}
    </span>
  )
}
