import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Api } from '../api/client'
import type { PlanCheck, Project } from '../types'
import PlanIntake from '../components/PlanIntake'
import PlanChecklist from '../components/PlanChecklist'

/**
 * Yeni proje sihirbazı: 1) ad ve temel parametreler, 2) planları yükle (ruhsat dosyasından paftalar ayrılır),
 * eksik plan listesi anlık güncellenir, 3) projeye geç.
 */
export default function NewProject() {
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [storeyHeight, setStoreyHeight] = useState(3.0)
  const [slab, setSlab] = useState(0.15)
  const [project, setProject] = useState<Project | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [check, setCheck] = useState<PlanCheck | null>(null)

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true); setError('')
    try {
      setProject(await Api.projects.create({ name: name.trim(), description, storey_height: storeyHeight, slab_thickness: slab }))
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const step = project ? 2 : 1
  return (
    <>
      <div className="row between">
        <h1>Yeni proje</h1>
        <Link to="/" className="muted">← Projeler</Link>
      </div>
      <ol className="steps">
        <li className={step === 1 ? 'active' : 'done'}>1. Proje bilgileri</li>
        <li className={step === 2 ? 'active' : ''}>2. Planları yükle</li>
        <li>3. Metraj, fiyat, maliyet</li>
      </ol>
      {error && <div className="error">{error}</div>}

      {!project && (
        <div className="panel">
          <form onSubmit={create}>
            <div className="row">
              <label className="field">Proje adı<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Örn. Ataşehir Konut Bloğu" style={{ width: 300 }} /></label>
              <label className="field">Açıklama<input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="ada / parsel, blok, işveren…" style={{ width: 300 }} /></label>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <label className="field">Kat yüksekliği H (m)<input type="number" step="0.05" value={storeyHeight} onChange={(e) => setStoreyHeight(+e.target.value)} /></label>
              <label className="field">Döşeme kalınlığı d (m)<input type="number" step="0.01" value={slab} onChange={(e) => setSlab(+e.target.value)} /></label>
              <span className="muted">Kat yüksekliği her plan için ayrıca girilebilir; diğer parametreler (KDV, demir oranı, duvar yüksekliği, fire) proje sayfasında.</span>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button type="submit" disabled={busy || !name.trim()}>{busy ? 'Oluşturuluyor...' : 'Oluştur ve planları yükle →'}</button>
            </div>
          </form>
        </div>
      )}

      {project && (
        <>
          <div className="panel">
            <h3>{project.name} <span className="muted">— planlarınızı yükleyin</span></h3>
            <PlanIntake projectId={project.id} storeyHeight={project.storey_height} onChanged={() => setRefresh((r) => r + 1)} />
          </div>
          <div className="panel">
            <PlanChecklist projectId={project.id} refreshKey={refresh} onLoaded={setCheck} />
          </div>
          <div className="panel row between">
            <span className="muted">
              {check?.complete
                ? 'Bütün gerekli planlar yüklendi.'
                : check ? `${check.missing_required} gerekli plan eksik; daha sonra proje sayfasından da yükleyebilirsiniz.` : ''}
            </span>
            <div className="row">
              <Link className="btn secondary-link" to={`/projects/${project.id}`}>Projeye git (çizimler, parametreler)</Link>
              <button onClick={() => nav(`/projects/${project.id}/quantities`)}>Metraja geç →</button>
            </div>
          </div>
        </>
      )}
    </>
  )
}
