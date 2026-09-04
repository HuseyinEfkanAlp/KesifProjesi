import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import { ETYPE_LABELS, LAYER_TYPE_LABELS, type Drawing, type Element, type EType } from '../types'

const ETYPES = Object.keys(ETYPE_LABELS) as EType[]

export default function Elements() {
  const { id, did } = useParams()
  const pid = Number(id), drawingId = Number(did)
  const [drawing, setDrawing] = useState<Drawing | null>(null)
  const [elements, setElements] = useState<Element[]>([])
  const [svg, setSvg] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState<EType | ''>('')
  const svgRef = useRef<HTMLDivElement>(null)
  const [manual, setManual] = useState({ etype: 'column' as EType, name: '', b: 0.3, h: 0.6, length: 0, thickness: 0, count: 1 })

  const load = useCallback(async () => {
    try {
      const [d, els, s] = await Promise.all([Api.drawings.get(drawingId), Api.drawings.elements(drawingId), Api.drawings.previewSvg(drawingId)])
      setDrawing(d); setElements(els); setSvg(s)
    } catch (e) { setError((e as Error).message) }
  }, [drawingId])
  useEffect(() => { load() }, [load])

  // SVG üzerinde tıklama -> satır seç
  useEffect(() => {
    const root = svgRef.current
    if (!root) return
    const handler = (ev: MouseEvent) => {
      const t = (ev.target as SVGElement).closest('polygon.el') as SVGElement | null
      if (t) setSelected(Number(t.dataset.id))
    }
    root.addEventListener('click', handler)
    return () => root.removeEventListener('click', handler)
  }, [svg])
  useEffect(() => {
    const root = svgRef.current
    if (!root) return
    root.querySelectorAll('polygon.el.selected').forEach((n) => n.classList.remove('selected'))
    if (selected !== null) root.querySelector(`polygon.el[data-id="${selected}"]`)?.classList.add('selected')
  }, [selected, svg])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await fn(); await load() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const mapLayer = (layer: string, etype: string) => run(() => Api.projects.mapLayer(pid, layer, (etype || null) as EType | null))
  const patch = (el: Element, body: Partial<Element>) => run(() => Api.elements.patch(el.id, body))
  const remove = (el: Element) => { if (confirm('Eleman silinsin mi?')) run(() => Api.elements.remove(el.id)) }
  const addManual = (e: React.FormEvent) => {
    e.preventDefault()
    const body: Partial<Element> = { etype: manual.etype, name: manual.name || null, count: manual.count }
    if (manual.etype === 'column') Object.assign(body, { b: manual.b, h: manual.h })
    if (manual.etype === 'shear_wall') Object.assign(body, { b: manual.b, length: manual.length })
    if (manual.etype === 'beam') Object.assign(body, { b: manual.b, h: manual.h, length: manual.length })
    if (manual.etype === 'slab') Object.assign(body, { area: manual.length, thickness: manual.thickness })
    if (manual.etype === 'foundation') Object.assign(body, { subtype: 'strip', b: manual.b, h: manual.h, length: manual.length })
    run(() => Api.drawings.addElement(drawingId, body))
  }

  const numCell = (el: Element, field: 'b' | 'h' | 'thickness' | 'length' | 'area', asCm: boolean) => {
    const v = el[field]
    return (
      <td className="num">
        <input type="number" step={asCm ? 1 : 0.01} defaultValue={v === null || v === undefined ? '' : asCm ? Math.round(v * 100) : +v.toFixed(3)}
          key={`${el.id}-${field}-${v}`}
          onBlur={(e) => {
            if (e.target.value === '') return
            const nv = asCm ? +e.target.value / 100 : +e.target.value
            if (Math.abs(nv - (v ?? -1)) > 1e-6) patch(el, { [field]: nv })
          }} />
      </td>
    )
  }

  if (!drawing) return <p className="muted">{error || 'Yükleniyor...'}</p>
  const shown = elements.filter((e) => !filter || e.etype === filter)
  const counts = ETYPES.map((t) => [t, elements.filter((e) => e.etype === t).length] as const)

  return (
    <>
      <div className="row between">
        <h1>{drawing.label} <span className="muted" style={{ fontSize: 14 }}>({drawing.filename}, birim: {drawing.unit})</span></h1>
        <div className="row">
          <Link to={`/projects/${pid}`}>← Projeye dön</Link>
          <button className="secondary" disabled={busy} onClick={() => run(() => Api.drawings.reanalyze(drawingId))}>Yeniden analiz et</button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {drawing.warnings.length > 0 && (
        <div className="warn"><b>Uyarılar</b><ul>{drawing.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>
      )}

      <div className="grid2">
        <div className="panel">
          <h3>Plan önizleme</h3>
          <div className="legend">{ETYPES.map((t) => <span key={t}><i style={{ background: color(t) }} />{ETYPE_LABELS[t]}</span>)}<span className="muted">— tıklayınca tabloda seçilir</span></div>
          <div className="svg-wrap" ref={svgRef} dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
        <div className="panel">
          <h3>Katman eşleme</h3>
          <p className="muted">Hangi katman hangi elemanı çiziyor? Eşlenmemiş katmanlar metraja girmez. Değişiklik projedeki tüm çizimlere uygulanır.</p>
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            <table>
              <thead><tr><th>Katman</th><th className="num">Nesne</th><th>Eleman tipi</th></tr></thead>
              <tbody>
                {drawing.layers.filter((l) => l.count > 0).map((l) => (
                  <tr key={l.name}>
                    <td className="mono">{l.name}</td>
                    <td className="num">{l.count}</td>
                    <td>
                      <select value={l.etype ?? ''} disabled={busy} onChange={(e) => mapLayer(l.name, e.target.value)}>
                        <option value="">— yok sayılır —</option>
                        {Object.entries(LAYER_TYPE_LABELS).map(([t, lbl]) => <option key={t} value={t}>{lbl}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="row between">
          <h3>Tespit edilen elemanlar ({elements.length})</h3>
          <div className="row">
            <button className={`small ${filter === '' ? '' : 'secondary'}`} onClick={() => setFilter('')}>Tümü</button>
            {counts.map(([t, n]) => <button key={t} className={`small ${filter === t ? '' : 'secondary'}`} onClick={() => setFilter(t)}>{ETYPE_LABELS[t]} ({n})</button>)}
          </div>
        </div>
        <p className="muted">Boyutlar cm. Hücreyi düzenleyip dışına tıklayın; alan/çevre otomatik güncellenir. Elle düzenlenen elemanlar yeniden analizde korunur.</p>
        <div style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Dahil</th><th>Tip</th><th>Ad</th><th>Katman</th><th className="num">b</th><th className="num">h</th><th className="num">Kal.</th>
                <th className="num">Uzunluk (m)</th><th className="num">Alan (m²)</th><th className="num">Adet</th><th>Güven</th><th>Etiket / Uyarı</th><th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((el) => (
                <tr key={el.id} className={`${selected === el.id ? 'selected' : ''} ${el.included ? '' : 'excluded'}`} onClick={() => setSelected(el.id)}>
                  <td><input type="checkbox" checked={el.included} onChange={(e) => patch(el, { included: e.target.checked })} /></td>
                  <td>
                    <select value={el.etype} onChange={(e) => patch(el, { etype: e.target.value as EType })} className="badge-select">
                      {ETYPES.map((t) => <option key={t} value={t}>{ETYPE_LABELS[t]}</option>)}
                    </select>
                    {el.subtype && <div className="muted">{el.subtype === 'raft' ? 'radye' : 'sürekli'}</div>}
                  </td>
                  <td><input style={{ width: 70 }} defaultValue={el.name ?? ''} key={`${el.id}-name-${el.name}`} onBlur={(e) => e.target.value !== (el.name ?? '') && patch(el, { name: e.target.value })} /></td>
                  <td className="mono">{el.layer}</td>
                  {numCell(el, 'b', true)}
                  {numCell(el, 'h', true)}
                  {numCell(el, 'thickness', true)}
                  {numCell(el, 'length', false)}
                  {el.etype === 'slab' || (el.etype === 'foundation' && el.subtype === 'raft')
                    ? numCell(el, 'area', false)
                    : <td className="num">{fmt(el.area, 3)}</td>}
                  <td className="num"><input type="number" min={1} style={{ width: 55 }} defaultValue={el.count} key={`${el.id}-count-${el.count}`} onBlur={(e) => +e.target.value !== el.count && patch(el, { count: +e.target.value })} /></td>
                  <td>
                    {el.manual ? <span className="muted">elle</span> : (
                      <span className={`conf ${el.confidence < 0.6 ? 'low' : ''}`} title={`${Math.round(el.confidence * 100)}%`}><i style={{ width: `${el.confidence * 100}%` }} /></span>
                    )}
                  </td>
                  <td>
                    {el.label_raw && <div className="mono">{el.label_raw}</div>}
                    {el.warnings.map((w, i) => <div key={i} className="muted">⚠ {w}</div>)}
                  </td>
                  <td><button className="danger small" onClick={(e) => { e.stopPropagation(); remove(el) }}>Sil</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3>Elle eleman ekle</h3>
        <form className="row" onSubmit={addManual}>
          <label className="field">Tip
            <select value={manual.etype} onChange={(e) => setManual({ ...manual, etype: e.target.value as EType })}>
              {ETYPES.map((t) => <option key={t} value={t}>{ETYPE_LABELS[t]}{t === 'foundation' ? ' (sürekli)' : ''}</option>)}
            </select>
          </label>
          <label className="field">Ad<input style={{ width: 80 }} value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} /></label>
          {manual.etype !== 'slab' && <label className="field">b (m)<input type="number" step="0.01" value={manual.b} onChange={(e) => setManual({ ...manual, b: +e.target.value })} /></label>}
          {(manual.etype === 'column' || manual.etype === 'beam' || manual.etype === 'foundation') && <label className="field">h (m)<input type="number" step="0.01" value={manual.h} onChange={(e) => setManual({ ...manual, h: +e.target.value })} /></label>}
          {manual.etype === 'slab' && <label className="field">Kalınlık (m)<input type="number" step="0.01" value={manual.thickness} onChange={(e) => setManual({ ...manual, thickness: +e.target.value })} /></label>}
          {manual.etype !== 'column' && <label className="field">{manual.etype === 'slab' ? 'Alan (m²)' : 'Uzunluk (m)'}<input type="number" step="0.01" value={manual.length} onChange={(e) => setManual({ ...manual, length: +e.target.value })} /></label>}
          <label className="field">Adet<input type="number" min={1} value={manual.count} onChange={(e) => setManual({ ...manual, count: +e.target.value })} /></label>
          <button type="submit" disabled={busy}>Ekle</button>
        </form>
      </div>
    </>
  )
}

function color(t: EType) {
  return { column: '#d62728', shear_wall: '#9467bd', beam: '#1f77b4', slab: '#2ca02c', foundation: '#ff7f0e' }[t]
}
