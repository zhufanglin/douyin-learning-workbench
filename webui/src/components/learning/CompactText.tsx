import { useEffect, useId, useRef, useState } from 'react'

/** Keep full text available to keyboard and touch users as well as mouse users. */
export function CompactText({ text }: { text: string }) {
  const id = useId()
  const ref = useRef<HTMLParagraphElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflow, setOverflow] = useState(false)
  useEffect(() => { setExpanded(false) }, [text])
  useEffect(() => {
    const node = ref.current
    if (!node || expanded) return
    const measure = () => setOverflow(node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [text, expanded])
  return <div className="compact-text">
    <p ref={ref} id={id} className={expanded ? 'compact-text-full' : 'compact-text-preview'} title={expanded ? undefined : text}>{text}</p>
    {(overflow || expanded) && <button type="button" className="compact-text-toggle" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded(value => !value)}>{expanded ? '收起全文' : '展开全文'}</button>}
  </div>
}
