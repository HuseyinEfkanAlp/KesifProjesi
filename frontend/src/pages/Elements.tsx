import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import { DISCIPLINES, ETYPE_COLORS, ETYPE_LABELS, ETYPES_BY_DISCIPLINE, SUBTYPE_LABELS, layerTypeLabels, type Catalog, type Drawing, type Element, type EType } from '../types'

/** Tipe göre düzenlenebilir sayısal alanlar */
const FIELDS: Record<EType, Array<'b' | 'h' | 'thickness' | 'length' | 'area'>> = {
  column: ['b', 'h'], shear_wall: ['b', 'length'], beam: ['b', 'h', 'length'], slab: ['thickness', 'area'], foundation: ['b', 'h', 'thickness', 'length', 'area'],
  wall: ['b', 'h', 'length'], door: ['b', 'h'], window: ['b', 'h'],
  tray: ['b', 'h', 'length'], cable: ['length'], conduit: ['length'], fixture: [],
}
const SUBTYPE_HINT: Partial<Record<EType, string>> = {
  wall: 'malzeme (ytong / tugla / bims / alcipan)', tray: 'boyut, ör. 200x60', cable: 'kesit, ör. NYY 4x16', conduit: 'çap, ör. Ø20 PVC',
  fixture: 'kategori (armatur / priz / anahtar / data / yangin / pano)',
}

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
  const [manual, setManual] = useState({ etype: '' as EType | '', name: '', subtype: '', b: 0.3, h: 0.6, length: 0, thickness: 0, area: 0, count: 1 })
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [measureSel, setMeasureSel] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    try {
      const [d, els, s] = await Promise.all([Api.drawings.get(drawingId), Api.drawings.elements(drawingId), Api.drawings.previewSvg(drawingId)])
      setDrawing(d); setElements(els); setSvg(s)
      setManual((m) => (m.etype ? m : { ...m, etype: ETYPES_BY_DISCIPLINE[d.discipline][0] ?? '' }))
      if (d.discipline === 'mapped') Api.catalog.get().then(setCatalog).catch(() => {})
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

  const mapLayer = (layer: string, etype: string) => run(() => Api.projects.mapLayer(pid, layer, etype || null))
  const patch = (el: Element, body: Partial<Element>) => run(() => Api.elements.patch(el.id, body))
  const remove = (el: Element) => { if (confirm('Eleman silinsin mi?')) run(() => Api.elements.remove(el.id)) }
  const addManual = (e: React.FormEvent) => {
    e.preventDefault()
    if (!manual.etype) return
    const t = manual.etype
    const body: Partial<Element> = { etype: t, name: manual.name || null, count: manual.count, subtype: manual.subtype || (t === 'foundation' ? 'strip' : null) }
    for (const f of FIELDS[t]) {
      const v = manual[f]
      if (v) (body as Record<string, unknown>)[f] = v
    }
    run(() => Api.drawings.addElement(drawingId, body))
  }

  const numCell = (el: Element, field: 'b' | 'h' | 'thickness' | 'length' | 'area', asCm: boolean) => {
    if (!(FIELDS[el.etype] ?? ['length', 'area']).includes(field)) {
      const v = el[field]
      return <td className="num muted">{v ? (asCm ? Math.round(v * 100) : fmt(v, field === 'area' ? 3 : 2)) : '-'}</td>
    }
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
  const discipline = drawing.discipline
  const isMapped = discipline === 'mapped'
  const isStd = discipline === 'standard' || isMapped
  // KSF / eşlemeli çizimde tipler katalog kalem kodlarıdır; etiketleri katman bilgisinden alınır
  const stdLabels: Record<string, string> = {}
  if (isStd) for (const l of drawing.layers) if (l.etype && l.etype_label) stdLabels[l.etype] = l.etype_label.split(' · ')[0].replace(/ \[.*\]$/, '')
  const mapItem = (layer: string, code: string, measure: string) => run(() => Api.projects.mapLayer(pid, layer, code ? `item:${code}${measure ? ':' + measure : ''}` : null))
  const itemName = (code: string) => catalog?.items.find((i) => i.code === code)?.name ?? code
  const ETYPES: string[] = isStd ? Array.from(new Set(elements.map((e) => e.etype))) : ETYPES_BY_DISCIPLINE[discipline]
  const labelOf = (t: string) => (ETYPE_LABELS as Record<string, string>)[t] ?? stdLabels[t] ?? t
  const colorOf = (t: string) => (ETYPE_COLORS as Record<string, string>)[t] ?? '#555'
  const layerTypes = layerTypeLabels(discipline)
  const isElec = discipline === 'electrical'
  const shown = elements.filter((e) => !filter || e.etype === filter)
  const counts = ETYPES.map((t) => [t, elements.filter((e) => e.etype === t).length] as const)
  const subtypeText = (el: Element) => (el.subtype ? (SUBTYPE_LABELS[el.subtype] ?? el.subtype) : '')
  const mt = manual.etype as EType

  return (
    <>
      <div className="row between">
        <h1>
          {drawing.label} <span className={`badge disc-${discipline}`}>{DISCIPLINES[discipline]}</span>
          <span className="muted" style={{ fontSize: 14 }}> ({drawing.filename}, birim: {drawing.unit})</span>
        </h1>
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
          <div className="legend">{ETYPES.map((t) => <span key={t}><i style={{ background: colorOf(t) }} />{labelOf(t)}</span>)}<span className="muted">— tıklayınca tabloda seçilir</span></div>
          <div className="svg-wrap" ref={svgRef} dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
        <div className="panel">
          <h3>{isMapped ? 'Katman → katalog kalemi eşleme' : isStd ? 'Katmanlar (KSF standardı)' : 'Katman eşleme'}</h3>
          {isMapped ? (
            <p className="muted">Her katmanı ölçülecek bir katalog kalemine ve ölçüm kuralına atayın (kapalı çokgen / tarama → m², çizgi → m, blok → adet).
              Katman adından üretilen öneriler <b>öneri</b> düğmesiyle tek tıkla uygulanır. Eşlenmeyen katman metraja girmez. <Link to="/standard">Katalog</Link></p>
          ) : isStd ? (
            <p className="muted">Katman adı kalemi tanımlar; eşleme gerekmez. <code className="layer">KSF-</code> ile başlamayan katmanlar metraja girmez.
              Tanınmayan kalem kodları <Link to="/standard">Standart</Link> sayfasından kataloğa eklenir.</p>
          ) : (
            <p className="muted">
              Hangi katman hangi elemanı çiziyor? Eşlenmemiş katmanlar metraja girmez. Bu çizim <b>{DISCIPLINES[discipline]}</b> disiplininde;
              yalnızca bu disiplinin tipleri seçilebilir (disiplin proje sayfasından değiştirilir). Değişiklik projedeki tüm çizimlere uygulanır.
            </p>
          )}
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            <table>
              <thead><tr><th>Katman</th><th className="num">Nesne</th><th>Eleman tipi</th></tr></thead>
              <tbody>
                {drawing.layers.filter((l) => l.count > 0).map((l) => (
                  <tr key={l.name}>
                    <td className="mono">{l.name}</td>
                    <td className="num">{l.count}</td>
                    <td>
                      {isMapped ? (
                        <div className="row" style={{ gap: 6 }}>
                          <select value={l.mapped_code ?? ''} disabled={busy || !catalog}
                            onChange={(e) => mapItem(l.name, e.target.value, measureSel[l.name] ?? l.mapped_measure ?? '')} style={{ maxWidth: 260 }}>
                            <option value="">— ölçülmez —</option>
                            {catalog?.by_discipline.map((g) => (
                              <optgroup key={g.code} label={`${g.code} · ${g.name}`}>
                                {g.items.map((it) => <option key={it.code} value={it.code}>{it.name} ({it.unit})</option>)}
                              </optgroup>
                            ))}
                          </select>
                          <select value={measureSel[l.name] ?? l.mapped_measure ?? ''} disabled={busy}
                            onChange={(e) => { setMeasureSel({ ...measureSel, [l.name]: e.target.value }); if (l.mapped_code) mapItem(l.name, l.mapped_code, e.target.value) }}>
                            <option value="">ölçüm: kalem varsayılanı</option>
                            {catalog && Object.entries(catalog.measures).map(([m, v]) => <option key={m} value={m}>{v.label}</option>)}
                          </select>
                          {!l.mapped_code && l.suggested && (
                            <button className="small secondary" disabled={busy} title={`Öneri: ${itemName(l.suggested)}`}
                              onClick={() => mapItem(l.name, l.suggested!, measureSel[l.name] ?? '')}>öneri: {itemName(l.suggested)}</button>
                          )}
                        </div>
                      ) : isStd ? (l.etype_label ? <span>{l.etype_label}</span> : <span className="muted">— standart dışı, yok sayılır —</span>) : (
                        <select value={l.etype ?? ''} disabled={busy} onChange={(e) => mapLayer(l.name, e.target.value)}>
                          <option value="">— yok sayılır —</option>
                          {Object.entries(layerTypes).map(([t, lbl]) => <option key={t} value={t}>{lbl}</option>)}
                        </select>
                      )}
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
            {counts.map(([t, n]) => <button key={t} className={`small ${filter === t ? '' : 'secondary'}`} onClick={() => setFilter(t as EType)}>{labelOf(t)} ({n})</button>)}
          </div>
        </div>
        <p className="muted">
          {isElec ? 'Tava genişlik/yükseklik mm; uzunluk m.' : 'Boyutlar cm; uzunluk m.'} Hücreyi düzenleyip dışına tıklayın; alan otomatik güncellenir.
          Elle düzenlenen elemanlar yeniden analizde korunur. {discipline === 'architectural' && 'Duvarda h boşsa proje duvar yüksekliği kullanılır; kapı/pencerede b×h boşluk alanıdır.'}
        </p>
        <div style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Dahil</th><th>Tip</th><th>Ad</th><th>{discipline === 'structural' ? 'Alt tip' : discipline === 'architectural' ? 'Malzeme / blok' : isStd ? 'Özellik' : 'Boyut / kesit / kategori'}</th><th>Katman</th>
                <th className="num">b {isElec ? '(mm)' : '(cm)'}</th><th className="num">h {isElec ? '(mm)' : '(cm)'}</th><th className="num">Kal. (cm)</th>
                <th className="num">Uzunluk (m)</th><th className="num">Alan (m²)</th><th className="num">Adet</th><th>Güven</th><th>Etiket / Uyarı</th><th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((el) => (
                <tr key={el.id} className={`${selected === el.id ? 'selected' : ''} ${el.included ? '' : 'excluded'}`} onClick={() => setSelected(el.id)}>
                  <td><input type="checkbox" checked={el.included} onChange={(e) => patch(el, { included: e.target.checked })} /></td>
                  <td>
                    {isStd ? <span className="badge" style={{ background: colorOf(el.etype) }}>{labelOf(el.etype)}</span> : (
                      <select value={el.etype} onChange={(e) => patch(el, { etype: e.target.value as EType })} className="badge-select">
                        {ETYPES.map((t) => <option key={t} value={t}>{labelOf(t)}</option>)}
                        {!ETYPES.includes(el.etype) && <option value={el.etype}>{labelOf(el.etype)}</option>}
                      </select>
                    )}
                  </td>
                  <td><input style={{ width: 90 }} defaultValue={el.name ?? ''} key={`${el.id}-name-${el.name}`} onBlur={(e) => e.target.value !== (el.name ?? '') && patch(el, { name: e.target.value })} /></td>
                  <td>
                    {discipline === 'structural'
                      ? <span className="muted">{subtypeText(el)}</span>
                      : <input style={{ width: 120 }} defaultValue={el.subtype ?? ''} key={`${el.id}-sub-${el.subtype}`} title={subtypeText(el)}
                          onBlur={(e) => e.target.value !== (el.subtype ?? '') && patch(el, { subtype: e.target.value || null })} />}
                  </td>
                  <td className="mono">{el.layer}</td>
                  {isElec
                    ? <td className="num">{el.b ? Math.round(el.b * 1000) : '-'}</td>
                    : numCell(el, 'b', true)}
                  {isElec
                    ? <td className="num">{el.h ? Math.round(el.h * 1000) : '-'}</td>
                    : numCell(el, 'h', true)}
                  {numCell(el, 'thickness', true)}
                  {numCell(el, 'length', false)}
                  {numCell(el, 'area', false)}
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

        {!isStd && <h3>Elle eleman ekle</h3>}
        {!isStd && <form className="row" onSubmit={addManual}>
          <label className="field">Tip
            <select value={manual.etype} onChange={(e) => setManual({ ...manual, etype: e.target.value as EType })}>
              {ETYPES.map((t) => <option key={t} value={t}>{labelOf(t)}{t === 'foundation' ? ' (sürekli)' : ''}</option>)}
            </select>
          </label>
          <label className="field">Ad<input style={{ width: 90 }} value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} /></label>
          {mt && SUBTYPE_HINT[mt] && <label className="field">{SUBTYPE_HINT[mt]}<input style={{ width: 170 }} value={manual.subtype} onChange={(e) => setManual({ ...manual, subtype: e.target.value })} /></label>}
          {mt && FIELDS[mt].includes('b') && <label className="field">b (m)<input type="number" step="0.01" value={manual.b} onChange={(e) => setManual({ ...manual, b: +e.target.value })} /></label>}
          {mt && FIELDS[mt].includes('h') && <label className="field">h (m)<input type="number" step="0.01" value={manual.h} onChange={(e) => setManual({ ...manual, h: +e.target.value })} /></label>}
          {mt && FIELDS[mt].includes('thickness') && <label className="field">Kalınlık (m)<input type="number" step="0.01" value={manual.thickness} onChange={(e) => setManual({ ...manual, thickness: +e.target.value })} /></label>}
          {mt && FIELDS[mt].includes('length') && <label className="field">Uzunluk (m)<input type="number" step="0.01" value={manual.length} onChange={(e) => setManual({ ...manual, length: +e.target.value })} /></label>}
          {mt && FIELDS[mt].includes('area') && <label className="field">Alan (m²)<input type="number" step="0.01" value={manual.area} onChange={(e) => setManual({ ...manual, area: +e.target.value })} /></label>}
          <label className="field">Adet<input type="number" min={1} value={manual.count} onChange={(e) => setManual({ ...manual, count: +e.target.value })} /></label>
          <button type="submit" disabled={busy || !manual.etype}>Ekle</button>
        </form>}
      </div>
    </>
  )
}
