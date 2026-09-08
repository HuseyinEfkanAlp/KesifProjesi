import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import { ETYPE_LABELS, SUBTYPE_LABELS, type Boq, type Project, type QuantityLine, type QuantitySummary } from '../types'
import ProjectNav from './ProjectNav'
import SystemsPanel from '../components/SystemsPanel'

export default function Quantities() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [summary, setSummary] = useState<QuantitySummary | null>(null)
  const [lines, setLines] = useState<QuantityLine[]>([])
  const [boq, setBoq] = useState<Boq | null>(null)
  const [error, setError] = useState('')
  const [showLines, setShowLines] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    Promise.all([Api.projects.get(pid), Api.quantities(pid)])
      .then(([p, q]) => { setProject(p); setSummary(q.summary); setLines(q.lines); setBoq(q.boq) })
      .catch((e) => setError(e.message))
  }, [pid, refresh])

  if (!project || !summary || !boq) return <p className="muted">{error || 'Yükleniyor...'}</p>
  const hasStructural = summary.groups.length > 0
  const wallH = project.params?.wall_height

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}

      {boq.items.length === 0 && <p className="muted">Henüz metraj yok; çizim yükleyin.</p>}

      <div className="panel">
        <SystemsPanel projectId={pid} refreshKey={0} onChanged={() => setRefresh((r) => r + 1)} />
      </div>

      {boq.by_group.map((g) => (
        <div className="panel" key={g.group}>
          <h3>{g.label} <span className="muted" style={{ fontWeight: 400 }}>· {g.items.length} kalem</span></h3>
          <table>
            <thead><tr><th>Poz</th><th>Disiplin</th><th>Tür</th><th>Kalem</th><th className="num">Miktar</th><th>Birim</th><th className="num">Adet / hat</th><th>Not</th></tr></thead>
            <tbody>
              {g.items.map((it) => (
                <tr key={it.key} className={it.detail?.system ? 'system-row' : ''}>
                  <td className="mono" title={it.poz_name}>{it.poz || <span className="muted">-</span>}</td>
                  <td><span className={`badge disc-${it.discipline.split(':')[0]}`}>{it.discipline_label.split(' (')[0]}</span></td>
                  <td>{it.kind_label}{it.detail?.system ? <span className="badge none" style={{ marginLeft: 6 }}>sistem</span> : null}{it.detail?.info ? <span className="badge none" style={{ marginLeft: 6 }}>bilgi</span> : null}</td>
                  <td>{it.label}{it.detail?.system_code && !it.detail?.system ? <span className="muted hint"> ← {String(it.detail.system_code)}</span> : null}</td>
                  <td className="num"><b>{fmt(it.quantity, it.unit === 'adet' || it.unit === 'kg' ? 0 : 2)}</b></td>
                  <td>{it.unit}</td>
                  <td className="num">{it.count ? fmt(it.count, 0) : '-'}</td>
                  <td className="muted">{it.notes.join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {g.group === 'INCE' && (
            <p className="muted">
              Duvar m² = uzunluk × duvar yüksekliği ({wallH ? `${wallH} m` : `H − d = ${(project.storey_height - project.slab_thickness).toFixed(2)} m`}) × kat sayısı − 0,10 m² ve üstü boşluklar.
              Sıva ve boya: tüm boşluklar düşülür, × yüz sayısı ({project.params?.plaster_sides ?? 2} / {project.params?.paint_sides ?? 2}). Parametreler proje sayfasında.
            </p>
          )}
          {g.group === 'ELK' && (
            <p className="muted">
              Kablo m = (hat uzunluğu + iniş payı {project.params?.cable_drop ?? 0} m) × kat sayısı × (1 + fire %{project.params?.cable_waste_pct ?? 0}).
              Tava fire %{project.params?.tray_waste_pct ?? 0}. Kesit / boyut etiketten ya da katman adından okunur; bilinmeyenler "belirsiz" grubunda toplanır.
            </p>
          )}
        </div>
      ))}
      {boq.items.length > 0 && (
        <details className="section">
          <summary>Ölçü kuralları<span className="muted">ÇŞB birim fiyat tariflerine göre; poz numarası katalogdan ya da varsayılan eşlemeden</span></summary>
          <div className="panel">
            <ul className="muted" style={{ margin: 0 }}>
              {Object.values(boq.rules).map((r) => <li key={r.text}>{r.text} <span className="hint">({r.source})</span></li>)}
            </ul>
            <p className="muted hint" style={{ marginBottom: 0 }}>Poz numarası boş olan kalemler için Standart sayfasındaki katalogda kaleme poz girin; sezgisel kalemlerde (beton, kalıp, gazbeton duvar, sıva, boya, demir) varsayılan ÇŞB pozları kullanılır.</p>
          </div>
        </details>
      )}

      {hasStructural && (
        <>
          <div className="cards">
            <div className="card"><div className="label">Toplam beton</div><div className="value">{fmt(summary.totals.concrete_m3)} m³</div></div>
            <div className="card"><div className="label">Toplam kalıp</div><div className="value">{fmt(summary.totals.formwork_m2)} m²</div></div>
            <div className="card"><div className="label">Toplam demir (oran ile)</div><div className="value">{fmt(summary.totals.rebar_kg, 0)} kg</div></div>
          </div>

          <div className="panel">
            <h3>Statik: kat / pafta bazında</h3>
            <div style={{ overflow: 'auto' }}>
              <table>
                <thead>
                  <tr><th>Plan</th><th>Kot</th><th className="num">Kolon m³</th><th className="num">Perde m³</th><th className="num">Kiriş m³</th><th className="num">Döşeme m³</th><th className="num">Temel m³</th><th className="num">Beton m³</th><th className="num">Kalıp m²</th><th className="num">Demir (oran) t</th><th className="num">Demir (tablo) t</th><th>Çap bazında (kg)</th></tr>
                </thead>
                <tbody>
                  {summary.by_drawing.map((r) => (
                    <tr key={r.drawing}>
                      <td>{r.drawing_id ? <Link to={`/projects/${pid}/drawings/${r.drawing_id}`}>{r.drawing}</Link> : r.drawing}</td>
                      <td>{r.kot ?? '-'}</td>
                      {(['column', 'shear_wall', 'beam', 'slab', 'foundation'] as const).map((et) => (
                        <td className="num" key={et}>{r.groups[et] ? fmt(r.groups[et].concrete_m3, 1) : '-'}</td>
                      ))}
                      <td className="num"><b>{r.concrete_m3 ? fmt(r.concrete_m3, 1) : '-'}</b></td>
                      <td className="num">{r.formwork_m2 ? fmt(r.formwork_m2, 0) : '-'}</td>
                      <td className="num">{r.rebar_kg ? fmt(r.rebar_kg / 1000, 1) : '-'}</td>
                      <td className="num">{r.rebar_table_kg ? <b>{fmt(r.rebar_table_kg / 1000, 1)}</b> : '-'}{r.rebar_target && <span className="muted"> ({ETYPE_LABELS[r.rebar_target as keyof typeof ETYPE_LABELS] ?? r.rebar_target})</span>}</td>
                      <td className="muted">{Object.entries(r.rebar_by_dia).map(([d, kg]) => `Ø${d}: ${fmt(kg, 0)}`).join(' · ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">
              Her kalıp planı o kottaki döşeme ve kirişleri, altındaki katın kolon ve perdelerini içerir. "Demir (oran)" beton × kg/m³ tahminidir;
              "Demir (tablo)" donatı paftasındaki metraj tablosundan okunan gerçek değerdir ve ilgili eleman tipinin oran tahminini geçersiz kılar.
            </p>
          </div>

          {summary.rebar_by_dia.length > 0 && (
            <div className="panel">
              <h3>Demir: çap bazında (donatı tablolarından, {fmt(summary.rebar_table_total_kg / 1000, 1)} t)</h3>
              <table>
                <thead><tr><th>Çap</th><th className="num">Toplam boy (m)</th><th className="num">Ağırlık (kg)</th><th className="num">Ton</th><th>Dağılım</th></tr></thead>
                <tbody>
                  {summary.rebar_by_dia.map((d) => (
                    <tr key={d.dia_mm}>
                      <td><b>Ø{d.dia_mm}</b></td>
                      <td className="num">{fmt(d.length_m, 0)}</td>
                      <td className="num">{fmt(d.weight_kg, 0)}</td>
                      <td className="num">{fmt(d.weight_kg / 1000, 2)}</td>
                      <td className="muted">{Object.entries(d.targets).map(([k, v]) => `${ETYPE_LABELS[k as keyof typeof ETYPE_LABELS] ?? k} ${fmt(v / 1000, 1)} t`).join(' · ')}</td>
                    </tr>
                  ))}
                  <tr className="total"><td>TOPLAM</td><td></td><td className="num">{fmt(summary.rebar_table_total_kg, 0)}</td><td className="num">{fmt(summary.rebar_table_total_kg / 1000, 2)}</td><td className="muted">{summary.rebar_ratio_total_kg > 0 ? `+ oranla tahmin edilen ${fmt(summary.rebar_ratio_total_kg / 1000, 1)} t (tablosu olmayan elemanlar)` : ''}</td></tr>
                </tbody>
              </table>
            </div>
          )}

          <div className="panel">
            <h3>Statik: eleman grubuna göre özet</h3>
            <table>
              <thead><tr><th>Grup</th><th className="num">Adet (kat dahil)</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th></tr></thead>
              <tbody>
                {summary.groups.map((g) => (
                  <tr key={g.key}><td><span className={`badge ${g.etype}`}>{g.label}</span></td><td className="num">{g.element_count}</td><td className="num">{fmt(g.concrete_m3, 3)}</td><td className="num">{fmt(g.formwork_m2)}</td><td className="num">{fmt(g.rebar_kg, 0)} <span className="muted">({g.rebar_source})</span></td></tr>
                ))}
                <tr className="total"><td>TOPLAM</td><td></td><td className="num">{fmt(summary.totals.concrete_m3, 3)}</td><td className="num">{fmt(summary.totals.formwork_m2)}</td><td className="num">{fmt(summary.totals.rebar_kg, 0)}</td></tr>
              </tbody>
            </table>
            <p className="muted">H = {project.storey_height} m, d = {Math.round(project.slab_thickness * 100)} cm. Temel kat sayısıyla çarpılmaz. Demir: "tablo" = donatı paftasından okundu, "oran" = beton × kg/m³ tahmini. Fire, bağ teli, plywood, kalıp yağı ve çivi keşif listesinde ayrı kalemlerdir.</p>
          </div>

          <div className="panel">
            <div className="row between">
              <h3>Statik: eleman bazında metraj ({lines.length} satır)</h3>
              <button className="secondary small" onClick={() => setShowLines(!showLines)}>{showLines ? 'Gizle' : 'Göster'}</button>
            </div>
            {showLines && (
              <div style={{ overflow: 'auto' }}>
                <table>
                  <thead>
                    <tr><th>Çizim</th><th>Tip</th><th>Ad</th><th className="num">b (cm)</th><th className="num">h (cm)</th><th className="num">Kal. (cm)</th><th className="num">Uzunluk (m)</th><th className="num">Alan (m²)</th><th className="num">Adet</th><th className="num">Kat</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th><th>Not</th></tr>
                  </thead>
                  <tbody>
                    {lines.map((l) => (
                      <tr key={l.element_id}>
                        <td>{l.drawing_id ? <Link to={`/projects/${pid}/drawings/${l.drawing_id}`}>{l.drawing}</Link> : l.drawing}</td>
                        <td><span className={`badge ${l.etype}`}>{ETYPE_LABELS[l.etype]}</span>{l.subtype && <span className="muted"> {SUBTYPE_LABELS[l.subtype] ?? l.subtype}</span>}</td>
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
            )}
          </div>
        </>
      )}
    </>
  )
}
