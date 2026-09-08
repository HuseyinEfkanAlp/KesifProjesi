import { useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { useParams } from 'react-router-dom'
import { Api } from '../api/client'
import type { PriceIn, PriceItem, Project } from '../types'
import ProjectNav from './ProjectNav'

type Field = 'unit_price' | 'labor_price' | 'hours_per_unit' | 'crew_size' | 'brand'
type Edit = Partial<Record<Field, number | string>>

const GROUP_ORDER = ['KABA', 'INCE', 'MEK', 'ELK', 'ALT']

export default function Prices() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [items, setItems] = useState<PriceItem[]>([])
  const [edited, setEdited] = useState<Record<string, Edit>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [showSpecific, setShowSpecific] = useState(true)
  const [group, setGroup] = useState('')
  const [q, setQ] = useState('')

  const load = () => Promise.all([Api.projects.get(pid), Api.prices.list(pid)])
    .then(([p, it]) => { setProject(p); setItems(it); setEdited({}) })
    .catch((e) => setError(e.message))
  useEffect(() => { load() }, [pid]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key: string, field: Field, value: string) => {
    setSaved(false)
    const v: number | string = field === 'brand' ? value : (value === '' ? 0 : +value)
    setEdited({ ...edited, [key]: { ...(edited[key] || {}), [field]: v } })
  }
  const val = (i: PriceItem, field: Field) => {
    const e = edited[i.key]
    if (e && field in e) return e[field] as number | string
    return i[field]
  }

  const save = async () => {
    setError(''); setSaved(false)
    try {
      const body: PriceIn[] = Object.entries(edited).map(([key, e]) => ({ key, ...e } as PriceIn))
      await Api.prices.save(pid, body)
      await load(); setSaved(true)
    } catch (e) { setError((e as Error).message) }
  }

  if (!project) return <Loading error={error} />
  const hoursPerDay = project.params?.work_hours_per_day ?? 8
  const dirty = Object.keys(edited).length
  const specific = items.filter((i) => !i.is_general)
  const priced = specific.filter((i) => (i.unit_price > 0 || i.labor_price > 0) || items.some((g) => g.is_general && g.kind === i.kind && (g.unit_price > 0 || g.labor_price > 0))).length
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

  const numInput = (i: PriceItem, field: Exclude<Field, 'brand'>, step = '0.01') => {
    const v = val(i, field) as number
    return (
      <td className="num">
        <input type="number" min={0} step={step} className={`wide${edited[i.key] && field in edited[i.key] ? ' dirty' : ''}`} value={v}
          placeholder="0" onChange={(e) => set(i.key, field, e.target.value)} />
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
              <h3 style={{ margin: 0 }}>Birim fiyatlar <span className="count-pill">{priced} / {specific.length} fiyatlı</span></h3>
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
            Türün <b>genel</b> satırı, boş bırakılan özel satırlara uygulanır. Süre = miktar × adam-saat / (ekip × {hoursPerDay} saat/gün). Fiyatlar KDV hariç;
            KDV oranı ve günlük çalışma saati proje parametrelerinde. "Reçete" rozetli kalemler ana kalemden türetilen alt işlerdir (işçilik saatleri dahil).
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
                    <th>Kalem</th><th>Poz</th><th className="num">Miktar</th><th>Birim</th><th>Marka</th>
                    <th className="num">Malzeme ₺</th><th className="num">İşçilik ₺</th>
                    <th className="num" title="Adam-saat / birim">A-saat / birim</th><th className="num" title="Aynı anda çalışan kişi">Ekip</th>
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
                      <td><input className="wide" value={val(i, 'brand') as string} placeholder={i.is_general ? 'marka' : ''} onChange={(e) => set(i.key, 'brand', e.target.value)} /></td>
                      {numInput(i, 'unit_price')}
                      {numInput(i, 'labor_price')}
                      {numInput(i, 'hours_per_unit', '0.001')}
                      {numInput(i, 'crew_size', '1')}
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
