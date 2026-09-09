import { useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { useParams } from 'react-router-dom'
import { Link } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import type { MaterialIn, MaterialOptions, MaterialPrice, PriceIn, PriceItem, Project, ProjectParams } from '../types'
import ProjectNav from './ProjectNav'

type Field = 'labor_price' | 'hours_per_unit' | 'crew_size'
type Edit = Partial<Record<Field, number | string>>
type MatEdit = { unit_price?: number | string; brand?: string }
type Mode = 'material' | 'labor'

const GROUP_ORDER = ['KABA', 'INCE', 'MEK', 'ELK', 'ALT']
/** Ürün seçimi: hangi eleman hangi malzemeden yapılıyor (malzeme fiyatı ürüne girilir) */
const CONCRETE_KEYS: Array<keyof ProjectParams> = ['concrete_class_foundation', 'concrete_class_column',
  'concrete_class_shear_wall', 'concrete_class_beam', 'concrete_class_slab']

export default function Prices() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [items, setItems] = useState<PriceItem[]>([])
  const [materials, setMaterials] = useState<MaterialPrice[]>([])
  const [opts, setOpts] = useState<MaterialOptions | null>(null)
  const [edited, setEdited] = useState<Record<string, Edit>>({})
  const [matEdited, setMatEdited] = useState<Record<string, MatEdit>>({})
  const [choice, setChoice] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showSpecific, setShowSpecific] = useState(true)
  const [mode, setMode] = useState<Mode>(() => { try { return (localStorage.getItem('prices.mode') as Mode) || 'material' } catch { return 'material' } })
  const [group, setGroup] = useState('')
  const [q, setQ] = useState('')
  const [openRow, setOpenRow] = useState('')

  const load = () => Promise.all([Api.projects.get(pid), Api.prices.list(pid), Api.materials.list(pid), Api.materials.options(pid)])
    .then(([p, it, ms, o]) => {
      setProject(p); setItems(it); setMaterials(ms); setOpts(o); setEdited({}); setMatEdited({})
      const pr = (p.params ?? {}) as Partial<ProjectParams>
      setChoice(Object.fromEntries([...CONCRETE_KEYS, 'concrete_class', 'lean_concrete_class', 'rebar_grade', 'formwork_material']
        .map((k) => [k, String(pr[k as keyof ProjectParams] ?? '')])))
    })
    .catch((e) => setError(e.message))
  useEffect(() => { load() }, [pid]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---- işçilik satırları
  const set = (key: string, field: Field, value: string) => {
    setSaved(false)
    setEdited({ ...edited, [key]: { ...(edited[key] || {}), [field]: value === '' ? '' : +value } })
  }
  const val = (i: PriceItem, field: Field) => {
    const e = edited[i.key]
    if (e && field in e) return e[field] as number | string
    if (!i.is_general && !(i.set_fields || []).includes(field) && !(i[field] > 0)) return ''   // girilmedi: boş
    return i[field]
  }
  // ---- ürün satırları
  const setMat = (key: string, field: keyof MatEdit, value: string) => {
    setSaved(false)
    const v = field === 'brand' ? value : (value === '' ? '' : +value)
    setMatEdited({ ...matEdited, [key]: { ...(matEdited[key] || {}), [field]: v } })
  }
  const matVal = (m: MaterialPrice, field: keyof MatEdit) => {
    const e = matEdited[m.key]
    if (e && field in e) return e[field] as number | string
    if (field === 'brand') return m.brand
    return m.unit_price > 0 ? m.unit_price : ''
  }

  const save = async () => {
    setError(''); setSaved(false); setBusy(true)
    try {
      if (Object.keys(matEdited).length) {
        const body: MaterialIn[] = Object.entries(matEdited).map(([key, e]) => ({
          key, ...(e.brand !== undefined ? { brand: e.brand } : {}),
          ...(e.unit_price !== undefined ? { unit_price: e.unit_price === '' ? 0 : +e.unit_price } : {}),
        }))
        await Api.materials.save(pid, body)
      }
      if (Object.keys(edited).length) {
        const body: PriceIn[] = Object.entries(edited).map(([key, e]) => {
          const out: Record<string, unknown> = { key }
          const clear: string[] = []
          for (const [f, v] of Object.entries(e)) {
            if (v === '') clear.push(f)
            else out[f] = v
          }
          if (clear.length) out.clear = clear
          return out as unknown as PriceIn
        })
        await Api.prices.save(pid, body)
      }
      await load(); setSaved(true)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const applyBook = async (overwrite: boolean) => {
    setError(''); setBusy(true)
    try {
      const r = await Api.pricebook.applyTo(pid, overwrite)
      await load()
      setError(r.materials + r.labor === 0 ? 'Fiyat bankasında bu projeye uyan fiyat bulunamadı.' : '')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const applyChoice = async () => {
    setError(''); setBusy(true)
    try {
      await Api.projects.patch(pid, { params: choice as unknown as ProjectParams })
      await load()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  if (!project || !opts) return <Loading error={error} />
  const hoursPerDay = project.params?.work_hours_per_day ?? 8
  const dirty = Object.keys(edited).length + Object.keys(matEdited).length
  const switchMode = (m: Mode) => { setMode(m); try { localStorage.setItem('prices.mode', m) } catch { /* yok say */ } }
  const qq = q.trim().toLocaleLowerCase('tr-TR')
  const has = (s: string) => !qq || s.toLocaleLowerCase('tr-TR').includes(qq)
  const fmtQ = (v: number | null) => v == null ? '' : v.toLocaleString('tr-TR', { maximumFractionDigits: v >= 100 ? 0 : 2 })

  // ---- gruplar (iki sekmede de iş grubu bazında)
  const rowsOf = (g: string) => mode === 'material'
    ? materials.filter((m) => m.work_group === g && (has(m.name) || m.items.some((x) => has(x.label))))
    : items.filter((i) => i.work_group === g && (showSpecific || i.is_general) && (has(i.name) || has(i.kind_label) || (i.poz || '').includes(qq)))
  const groupKeys = Array.from(new Set((mode === 'material' ? materials.map((m) => m.work_group) : items.map((i) => i.work_group)).filter(Boolean)))
    .sort((a, b) => (GROUP_ORDER.indexOf(a) === -1 ? 99 : GROUP_ORDER.indexOf(a)) - (GROUP_ORDER.indexOf(b) === -1 ? 99 : GROUP_ORDER.indexOf(b)))
  const shown = groupKeys.filter((g) => !group || g === group).map((g) => ({ g, rows: rowsOf(g) })).filter((x) => x.rows.length > 0)
  const groupLabel = (g: string) => (mode === 'material' ? materials.find((m) => m.work_group === g)?.work_group_label
    : items.find((i) => i.work_group === g)?.work_group_label) ?? g
  const countOf = (g: string) => mode === 'material' ? materials.filter((m) => m.work_group === g).length
    : items.filter((i) => i.work_group === g && !i.is_general).length

  const specific = items.filter((i) => !i.is_general)
  const pricedLabor = specific.filter((i) => i.labor_price > 0 || (i.set_fields || []).includes('labor_price')
    || items.some((g) => g.is_general && g.kind === i.kind && g.labor_price > 0)).length
  const pricedMat = materials.filter((m) => m.unit_price > 0).length
  const counter = mode === 'material' ? `${pricedMat} / ${materials.length} ürün fiyatlı` : `${pricedLabor} / ${specific.length} işçilik fiyatlı`

  const numInput = (i: PriceItem, field: Field, step = '0.01') => (
    <td className="num">
      <input type="number" min={0} step={step} className={`wide${edited[i.key] && field in edited[i.key] ? ' dirty' : ''}`} value={val(i, field) as number}
        placeholder={i.is_general ? '0' : 'genel'} title={i.is_general ? '' : 'Boş: türün genel satırı uygulanır. 0: bu kalemde yok (ör. işçilik yok)'}
        onChange={(e) => set(i.key, field, e.target.value)} />
    </td>
  )
  const select = (key: string, values: string[] | Record<string, string>, placeholder: string) => {
    const entries = Array.isArray(values) ? values.map((v) => [v, v] as [string, string]) : Object.entries(values)
    return (
      <select value={choice[key] ?? ''} onChange={(e) => setChoice({ ...choice, [key]: e.target.value })}>
        <option value="">{placeholder}</option>
        {entries.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
      </select>
    )
  }

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      {items.length === 0 && materials.length === 0 && (
        <div className="panel empty-state">
          <h2>Fiyatlanacak kalem yok</h2>
          <p>Önce plan yükleyin; keşif çıkınca malzeme fiyatı ürüne (C30/37 beton, Ø12 demir), işçilik fiyatı kaleme girilir.</p>
        </div>
      )}
      {(items.length > 0 || materials.length > 0) && (
        <div className="panel">
          <div className="row between sticky-bar">
            <div className="row" style={{ gap: 14 }}>
              <h3 style={{ margin: 0 }}>Birim fiyatlar</h3>
              <div className="chips" style={{ margin: 0 }}>
                <button className={`chip-btn${mode === 'material' ? ' on' : ''}`} onClick={() => switchMode('material')}>
                  Malzeme (ürün){Object.keys(matEdited).length > 0 && ' •'}
                </button>
                <button className={`chip-btn${mode === 'labor' ? ' on' : ''}`} onClick={() => switchMode('labor')}>
                  İşçilik{Object.keys(edited).length > 0 && ' •'}
                </button>
              </div>
              <span className="count-pill">{counter}</span>
              <input placeholder="ara: beton, ytong, kablo…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 200 }} />
              {mode === 'labor' && (
                <button className={`chip-btn${showSpecific ? '' : ' on'}`} onClick={() => setShowSpecific(!showSpecific)} title="Yalnız türün genel satırlarını göster">yalnız genel satırlar</button>
              )}
            </div>
            <div className="row">
              {saved && !dirty && <span className="ok">Kaydedildi</span>}
              {dirty > 0 && <span className="muted">{dirty} satır değişti</span>}
              <button onClick={save} disabled={dirty === 0 || busy}>Fiyatları kaydet</button>
            </div>
          </div>

          <div className="row" style={{ gap: 8, margin: '0 0 8px' }}>
            <button className="secondary" onClick={() => applyBook(false)} disabled={busy} title="Boş satırları genel fiyat listesinden doldur">Fiyat bankasından doldur</button>
            <button className="secondary" onClick={() => { if (confirm('Bu projedeki fiyatların üzerine fiyat bankasındaki güncel fiyatlar yazılsın mı?')) applyBook(true) }} disabled={busy}>Bankadaki fiyatlarla güncelle</button>
            <Link className="btn secondary-link" to="/pricebook">Fiyatlar ve tedarikçiler sayfası</Link>
          </div>

          <p className="muted hint">
            {mode === 'material'
              ? <>Malzeme fiyatı <b>ürüne</b> girilir: kolon, perde ve döşeme betonu aynı "Hazır beton C30/37" satırından fiyatlanır.
                Hangi elemanın hangi ürünü kullandığı aşağıdaki <b>ürün seçimi</b>nden değişir. Fiyatlar ₺/birim, KDV hariç.</>
              : <>İşçilik birim fiyatı (₺/birim), adam-saat / birim ve ekip kaleme girilir. Süre = miktar × adam-saat / (ekip × {hoursPerDay} saat/gün).
                Türün <b>genel</b> satırı boş bırakılan kalemlere uygulanır; malzeme ayrı sekmede.</>}
          </p>

          {mode === 'material' && (
            <details className="catalog-group" style={{ marginBottom: 10 }}>
              <summary><b>Ürün seçimi</b><span className="muted"> · beton sınıfı, donatı, kalıp — hangi elemanda ne kullanılıyor</span></summary>
              <div className="params-grid" style={{ marginTop: 8 }}>
                <label className="field">Genel beton sınıfı{select('concrete_class', opts.concrete_classes, 'C30/37')}</label>
                {CONCRETE_KEYS.map((k) => {
                  const t = String(k).replace('concrete_class_', '')
                  return <label className="field" key={k}>{opts.concrete_types[t] ?? t} betonu{select(k, opts.concrete_classes, 'genel sınıf')}</label>
                })}
                <label className="field">Grobeton{select('lean_concrete_class', opts.concrete_classes, 'C16/20')}</label>
                <label className="field">Donatı sınıfı{select('rebar_grade', opts.rebar_grades, 'B420C')}</label>
                <label className="field">Kalıp malzemesi{select('formwork_material', opts.formwork_materials, 'Plywood kalıp')}</label>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <button onClick={applyChoice} disabled={busy}>Ürün seçimini uygula</button>
                <span className="muted">Eleman tipi boş bırakılırsa genel sınıf kullanılır. Değişince ürün listesi yenilenir.</span>
              </div>
            </details>
          )}

          <div className="chips" style={{ margin: '6px 0 10px' }}>
            <button className={`chip-btn${group === '' ? ' on' : ''}`} onClick={() => setGroup('')}>Tümü</button>
            {groupKeys.map((g) => (
              <button key={g} className={`chip-btn${group === g ? ' on' : ''}`} onClick={() => setGroup(group === g ? '' : g)}>{groupLabel(g)} ({countOf(g)})</button>
            ))}
          </div>
          {shown.length === 0 && <p className="muted">Aramayla eşleşen kalem yok.</p>}

          {shown.map(({ g, rows }) => (
            <details key={g} className="catalog-group" open>
              <summary><b>{groupLabel(g)}</b><span className="muted"> · {mode === 'material' ? `${rows.length} ürün` : `${(rows as PriceItem[]).filter((r) => !r.is_general).length} kalem`}</span></summary>
              {mode === 'material' ? (
                <table className="table-compact price-table">
                  <thead>
                    <tr><th>Ürün</th><th>Birim</th><th className="num">Miktar</th><th>Marka</th><th className="num">₺ / birim</th><th className="num">Tutar ₺</th></tr>
                  </thead>
                  <tbody>
                    {(rows as MaterialPrice[]).map((m) => {
                      const price = matVal(m, 'unit_price')
                      const total = price === '' ? null : m.quantity * +price
                      const open = openRow === m.key
                      return (
                        <tr key={m.key}>
                          <td>
                            <b>{m.name}</b>
                            {(m.items.length > 1 || (m.items[0] && m.items[0].label !== m.name)) && (
                              <div className="muted hint" style={{ cursor: 'pointer' }} onClick={() => setOpenRow(open ? '' : m.key)}
                                title="Bu ürünü kullanan keşif kalemleri">
                                {open
                                  ? m.items.map((x) => `${x.label} (${fmtQ(x.quantity)} ${m.unit})`).join(' · ')
                                  : `${m.items.slice(0, 3).map((x) => x.label).join(', ')}${m.items.length > 3 ? ` +${m.items.length - 3}` : ''}`}
                              </div>
                            )}
                          </td>
                          <td>{m.unit}</td>
                          <td className="num muted">{fmtQ(m.quantity)}</td>
                          <td><input className="wide" value={matVal(m, 'brand') as string} placeholder="marka"
                            onChange={(e) => setMat(m.key, 'brand', e.target.value)} /></td>
                          <td className="num">
                            <input type="number" min={0} step="0.01" className={`wide${matEdited[m.key]?.unit_price !== undefined ? ' dirty' : ''}`}
                              value={price} placeholder="0" onChange={(e) => setMat(m.key, 'unit_price', e.target.value)} />
                          </td>
                          <td className="num muted">{total == null ? '' : fmt(total)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              ) : (
                <table className="table-compact price-table">
                  <thead>
                    <tr>
                      <th>Kalem</th><th>Poz</th><th className="num">Miktar</th><th>Birim</th>
                      <th className="num">İşçilik ₺/birim</th><th className="num" title="Adam-saat / birim">A-saat / birim</th>
                      <th className="num" title="Aynı anda çalışan kişi">Ekip</th><th className="num">İşçilik tutarı ₺</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(rows as PriceItem[]).map((i) => {
                      const v = val(i, 'labor_price')
                      const gen = items.find((x) => x.is_general && x.kind === i.kind)
                      const eff = v !== '' ? +v : (gen ? gen.labor_price : 0)
                      const total = i.quantity == null || i.is_general ? null : i.quantity * eff
                      return (
                        <tr key={i.key} className={i.is_general ? 'general' : ''}>
                          <td>
                            {i.is_general
                              ? <><b>{i.name.replace(' (genel)', '')}</b> <span className="muted hint">genel · tüm {i.kind_label.toLocaleLowerCase('tr-TR')} kalemleri</span></>
                              : <>{i.name}{i.recipe && <span className="badge recipe" style={{ marginLeft: 6 }}>reçete</span>}</>}
                          </td>
                          <td className="mono">{i.poz || ''}</td>
                          <td className="num muted">{fmtQ(i.quantity)}</td>
                          <td>{i.unit}</td>
                          {numInput(i, 'labor_price')}
                          {numInput(i, 'hours_per_unit', '0.001')}
                          {numInput(i, 'crew_size', '1')}
                          <td className="num muted">{total == null ? '' : fmt(total)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </details>
          ))}
          <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}>
            <button onClick={save} disabled={dirty === 0 || busy}>Fiyatları kaydet</button>
          </div>
        </div>
      )}
    </>
  )
}
