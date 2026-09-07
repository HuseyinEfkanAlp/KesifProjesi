import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Api } from '../api/client'
import type { Project } from '../types'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [error, setError] = useState('')

  const load = () => Api.projects.list().then(setProjects).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const remove = async (p: Project) => {
    if (!confirm(`"${p.name}" projesi ve tüm çizimleri silinsin mi?`)) return
    await Api.projects.remove(p.id)
    load()
  }

  return (
    <>
      <div className="row between">
        <h1>Projeler</h1>
        <Link className="btn" to="/projects/new">+ Yeni proje</Link>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="panel">
        {projects.length === 0 && (
          <p className="muted">Henüz proje yok. <Link to="/projects/new">Yeni proje</Link> açın: ad ve kat yüksekliğini girin, planlarınızı (ya da bütün ruhsat projesini) bırakın.</p>
        )}
        <ul className="list">
          {projects.map((p) => (
            <li key={p.id}>
              <div>
                <Link to={`/projects/${p.id}`}><strong>{p.name}</strong></Link>
                {p.plan_check && (p.plan_check.complete
                  ? <span className="badge st-present" style={{ marginLeft: 8 }}>plan seti tamam</span>
                  : <span className="badge st-missing" style={{ marginLeft: 8 }} title={p.plan_check.warnings.join('\n')}>{p.plan_check.missing_required} plan eksik</span>)}
                <div className="muted">{p.drawing_count} çizim · Kat yük. {p.storey_height} m · Döşeme {Math.round(p.slab_thickness * 100)} cm{p.description ? ` · ${p.description}` : ''}</div>
              </div>
              <div className="row">
                <Link className="btn" to={`/projects/${p.id}`}>Aç</Link>
                <button className="danger small" onClick={() => remove(p)}>Sil</button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
