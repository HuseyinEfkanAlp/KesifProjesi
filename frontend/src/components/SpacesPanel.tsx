import { Fragment, useCallback, useEffect, useState } from 'react'
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
  const childrenOf = (g: SpaceRow) => data.spaces.filter((s) => s.parent === g.key)
  /** Mahaller geldikleri paftaya (kata) göre gruplanır: "hangi katta hangi mahal" görünsün */
  const katlar = Array.from(data.spaces.reduce((m, s) => {
    m.set(s.drawing, [...(m.get(s.drawing) ?? []), s])
    return m
  }, new Map<string, SpaceRow[]>()).entries())

  /** Kalemleri iş grubuna göre ayırır: Kaba / İnce / Mekanik / Elektrik / Altyapı */
  const byGroup = (rows: { work_group_label?: string; work_group?: string }[]) => {
    const m = new Map<string, typeof rows>()
    rows.forEach((i) => {
      const k = i.work_group_label || i.work_group || 'Diğer'
      m.set(k, [...(m.get(k) ?? []), i])
    })
    return Array.from(m.entries())
  }

  const itemRows = (rows: SpaceRow['items'], title: string) => (
    rows.length === 0 ? <div className="muted hint">{title}: kalem yok</div> : (
      <table className="summary-table">
        <thead><tr><th>{title}</th><th>Miktar</th><th>Birim</th></tr></thead>
        <tbody>{byGroup(rows).map(([grup, liste]) => (
          <Fragment key={grup}>
            <tr><td colSpan={3} className="muted" style={{ fontWeight: 600, paddingTop: 6 }}>{grup}</td></tr>
            {(liste as SpaceRow['items']).map((i) => (
              <tr key={i.key}><td style={{ paddingLeft: 14 }}>{i.label}</td>
                <td style={{ textAlign: 'right' }}>{fmt(i.quantity, 2)}</td><td>{i.unit}</td></tr>
            ))}
          </Fragment>
        ))}</tbody>
      </table>
    )
  )

  const spaceBlock = (s: SpaceRow, isGroup = false) => (
    <div key={s.key} className="facade-info" style={{ marginTop: 6 }}>
      <b>{isGroup ? '🏠 ' : ''}{s.code ? `${s.code} · ` : ''}{s.path || s.name}</b>{' '}
      <span className="muted">{fmt(s.area)} m²{s.perimeter > 0 ? ` · çevre ${fmt(s.perimeter)} m` : ''}
        {s.label_area > 0 && Math.abs(s.label_area - s.area) > 0.5
          ? ` (yazıda ${fmt(s.label_area)} m²)` : ''} · {s.drawing}</span>{' '}
        <span className={`chip${s.area_source === 'drawing' ? '' : ' st-missing'}`}>
          {s.area_source === 'drawing' ? 'sınır çizimden ölçüldü'
            : s.area_source === 'label' ? 'yalnız mahal yazısından' : 'sınır var, yazıda alan yok'}
        </span>{' '}
      <button className="link" onClick={() => setOpen({ ...open, [s.key]: !open[s.key] })}>
        {open[s.key] ? 'gizle' : 'kalemler'}
      </button>
      {open[s.key] && (
        <div style={{ marginTop: 4 }}>
          {itemRows(s.items, 'Bu mahalde ölçülen')}
          {(s.derived ?? []).length > 0 && (
            <table className="summary-table" style={{ marginTop: 6 }}>
              <thead><tr><th>Mahalden türetilen</th><th>Miktar</th><th>Birim</th><th>Nereden</th></tr></thead>
              <tbody>{s.derived.map((i) => (
                <tr key={i.key}><td>{i.label}</td><td style={{ textAlign: 'right' }}>{fmt(i.quantity, 2)}</td>
                  <td>{i.unit}</td><td className="muted">{i.note}</td></tr>
              ))}</tbody>
            </table>
          )}
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
        {groups.length > 0 ? `, ${groups.length} bağımsız bölüm` : ''})</span>{' '}
        <a className="btn secondary-link" style={{ fontSize: 12, padding: '2px 10px' }}
           href={Api.cost.spacesExcelUrl(projectId)}>Mahal metrajı (Excel)</a></h3>
      <div className="muted hint">Mahal sınırı mimarın alan çizgisinden, yoksa duvarlardan çıkarılır ve
        mahal yazısındaki alanla doğrulanır. Sınırı doğrulanan mahalde sıva / boya çevreden ÖLÇÜLÜR.
        mahale sayıldı. Duvar / hat gibi mahal sınırında duran kalemler komşu mahaller arasında bölüşülür.</div>
      {(data.alignment ?? []).length > 0 && (
        <div className="hint" style={{ marginTop: 4 }}>
          <b>Paftalar:</b>{' '}
          {data.alignment.map((a, i) => (
            <span key={i} className={`chip${a.hit < a.total ? ' st-missing' : ''}`}
                  title={`${a.how}${a.dx || a.dy ? ` · kayma (${a.dx}, ${a.dy}) m` : ''}`}>
              {a.drawing} → {a.to} <span className="muted">({a.hit}/{a.total} eleman mahale düştü)</span>
            </span>
          ))}
        </div>
      )}
      {data.warnings.map((w, i) => <div key={i} className="muted hint">⚠ {w}</div>)}
      {katlar.map(([kat, liste]) => (
        <div key={kat} style={{ marginTop: 14 }}>
          <div style={{ borderBottom: '2px solid #dce3ee', paddingBottom: 2, marginBottom: 4 }}>
            <b>{kat}</b> <span className="muted">({liste.length} mahal · {fmt(liste.reduce((t, s) => t + s.area, 0))} m²)</span>
          </div>
          {liste.filter((s) => s.kind === 'grup').map((g) => (
            <div key={g.key}>
              {spaceBlock(g, true)}
              <div style={{ marginLeft: 18 }}>{childrenOf(g).map((c) => spaceBlock(c))}</div>
            </div>
          ))}
          {liste.filter((s) => s.kind !== 'grup' && !s.parent).map((s) => spaceBlock(s))}
        </div>
      ))}
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
