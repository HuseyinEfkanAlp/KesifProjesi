import { useCallback, useEffect, useState } from 'react'
import { Api, fmt } from '../api/client'
import type { SpaceBreakdown, SpaceRow } from '../types'

interface Props {
  projectId: number
  refreshKey: number
}

/**
 * Mahaller: mimari plandaki duvarlardan çıkarılan kapalı alanlar ve her mahalin kendi keşfi.
 * Daire / bağımsız bölüm bir GRUPtur: kendi satırında çocuklarının toplamını gösterir ("evde 5 kamera").
 */
export default function SpacesPanel({ projectId, refreshKey }: Props) {
  const [data, setData] = useState<SpaceBreakdown | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const load = useCallback(() => {
    Api.projects.spaces(projectId).then(setData).catch((e) => setError(e.message))
  }, [projectId])
  useEffect(() => { load() }, [load, refreshKey])

  if (error) return <div className="badge st-missing">Mahaller okunamadı: {error}</div>
  if (!data) return <div className="muted">Mahaller yükleniyor…</div>
  if (data.spaces.length === 0) {
    return (
      <div>
        <h3>Mahaller</h3>
        <div className="muted hint">{data.warnings[0] ?? 'Mahal bulunamadı.'} Mahal sınırı mimari plandaki duvar
          katmanlarından çıkarılır; mahal adı ("HOL 32 m²", "DAİRE 1") alanın içine yazılmış olmalıdır.</div>
      </div>
    )
  }

  const groups = data.spaces.filter((s) => s.kind === 'grup')
  const loose = data.spaces.filter((s) => s.kind !== 'grup' && !s.parent)
  const childrenOf = (g: SpaceRow) => data.spaces.filter((s) => s.parent === g.key)

  const itemRows = (rows: SpaceRow['items'], title: string) => (
    rows.length === 0 ? <div className="muted hint">{title}: kalem yok</div> : (
      <table className="summary-table">
        <thead><tr><th>{title}</th><th>Miktar</th><th>Birim</th></tr></thead>
        <tbody>{rows.map((i) => (
          <tr key={i.key}><td>{i.label}</td><td style={{ textAlign: 'right' }}>{fmt(i.quantity, 2)}</td><td>{i.unit}</td></tr>
        ))}</tbody>
      </table>
    )
  )

  const spaceBlock = (s: SpaceRow, isGroup = false) => (
    <div key={s.key} className="facade-info" style={{ marginTop: 6 }}>
      <b>{isGroup ? '🏠 ' : ''}{s.path || s.name}</b>{' '}
      <span className="muted">{fmt(s.area)} m²{s.label_area > 0 && Math.abs(s.label_area - s.area) > 0.5
        ? ` (yazıda ${fmt(s.label_area)} m²)` : ''} · {s.drawing}</span>{' '}
      <button className="link" onClick={() => setOpen({ ...open, [s.key]: !open[s.key] })}>
        {open[s.key] ? 'gizle' : 'kalemler'}
      </button>
      {open[s.key] && (
        <div style={{ marginTop: 4 }}>
          {itemRows(s.items, 'Bu mahalde')}
          {isGroup && s.total_items && s.total_items.length > 0 && (
            <div style={{ marginTop: 6 }}>{itemRows(s.total_items, 'Bağımsız bölüm toplamı (içindeki mahaller dahil)')}</div>
          )}
        </div>
      )}
    </div>
  )

  return (
    <div>
      <h3>Mahaller <span className="muted">({data.spaces.filter((s) => s.kind === 'mahal').length} mahal
        {groups.length > 0 ? `, ${groups.length} bağımsız bölüm` : ''})</span></h3>
      <div className="muted hint">Mahal sınırı mimari plandaki duvarlardan çıkarıldı; her kalem, elemanın düştüğü
        mahale sayıldı. Duvar / hat gibi mahal sınırında duran kalemler komşu mahaller arasında bölüşülür.</div>
      {data.warnings.map((w, i) => <div key={i} className="muted hint">⚠ {w}</div>)}
      {groups.map((g) => (
        <div key={g.key} style={{ marginTop: 10 }}>
          {spaceBlock(g, true)}
          <div style={{ marginLeft: 18 }}>{childrenOf(g).map((c) => spaceBlock(c))}</div>
        </div>
      ))}
      {loose.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <b className="muted">Bağımsız bölüme girmeyen mahaller</b>
          {loose.map((s) => spaceBlock(s))}
        </div>
      )}
      {data.unassigned.length > 0 && (
        <div className="facade-info" style={{ marginTop: 10 }}>
          <b>Mahale atanamayan kalemler</b> <span className="muted">({data.unassigned_reason})</span>
          <button className="link" onClick={() => setOpen({ ...open, __un: !open.__un })}>
            {open.__un ? 'gizle' : `${data.unassigned.length} kalem`}
          </button>
          {open.__un && itemRows(data.unassigned, 'Atanmamış')}
        </div>
      )}
    </div>
  )
}
