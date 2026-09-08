import { useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { useParams } from 'react-router-dom'
import { Api } from '../api/client'
import type { PriceIn, PriceItem, Project } from '../types'
import ProjectNav from './ProjectNav'

type Field = 'unit_price' | 'labor_price' | 'hours_per_unit' | 'crew_size' | 'brand'
type Edit = Partial<Record<Field, number | string>>

const DISC_ORDER = ['structural', 'architectural', 'electrical']

export default function Prices() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [items, setItems] = useState<PriceItem[]>([])
  const [edited, setEdited] = useState<Record<string, Edit>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [showSpecific, setShowSpecific] = useState(true)

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

  const discKeys = Array.from(new Set(items.map((i) => i.discipline)))
    .sort((a, b) => (DISC_ORDER.indexOf(a) === -1 ? 99 : DISC_ORDER.indexOf(a)) - (DISC_ORDER.indexOf(b) === -1 ? 99 : DISC_ORDER.indexOf(b)) || a.localeCompare(b))
  const byDisc = discKeys
    .map((d) => ({ d, label: items.find((i) => i.discipline === d)?.discipline_label ?? d, rows: items.filter((i) => i.discipline === d) }))
    .filter((g) => g.rows.length > 0)
  const kindsOf = (rows: PriceItem[]) => Array.from(new Set(rows.map((r) => r.kind)))

  const numInput = (i: PriceItem, field: Exclude<Field, 'brand'>, step = '0.01') => (
    <td className="num">
      <input type="number" min={0} step={step} className="wide" value={val(i, field) as number}
        onChange={(e) => set(i.key, field, e.target.value)} />
    </td>
  )

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <p className="muted">
          Her kalem için <b>malzeme</b> ve <b>işçilik</b> birim fiyatını, isteğe bağlı <b>marka</b>yı ve süre tahmini için
          <b> adam-saat / birim</b> ile <b>ekip</b> (aynı anda çalışan kişi) değerini girin. Türün <b>genel</b> satırı boş bırakılan
          özel satırlara uygulanır (özel satırda 0 ise genel değer kullanılır). Süre = miktar × adam-saat / (ekip × {hoursPerDay} saat/gün).
          Fiyatlar KDV hariç; KDV oranı ve günlük çalışma saati proje parametrelerinde.
        </p>
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="secondary small" onClick={() => setShowSpecific(!showSpecific)}>
            {showSpecific ? 'Yalnızca genel fiyatları göster' : 'Kaleme özel satırları da göster'}
          </button>
          <button onClick={save} disabled={Object.keys(edited).length === 0}>Fiyatları kaydet</button>
          {saved && <span style={{ color: 'var(--ok)' }}>Kaydedildi.</span>}
        </div>
        {byDisc.length === 0 && <p className="muted">Henüz keşif kalemi yok; önce çizim yükleyin.</p>}
        {byDisc.map(({ d, label, rows }) => (
          <div key={d}>
            <h2>{label}</h2>
            <table>
              <thead>
                <tr>
                  <th>Tür</th><th>Kalem</th><th>Birim</th><th>Marka</th>
                  <th className="num">Malzeme (₺/birim)</th><th className="num">İşçilik (₺/birim)</th>
                  <th className="num">Adam-saat / birim</th><th className="num">Ekip (kişi)</th>
                </tr>
              </thead>
              <tbody>
                {kindsOf(rows).flatMap((kind) => rows
                  .filter((i) => i.kind === kind && (showSpecific || i.is_general))
                  .map((i) => (
                    <tr key={i.key} className={i.is_general ? 'total' : ''}>
                      <td>{i.is_general ? i.name.replace(' (genel)', '') : ''}</td>
                      <td>{i.is_general ? <span className="muted">genel (tüm {i.name.replace(' (genel)', '').toLocaleLowerCase('tr-TR')} kalemleri)</span> : i.name}</td>
                      <td>{i.unit}</td>
                      <td><input className="wide" value={val(i, 'brand') as string} placeholder={i.is_general ? 'ör. Ytong' : ''} onChange={(e) => set(i.key, 'brand', e.target.value)} /></td>
                      {numInput(i, 'unit_price')}
                      {numInput(i, 'labor_price')}
                      {numInput(i, 'hours_per_unit', '0.001')}
                      {numInput(i, 'crew_size', '1')}
                    </tr>
                  )))}
              </tbody>
            </table>
          </div>
        ))}
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={save} disabled={Object.keys(edited).length === 0}>Fiyatları kaydet</button>
          {saved && <span style={{ color: 'var(--ok)' }}>Kaydedildi.</span>}
        </div>
      </div>
    </>
  )
}
