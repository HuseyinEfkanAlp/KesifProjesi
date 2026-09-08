import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Api } from '../api/client'
import type { Project } from '../types'
import Icon from '../components/Icon'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = () => Api.projects.list().then((items) => { setProjects(items); setError('') }).catch((e) => setError(e.message)).finally(() => setLoading(false))
  useEffect(() => { load() }, [])
  const remove = async (p: Project) => {
    if (!confirm(`"${p.name}" projesi ve tüm çizimleri silinsin mi?`)) return
    try { await Api.projects.remove(p.id); await load() } catch (e) { setError((e as Error).message) }
  }
  const totalDrawings = projects.reduce((sum, p) => sum + p.drawing_count, 0)
  const complete = projects.filter((p) => p.plan_check?.complete).length
  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">PROJE YÖNETİMİ</div><h1>Projeler</h1><p className="muted">Çizimleriniz, metrajlarınız ve maliyetleriniz tek bir yerde.</p></div><Link className="btn" to="/projects/new"><Icon name="plus" size={18} />Yeni proje</Link></div>
      {error && <div className="error" role="alert">{error} <button className="secondary small" onClick={load}>Tekrar dene</button></div>}
      <div className="project-stats">
        <div className="stat"><span className="stat-icon"><Icon name="folder" /></span><div><span className="stat-label">Toplam proje</span><strong>{loading || error ? '—' : projects.length.toLocaleString('tr-TR')}</strong></div></div>
        <div className="stat"><span className="stat-icon"><Icon name="layers" /></span><div><span className="stat-label">Yüklenen çizim</span><strong>{loading || error ? '—' : totalDrawings.toLocaleString('tr-TR')}</strong></div></div>
        <div className="stat"><span className="stat-icon green"><Icon name="check" /></span><div><span className="stat-label">Plan seti tamam</span><strong>{loading || error ? '—' : complete.toLocaleString('tr-TR')}</strong></div></div>
      </div>
      <section className="panel projects-panel" aria-label="Proje listesi">
        <div className="panel-heading"><h2>Tüm projeler <span className="count-pill">{projects.length}</span></h2><span className="muted">Proje portföyü</span></div>
        {loading ? <div className="empty-state" role="status">Projeler yükleniyor…</div> : !error && projects.length === 0 ? <div className="empty-state"><span className="empty-icon"><Icon name="folder" size={32} /></span><h2>İlk projenizi oluşturun</h2><p>Proje bilgilerini girin, DXF veya DWG planlarınızı yükleyin.</p><Link className="btn" to="/projects/new"><Icon name="plus" size={18} />Yeni proje</Link></div> : <ul className="project-list">{projects.map((p) => (
          <li key={p.id} className="project-item">
            <span className="project-icon"><Icon name="folder" size={24} /></span>
            <div className="project-info"><Link className="project-name" to={`/projects/${p.id}`}>{p.name}</Link>{p.description && <p className="project-description">{p.description}</p>}<div className="project-meta"><span>{p.drawing_count} çizim</span><span>Kat yüksekliği {p.storey_height} m</span><span>Döşeme {Math.round(p.slab_thickness * 100)} cm</span></div></div>
            <div className="project-status">{p.plan_check ? p.plan_check.complete ? <span className="status-badge complete">Plan seti tamam</span> : <span className="status-badge missing" title={p.plan_check.warnings.join('\n')}>{p.plan_check.missing_required} plan eksik</span> : <span className="status-badge">Plan seti bekleniyor</span>}</div>
            <div className="project-actions"><Link className="btn secondary-link" to={`/projects/${p.id}`}>Projeyi aç<Icon name="arrow" size={16} /></Link><button className="icon-button delete-button" onClick={() => remove(p)} aria-label={`${p.name} projesini sil`} title="Projeyi sil"><Icon name="trash" size={17} /></button></div>
          </li>
        ))}</ul>}
      </section>
    </>
  )
}
