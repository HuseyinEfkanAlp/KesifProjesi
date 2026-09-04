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

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      <div className="cards">
        <div className="card"><div className="label">Beton</div><div className="value">{money(cost.by_kind.beton ?? 0)}</div></div>
        <div className="card"><div className="label">Kalıp</div><div className="value">{money(cost.by_kind.kalip ?? 0)}</div></div>
        <div className="card"><div className="label">Demir</div><div className="value">{money(cost.by_kind.demir ?? 0)}</div></div>
        <div className="card"><div className="label">Genel toplam {cost.vat_rate ? `(KDV %${Math.round(cost.vat_rate * 100)} dahil)` : '(KDV hariç)'}</div><div className="value">{money(cost.grand_total)}</div></div>
      </div>
      {cost.missing_prices.length > 0 && (
        <div className="warn">Fiyatı girilmemiş kalemler var ({cost.missing_prices.length}); bunlar toplama 0 olarak girdi. <Link to={`/projects/${pid}/prices`}>Birim fiyatlara git</Link></div>
      )}
      <div className="panel">
        <div className="row between">
          <h3>Maliyet kalemleri</h3>
          <a className="btn" href={Api.cost.excelUrl(pid)}>Excel indir (metraj + maliyet)</a>
        </div>
        <table>
          <thead><tr><th>Kalem</th><th>Grup</th><th className="num">Miktar</th><th>Birim</th><th className="num">Birim fiyat</th><th className="num">Tutar</th><th>Fiyat kaynağı</th></tr></thead>
          <tbody>
            {cost.lines.map((l) => (
              <tr key={l.key}>
                <td>{l.kind_label}</td><td>{l.group_label}</td>
                <td className="num">{fmt(l.quantity, l.unit === 'kg' ? 0 : 2)}</td><td>{l.unit}</td>
                <td className="num">{fmt(l.unit_price)}</td><td className="num">{money(l.total)}</td>
                <td className={l.unit_price > 0 ? 'muted' : 'error'}>{l.price_source}</td>
              </tr>
            ))}
            <tr className="total"><td colSpan={5}>Ara toplam</td><td className="num">{money(cost.subtotal)}</td><td></td></tr>
            {cost.vat_rate > 0 && <tr><td colSpan={5}>KDV (%{Math.round(cost.vat_rate * 100)})</td><td className="num">{money(cost.vat)}</td><td></td></tr>}
            <tr className="total"><td colSpan={5}>GENEL TOPLAM</td><td className="num">{money(cost.grand_total)}</td><td></td></tr>
          </tbody>
        </table>
      </div>
    </>
  )
}
