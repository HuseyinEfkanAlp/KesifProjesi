import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import { ETYPE_LABELS, type Project, type QuantityLine, type QuantitySummary } from '../types'
import ProjectNav from './ProjectNav'

export default function Quantities() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [summary, setSummary] = useState<QuantitySummary | null>(null)
  const [lines, setLines] = useState<QuantityLine[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([Api.projects.get(pid), Api.quantities(pid)])
      .then(([p, q]) => { setProject(p); setSummary(q.summary); setLines(q.lines) })
      .catch((e) => setError(e.message))
  }, [pid])

  if (!project || !summary) return <p className="muted">{error || 'Yükleniyor...'}</p>

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      <div className="cards">
        <div className="card"><div className="label">Toplam beton</div><div className="value">{fmt(summary.totals.concrete_m3)} m³</div></div>
        <div className="card"><div className="label">Toplam kalıp</div><div className="value">{fmt(summary.totals.formwork_m2)} m²</div></div>
        <div className="card"><div className="label">Toplam demir (oran ile)</div><div className="value">{fmt(summary.totals.rebar_kg, 0)} kg</div></div>
      </div>

      <div className="panel">
        <h3>Eleman grubuna göre özet</h3>
        <table>
          <thead><tr><th>Grup</th><th className="num">Adet (kat dahil)</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th></tr></thead>
          <tbody>
            {summary.groups.map((g) => (
              <tr key={g.key}><td><span className={`badge ${g.etype}`}>{g.label}</span></td><td className="num">{g.element_count}</td><td className="num">{fmt(g.concrete_m3, 3)}</td><td className="num">{fmt(g.formwork_m2)}</td><td className="num">{fmt(g.rebar_kg, 0)}</td></tr>
            ))}
            <tr className="total"><td>TOPLAM</td><td></td><td className="num">{fmt(summary.totals.concrete_m3, 3)}</td><td className="num">{fmt(summary.totals.formwork_m2)}</td><td className="num">{fmt(summary.totals.rebar_kg, 0)}</td></tr>
          </tbody>
        </table>
        <p className="muted">H = {project.storey_height} m, d = {Math.round(project.slab_thickness * 100)} cm. Temel kat sayısıyla çarpılmaz. Demir = beton × kg/m³ oranı (yaklaşık; detay paftası okuma sonraki sürümde).</p>
      </div>

      <div className="panel">
        <h3>Eleman bazında metraj ({lines.length} satır)</h3>
        <div style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr><th>Çizim</th><th>Tip</th><th>Ad</th><th className="num">b (cm)</th><th className="num">h (cm)</th><th className="num">Kal. (cm)</th><th className="num">Uzunluk (m)</th><th className="num">Alan (m²)</th><th className="num">Adet</th><th className="num">Kat</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th><th>Not</th></tr>
            </thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.element_id}>
                  <td>{l.drawing_id ? <Link to={`/projects/${pid}/drawings/${l.drawing_id}`}>{l.drawing}</Link> : l.drawing}</td>
                  <td><span className={`badge ${l.etype}`}>{ETYPE_LABELS[l.etype]}</span>{l.subtype && <span className="muted"> {l.subtype === 'raft' ? 'radye' : 'sürekli'}</span>}</td>
                  <td>{l.name ?? '-'}</td>
                  <td className="num">{l.b != null ? Math.round(l.b * 100) : '-'}</td>
                  <td className="num">{l.h != null ? Math.round(l.h * 100) : '-'}</td>
                  <td className="num">{l.thickness != null ? Math.round(l.thickness * 100) : '-'}</td>
                  <td className="num">{l.length ? fmt(l.length) : '-'}</td>
                  <td className="num">{l.area ? fmt(l.area, 3) : '-'}</td>
                  <td className="num">{l.count}</td>
                  <td className="num">×{l.multiplier}</td>
                  <td className="num">{fmt(l.total_concrete_m3, 3)}</td>
                  <td className="num">{fmt(l.total_formwork_m2)}</td>
                  <td className="num">{fmt(l.total_rebar_kg, 0)}</td>
                  <td className="muted">{[...l.notes, ...l.warnings].join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
