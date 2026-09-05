import { useEffect, useState } from 'react'
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

  if (!project || !cost) return <p className="muted">{error || 'Yükleniyor...'}</p>
  const money = (v: number) => fmt(v) + ' ₺'
  const dur = cost.duration

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
          {cost.missing_prices.length > 0 && <div>Malzeme fiyatı girilmemiş {cost.missing_prices.length} kalem toplama 0 olarak girdi. </div>}
          {cost.missing_labor.length > 0 && <div>İşçilik fiyatı girilmemiş {cost.missing_labor.length} kalem var. </div>}
          {dur.missing_rates.length > 0 && <div>Adam-saat girilmemiş {dur.missing_rates.length} kalem süreye katılmadı. </div>}
          <Link to={`/projects/${pid}/prices`}>Birim fiyatlara git</Link>
        </div>
      )}

      <div className="panel">
        <h3>Disiplin bazında</h3>
        <table>
          <thead><tr><th>Disiplin</th><th className="num">Malzeme</th><th className="num">İşçilik</th><th className="num">Toplam</th><th className="num">Adam-saat</th><th className="num">Süre (gün)</th></tr></thead>
          <tbody>
            {cost.by_discipline.map((d) => (
              <tr key={d.discipline}>
                <td><span className={`badge disc-${d.discipline}`}>{d.label}</span></td>
                <td className="num">{money(d.material)}</td><td className="num">{money(d.labor)}</td><td className="num">{money(d.total)}</td>
                <td className="num">{fmt(d.hours, 0)}</td><td className="num">{fmt(d.days, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Süre her kalem için miktar × adam-saat / (ekip × günlük saat). Disiplinler aynı anda çalışırsa toplam süre en uzun disiplin kadardır; tek ekip sırayla yaparsa kalemlerin toplamıdır.</p>
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
                <th>Disiplin</th><th>Tür</th><th>Kalem</th><th>Marka</th><th className="num">Miktar</th><th>Birim</th>
                <th className="num">Malzeme ₺/birim</th><th className="num">İşçilik ₺/birim</th>
                <th className="num">Malzeme</th><th className="num">İşçilik</th><th className="num">Toplam</th>
                <th className="num">Süre (gün)</th><th>Kaynak</th>
              </tr>
            </thead>
            <tbody>
              {cost.lines.map((l) => (
                <tr key={l.key}>
                  <td><span className={`badge disc-${l.discipline}`}>{l.discipline_label}</span></td>
                  <td>{l.kind_label}</td><td>{l.group_label}</td><td className="muted">{l.brand || '-'}</td>
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
