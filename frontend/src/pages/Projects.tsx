import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Api } from '../api/client'
import type { Project } from '../types'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('')
  const [storeyHeight, setStoreyHeight] = useState(3.0)
  const [slab, setSlab] = useState(0.15)
  const [error, setError] = useState('')

  const load = () => Api.projects.list().then(setProjects).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await Api.projects.create({ name: name.trim(), storey_height: storeyHeight, slab_thickness: slab })
      setName('')
      load()
    } catch (err) { setError((err as Error).message) }
  }

  const remove = async (p: Project) => {
    if (!confirm(`"${p.name}" projesi ve tüm çizimleri silinsin mi?`)) return
    await Api.projects.remove(p.id)
    load()
  }

  return (
    <>
      <h1>Projeler</h1>
      <div className="panel">
        <h3>Yeni proje</h3>
        <form className="row" onSubmit={create}>
          <label className="field">Proje adı<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Örn. Ataşehir Konut Bloğu" style={{ width: 260 }} /></label>
          <label className="field">Kat yüksekliği (m)<input type="number" step="0.05" value={storeyHeight} onChange={(e) => setStoreyHeight(+e.target.value)} /></label>
          <label className="field">Döşeme kalınlığı (m)<input type="number" step="0.01" value={slab} onChange={(e) => setSlab(+e.target.value)} /></label>
          <button type="submit">Oluştur</button>
        </form>
        {error && <div className="error">{error}</div>}
      </div>
      <div className="panel">
        {projects.length === 0 && <p className="muted">Henüz proje yok.</p>}
        <ul className="list">
          {projects.map((p) => (
            <li key={p.id}>
              <div>
                <Link to={`/projects/${p.id}`}><strong>{p.name}</strong></Link>
                <div className="muted">{p.drawing_count} çizim · Kat yük. {p.storey_height} m · Döşeme {Math.round(p.slab_thickness * 100)} cm</div>
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
