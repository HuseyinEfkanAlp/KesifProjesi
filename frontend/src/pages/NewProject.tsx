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
  const [storeyHeight, setStoreyHeight] = useState<number | ''>('')   // boş: kat yüksekliği plan / kesit kotlarından
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
      setProject(await Api.projects.create({ name: name.trim(), description, storey_height: storeyHeight === '' ? 0 : storeyHeight, slab_thickness: slab }))
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const step = project ? 2 : 1
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><Link to="/">← Projeler</Link></div>
          <h1>Yeni proje</h1>
          <p className="muted">Ad ve kat bilgilerini girin, planları bırakın; metraj, keşif ve maliyet kendiliğinden çıkar.</p>
        </div>
      </div>
      <ol className="steps">
        <li className={step === 1 ? 'active' : 'done'}>1. Proje bilgileri</li>
        <li className={step === 2 ? 'active' : ''}>2. Planları yükle</li>
        <li>3. Metraj, fiyat, maliyet</li>
      </ol>
      {error && <div className="error">{error}</div>}

      {!project && (
        <div className="panel new-project">
          <form onSubmit={create}>
            <h3 style={{ marginTop: 0 }}>Proje bilgileri</h3>
            <div className="form-grid">
              <label className="field span2">Proje adı<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Örn. Ataşehir Konut Bloğu" required /></label>
              <label className="field span2"><span>Açıklama <span className="muted">(isteğe bağlı)</span></span><input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="ada / parsel, blok, işveren…" /></label>
              <label className="field" title="Boş bırakın: kat yüksekliği plan ve kesitlerdeki kot yazılarından türetilir. Yalnız düzeltme için girin.">Kat yüksekliği H (m) <span className="muted">(boş = kotlardan)</span><input type="number" step="0.05" min={0} placeholder="kotlardan" value={storeyHeight} onChange={(e) => setStoreyHeight(e.target.value === '' ? '' : +e.target.value)} /></label>
              <label className="field">Döşeme kalınlığı d (m)<input type="number" step="0.01" min={0.05} value={slab} onChange={(e) => setSlab(+e.target.value)} /></label>
            </div>
            <p className="muted hint">Duvar yüksekliği H − d alınır; her plan için kat yüksekliği ayrıca girilebilir. KDV, demir oranı, fire ve sıva / boya yüz sayısı proje sayfasında.</p>
            <div className="row" style={{ marginTop: 14 }}>
              <button type="submit" disabled={busy || !name.trim()}>{busy ? 'Oluşturuluyor…' : 'Oluştur ve planları yükle'}</button>
              {!name.trim() && <span className="muted hint">Devam etmek için proje adı girin.</span>}
            </div>
          </form>
        </div>
      )}

      {project && (
        <>
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>{project.name} <span className="muted" style={{ fontWeight: 400 }}>· planları yükleyin</span></h3>
            <PlanIntake projectId={project.id} storeyHeight={project.storey_height} onChanged={() => setRefresh((r) => r + 1)} />
          </div>
          <details className="section" open={!!check && !check.complete}>
            <summary>Plan seti kontrolü<span className="muted">{check ? (check.complete ? 'tamam' : `${check.missing_required} gerekli plan eksik`) : ''}</span></summary>
            <div className="panel"><PlanChecklist projectId={project.id} refreshKey={refresh} onLoaded={setCheck} /></div>
          </details>
          <div className="panel row between">
            <span className="muted">
              {check?.complete
                ? 'Bütün gerekli planlar yüklendi.'
                : check ? `${check.missing_required} gerekli plan eksik; daha sonra proje sayfasından da yükleyebilirsiniz.` : ''}
            </span>
            <div className="row">
              <Link className="btn secondary-link" to={`/projects/${project.id}`}>Projeye git</Link>
              <button onClick={() => nav(`/projects/${project.id}/quantities`)}>Metraja geç</button>
            </div>
          </div>
        </>
      )}
    </>
  )
}
