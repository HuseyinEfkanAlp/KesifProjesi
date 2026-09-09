import { useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { useParams } from 'react-router-dom'
import { Api } from '../api/client'
import type { PriceIn, PriceItem, Project } from '../types'
import ProjectNav from './ProjectNav'

type Field = 'unit_price' | 'labor_price' | 'hours_per_unit' | 'crew_size' | 'brand'
type Edit = Partial<Record<Field, number | string>>
type Mode = 'material' | 'labor'
const MODE_FIELDS: Record<Mode, Field[]> = { material: ['brand', 'unit_price'], labor: ['labor_price', 'hours_per_unit', 'crew_size'] }

const GROUP_ORDER = ['KABA', 'INCE', 'MEK', 'ELK', 'ALT']

export default function Prices() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [items, setItems] = useState<PriceItem[]>([])
  const [edited, setEdited] = useState<Record<string, Edit>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [showSpecific, setShowSpecific] = useState(true)
  const [mode, setMode] = useState<Mode>(() => { try { return (localStorage.getItem('prices.mode') as Mode) || 'material' } catch { return 'material' } })
  const [group, setGroup] = useState('')
  const [q, setQ] = useState('')

  const load = () => Promise.all([Api.projects.get(pid), Api.prices.list(pid)])
    .then(([p, it]) => { setProject(p); setItems(it); setEdited({}) })
    .catch((e) => setError(e.message))
  useEffect(() => { load() }, [pid]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key: string, field: Field, value: string) => {
    setSaved(false)
    const v: number | string = field === 'brand' ? value : (value === '' ? '' : +value)   // '' = temizle (genel satır uygulanır)
    setEdited({ ...edited, [key]: { ...(edited[key] || {}), [field]: v } })
  }
  const val = (i: PriceItem, field: Field) => {
    const e = edited[i.key]
    if (e && field in e) return e[field] as number | string
    if (field !== 'brand' && !i.is_general && !(i.set_fields || []).includes(field) && !(i[field] > 0)) return ''   // girilmedi: boş
    return i[field]
  }

  const save = async () => {
    setError(''); setSaved(false)
    try {
      const body: PriceIn[] = Object.entries(edited).map(([key, e]) => {
        const out: Record<string, unknown> = { key }
        const clear: string[] = []
        for (const [f, v] of Object.entries(e)) {
          if (f !== 'brand' && v === '') clear.push(f)
          else out[f] = v
        }
        if (clear.length) out.clear = clear
        return out as unknown as PriceIn
      })
      await Api.prices.save(pid, body)
      await load(); setSaved(true)
    } catch (e) { setError((e as Error).message) }
  }

  if (!project) return <Loading error={error} />
  const hoursPerDay = project.params?.work_hours_per_day ?? 8
  const dirty = Object.keys(edited).length
  const dirtyIn = (m: Mode) => Object.values(edited).filter((e) => MODE_FIELDS[m].some((f) => f in e)).length
  const specific = items.filter((i) => !i.is_general)
  const priceField: Exclude<Field, 'brand'> = mode === 'material' ? 'unit_price' : 'labor_price'
  const has = (i: PriceItem) => i[priceField] > 0 || (i.set_fields || []).includes(priceField)
  const priced = specific.filter((i) => has(i) || items.some((g) => g.is_general && g.kind === i.kind && g[priceField] > 0)).length
  const switchMode = (m: Mode) => { setMode(m); try { localStorage.setItem('prices.mode', m) } catch { /* yok say */ } }
  const qq = q.trim().toLocaleLowerCase('tr-TR')
  const groupKeys = Array.from(new Set(items.map((i) => i.work_group)))
    .sort((a, b) => (GROUP_ORDER.indexOf(a) === -1 ? 99 : GROUP_ORDER.indexOf(a)) - (GROUP_ORDER.indexOf(b) === -1 ? 99 : GROUP_ORDER.indexOf(b)))
  const byGroup = groupKeys
    .filter((g) => !group || g === group)
    .map((g) => ({ g, label: items.find((i) => i.work_group === g)?.work_group_label ?? g,
      rows: items.filter((i) => i.work_group === g && (showSpecific || i.is_general) && (!qq || i.name.toLocaleLowerCase('tr-TR').includes(qq) || i.kind_label.toLocaleLowerCase('tr-TR').includes(qq) || (i.poz || '').includes(qq))) }))
    .filter((x) => x.rows.length > 0)
  const kindsOf = (rows: PriceItem[]) => Array.from(new Set(rows.map((r) => r.kind)))
  const fmtQ = (v: number | null) => v == null ? '' : v.toLocaleString('tr-TR', { maximumFractionDigits: v >= 100 ? 0 : 2 })
  const effective = (i: PriceItem, field: Exclude<Field, 'brand'>): number => {
    const v = val(i, field)
    if (v !== '' && +v > 0) return +v
    if (v === 0 && ((i.set_fields || []).includes(field) || (edited[i.key] && field in edited[i.key]))) return 0   // açık 0: bu kalemde yok
    const g = items.find((x) => x.is_general && x.kind === i.kind)
    const gv = g ? val(g, field) : ''
    return gv === '' ? 0 : +gv
  }
  const lineTotal = (i: PriceItem) => i.quantity == null || i.is_general ? null : i.quantity * effective(i, priceField)

  const numInput = (i: PriceItem, field: Exclude<Field, 'brand'>, step = '0.01') => {
    const v = val(i, field) as number
    return (
      <td className="num">
        <input type="number" min={0} step={step} className={`wide${edited[i.key] && field in edited[i.key] ? ' dirty' : ''}`} value={v}
          placeholder={i.is_general ? '0' : 'genel'} title={i.is_general ? '' : 'Boş: türün genel satırı uygulanır. 0: bu kalemde yok (ör. işçilik yok)'}
          onChange={(e) => set(i.key, field, e.target.value)} />
      </td>
    )
  }

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      {items.length === 0 && (
        <div className="panel empty-state">
          <h2>Fiyatlanacak kalem yok</h2>
          <p>Önce plan yükleyin; keşif kalemleri çıkınca her biri için malzeme ve işçilik fiyatı burada girilir.</p>
        </div>
      )}
      {items.length > 0 && (
        <div className="panel">
          <div className="row between sticky-bar">
            <div className="row" style={{ gap: 14 }}>
              <h3 style={{ margin: 0 }}>Birim fiyatlar</h3>
              <div className="chips" style={{ margin: 0 }}>
                <button className={`chip-btn${mode === 'material' ? ' on' : ''}`} onClick={() => switchMode('material')}>Malzeme fiyatları{dirtyIn('material') > 0 && ' •'}</button>
                <button className={`chip-btn${mode === 'labor' ? ' on' : ''}`} onClick={() => switchMode('labor')}>İşçilik fiyatları{dirtyIn('labor') > 0 && ' •'}</button>
              </div>
              <span className="count-pill">{priced} / {specific.length} {mode === 'material' ? 'malzeme fiyatlı' : 'işçilik fiyatlı'}</span>
              <input placeholder="ara: ytong, kablo, 15.225…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 220 }} />
              <button className={`chip-btn${showSpecific ? '' : ' on'}`} onClick={() => setShowSpecific(!showSpecific)} title="Yalnız türün genel satırlarını göster">yalnız genel satırlar</button>
            </div>
            <div className="row">
              {saved && !dirty && <span className="ok">Kaydedildi</span>}
              {dirty > 0 && <span className="muted">{dirty} satır değişti</span>}
              <button onClick={save} disabled={dirty === 0}>Fiyatları kaydet</button>
            </div>
          </div>
          <p className="muted hint">
            {mode === 'material'
              ? <>Malzeme birim fiyatı (₺/birim, KDV hariç) ve tercih edilen marka. Türün <b>genel</b> satırı, boş bırakılan kalemlere uygulanır; işçilik ayrı sekmede girilir.</>
              : <>İşçilik birim fiyatı (₺/birim, KDV hariç), adam-saat / birim ve ekip. Süre = miktar × adam-saat / (ekip × {hoursPerDay} saat/gün). Türün <b>genel</b> satırı boş bırakılan kalemlere uygulanır; "reçete" rozetli kalemler ana kalemden türetilen alt işlerdir.</>}
          </p>
          <div className="chips" style={{ margin: '6px 0 10px' }}>
            <button className={`chip-btn${group === '' ? ' on' : ''}`} onClick={() => setGroup('')}>Tümü</button>
            {groupKeys.map((g) => <button key={g} className={`chip-btn${group === g ? ' on' : ''}`} onClick={() => setGroup(group === g ? '' : g)}>{items.find((i) => i.work_group === g)?.work_group_label} ({items.filter((i) => i.work_group === g && !i.is_general).length})</button>)}
          </div>
          {byGroup.length === 0 && <p className="muted">Aramayla eşleşen kalem yok.</p>}
          {byGroup.map(({ g, label, rows }) => (
            <details key={g} className="catalog-group" open>
              <summary><b>{label}</b><span className="muted"> · {rows.filter((r) => !r.is_general).length} kalem</span></summary>
              <table className="table-compact price-table">
                <thead>
                  <tr>
                    <th>Kalem</th><th>Poz</th><th className="num">Miktar</th><th>Birim</th>
                    {mode === 'material'
                      ? <><th>Marka</th><th className="num">Malzeme ₺/birim</th><th className="num">Malzeme tutarı ₺</th></>
                      : <><th className="num">İşçilik ₺/birim</th><th className="num" title="Adam-saat / birim">A-saat / birim</th><th className="num" title="Aynı anda çalışan kişi">Ekip</th><th className="num">İşçilik tutarı ₺</th></>}
                  </tr>
                </thead>
                <tbody>
                  {kindsOf(rows).flatMap((kind) => rows.filter((i) => i.kind === kind).map((i) => (
                    <tr key={i.key} className={i.is_general ? 'general' : ''}>
                      <td>
                        {i.is_general
                          ? <><b>{i.name.replace(' (genel)', '')}</b> <span className="muted hint">genel · tüm {i.kind_label.toLocaleLowerCase('tr-TR')} kalemleri</span></>
                          : <>{i.name}{i.recipe && <span className="badge recipe" style={{ marginLeft: 6 }}>reçete</span>}</>}
                      </td>
                      <td className="mono">{i.poz || ''}</td>
                      <td className="num muted">{fmtQ(i.quantity)}</td>
                      <td>{i.unit}</td>
                      {mode === 'material' && <>
                        <td><input className="wide" value={val(i, 'brand') as string} placeholder={i.is_general ? 'marka' : ''} onChange={(e) => set(i.key, 'brand', e.target.value)} /></td>
                        {numInput(i, 'unit_price')}
                      </>}
                      {mode === 'labor' && <>
                        {numInput(i, 'labor_price')}
                        {numInput(i, 'hours_per_unit', '0.001')}
                        {numInput(i, 'crew_size', '1')}
                      </>}
                      <td className="num muted">{lineTotal(i) == null ? '' : fmtQ(lineTotal(i))}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </details>
          ))}
          <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}>
            <button onClick={save} disabled={dirty === 0}>Fiyatları kaydet</button>
          </div>
        </div>
      )}
    </>
  )
}
