import { useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { Link, useParams } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import type { CostResult, Project } from '../types'
import ProjectNav from './ProjectNav'

export default function Cost() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [cost, setCost] = useState<CostResult | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([Api.projects.get(pid), Api.cost.get(pid)])
      .then(([p, c]) => { setProject(p); setCost(c.cost) })
      .catch((e) => setError(e.message))
  }, [pid])

  if (!project || !cost) return <Loading error={error} />
  const money = (v: number) => fmt(v) + ' ₺'
  const dur = cost.duration
  const priced = cost.by_material.filter((m) => m.unit_price > 0)
  const unpriced = cost.by_material.filter((m) => m.unit_price <= 0)

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      <div className="cards">
        <div className="card"><div className="label">Malzeme</div><div className="value">{money(cost.material_subtotal)}</div></div>
        <div className="card"><div className="label">İşçilik</div><div className="value">{money(cost.labor_subtotal)}</div></div>
        <div className="card"><div className="label">Genel toplam {cost.vat_rate ? `(KDV %${Math.round(cost.vat_rate * 100)} dahil)` : '(KDV hariç)'}</div><div className="value">{money(cost.grand_total)}</div></div>
        <div className="card">
          <div className="label">Süre (disiplinler paralel)</div>
          <div className="value">{fmt(dur.parallel_days, 1)} gün</div>
          <div className="muted">ardışık: {fmt(dur.sequential_days, 1)} gün · {fmt(dur.total_hours, 0)} adam-saat · {dur.hours_per_day} saat/gün</div>
        </div>
      </div>
      {(cost.missing_prices.length > 0 || dur.missing_rates.length > 0) && (
        <div className="warn">
          {cost.missing_materials.length > 0 && <div>Fiyatı girilmemiş {cost.missing_materials.length} ürün var; bunları kullanan {cost.missing_prices.length} kalem toplama 0 olarak girdi. </div>}
          {cost.missing_labor.length > 0 && <div>İşçilik fiyatı girilmemiş {cost.missing_labor.length} kalem var. </div>}
          {dur.missing_rates.length > 0 && <div>Adam-saat girilmemiş {dur.missing_rates.length} kalem süreye katılmadı. </div>}
          <Link to={`/projects/${pid}/prices`}>Birim fiyatlara git</Link>
        </div>
      )}

      <div className="panel">
        <h3>İş grubu bazında</h3>
        <table>
          <thead><tr><th>İş grubu</th><th className="num">Kalem</th><th className="num">Malzeme</th><th className="num">İşçilik</th><th className="num">Toplam</th><th className="num">Adam-saat</th><th className="num">Süre (gün)</th></tr></thead>
          <tbody>
            {cost.by_group.map((g) => (
              <tr key={g.group}>
                <td><b>{g.label}</b></td><td className="num">{g.lines}</td>
                <td className="num">{money(g.material)}</td><td className="num">{money(g.labor)}</td><td className="num"><b>{money(g.total)}</b></td>
                <td className="num">{fmt(g.hours, 0)}</td><td className="num">{fmt(g.days, 1)}</td>
              </tr>
            ))}
            <tr className="total"><td>TOPLAM</td><td className="num">{cost.lines.length}</td><td className="num">{money(cost.material_subtotal)}</td><td className="num">{money(cost.labor_subtotal)}</td><td className="num">{money(cost.material_subtotal + cost.labor_subtotal)}</td><td className="num">{fmt(dur.total_hours, 0)}</td><td className="num">{fmt(dur.sequential_days, 1)}</td></tr>
          </tbody>
        </table>
        <details style={{ marginTop: 8 }}>
          <summary className="muted">Disiplin bazında</summary>
          <table style={{ marginTop: 8 }}>
            <thead><tr><th>Disiplin</th><th className="num">Malzeme</th><th className="num">İşçilik</th><th className="num">Toplam</th><th className="num">Adam-saat</th><th className="num">Süre (gün)</th></tr></thead>
            <tbody>
              {cost.by_discipline.map((d) => (
                <tr key={d.discipline}>
                  <td><span className={`badge disc-${d.discipline.split(':')[0]}`}>{d.label.split(' (')[0]}</span></td>
                  <td className="num">{money(d.material)}</td><td className="num">{money(d.labor)}</td><td className="num">{money(d.total)}</td>
                  <td className="num">{fmt(d.hours, 0)}</td><td className="num">{fmt(d.days, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
        <p className="muted">Süre her kalem için miktar × adam-saat / (ekip × günlük saat). Disiplinler aynı anda çalışırsa toplam süre en uzun disiplin kadardır; tek ekip sırayla yaparsa kalemlerin toplamıdır.</p>
      </div>

      <div className="panel">
        <h3>Malzeme (ürün bazında)</h3>
        <table>
          <thead><tr><th>Ürün</th><th>Marka</th><th className="num">Miktar</th><th>Birim</th><th className="num">₺ / birim</th><th className="num">Tutar</th><th className="num">Kalem</th></tr></thead>
          <tbody>
            {priced.map((m) => (
              <tr key={m.key}>
                <td>{m.name}</td><td className="muted">{m.brand || '-'}</td>
                <td className="num">{fmt(m.quantity, m.unit === 'adet' || m.unit === 'kg' ? 0 : 2)}</td><td>{m.unit}</td>
                <td className="num">{fmt(m.unit_price)}</td>
                <td className="num"><b>{money(m.total)}</b></td><td className="num muted">{m.lines}</td>
              </tr>
            ))}
            {priced.length === 0 && <tr><td colSpan={7} className="muted">Henüz ürün fiyatı girilmedi.</td></tr>}
            <tr className="total"><td colSpan={5}>MALZEME TOPLAM</td><td className="num">{money(cost.material_subtotal)}</td><td></td></tr>
          </tbody>
        </table>
        {unpriced.length > 0 && (
          <details style={{ marginTop: 8 }}>
            <summary className="error">Fiyatı girilmemiş {unpriced.length} ürün (toplama 0 girdi)</summary>
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Ürün</th><th className="num">Miktar</th><th>Birim</th><th className="num">Kalem</th></tr></thead>
              <tbody>
                {unpriced.map((m) => (
                  <tr key={m.key}>
                    <td>{m.name}</td><td className="num">{fmt(m.quantity, m.unit === 'adet' || m.unit === 'kg' ? 0 : 2)}</td>
                    <td>{m.unit}</td><td className="num muted">{m.lines}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
        <p className="muted">Aynı ürünü kullanan bütün kalemler tek fiyattan hesaplanır. Ürün seçimi ve fiyatlar Birim Fiyatlar sayfasında.</p>
      </div>

      <div className="panel">
        <div className="row between">
          <h3>Maliyet kalemleri</h3>
          <a className="btn" href={Api.cost.excelUrl(pid)}>Excel indir (keşif + maliyet)</a>
        </div>
        <div style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>İş grubu</th><th>Poz</th><th>Tür</th><th>Kalem</th><th>Ürün (malzeme)</th><th className="num">Miktar</th><th>Birim</th>
                <th className="num">Malzeme ₺/birim</th><th className="num">İşçilik ₺/birim</th>
                <th className="num">Malzeme</th><th className="num">İşçilik</th><th className="num">Toplam</th>
                <th className="num">Süre (gün)</th><th>Kaynak</th>
              </tr>
            </thead>
            <tbody>
              {cost.lines.map((l) => (
                <tr key={l.key}>
                  <td>{l.work_group_label}{l.recipe ? <span className="badge recipe" style={{ marginLeft: 6 }}>reçete</span> : null}</td>
                  <td className="mono">{l.poz || <span className="muted">-</span>}</td>
                  <td>{l.kind_label}</td><td>{l.group_label}</td>
                  <td className="muted">{l.material_name || '-'}{l.brand ? ` · ${l.brand}` : ''}</td>
                  <td className="num">{fmt(l.quantity, l.unit === 'kg' || l.unit === 'adet' ? 0 : 2)}</td><td>{l.unit}</td>
                  <td className="num">{fmt(l.unit_price)}</td><td className="num">{fmt(l.labor_price)}</td>
                  <td className="num">{money(l.material_total)}</td><td className="num">{money(l.labor_total)}</td>
                  <td className="num"><b>{money(l.total)}</b></td>
                  <td className="num">{l.days ? fmt(l.days, 2) : <span className="muted">-</span>}</td>
                  <td className={l.unit_price > 0 ? 'muted' : 'error'}>{l.price_source}{l.labor_price > 0 ? '' : ' / işçilik yok'}</td>
                </tr>
              ))}
              <tr className="total"><td colSpan={8}>Malzeme ara toplam</td><td className="num">{money(cost.material_subtotal)}</td><td></td><td></td><td></td><td></td></tr>
              <tr className="total"><td colSpan={9}>İşçilik ara toplam</td><td className="num">{money(cost.labor_subtotal)}</td><td></td><td></td><td></td></tr>
              <tr className="total"><td colSpan={10}>Ara toplam</td><td className="num">{money(cost.subtotal)}</td><td></td><td></td></tr>
              {cost.vat_rate > 0 && <tr><td colSpan={10}>KDV (%{Math.round(cost.vat_rate * 100)})</td><td className="num">{money(cost.vat)}</td><td></td><td></td></tr>}
              <tr className="total"><td colSpan={10}>GENEL TOPLAM</td><td className="num">{money(cost.grand_total)}</td><td></td><td></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
