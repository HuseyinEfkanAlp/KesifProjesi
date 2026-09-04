import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Api } from '../api/client'
import type { PriceItem, Project } from '../types'
import ProjectNav from './ProjectNav'

const KIND_LABEL: Record<string, string> = { beton: 'Beton (₺/m³)', kalip: 'Kalıp (₺/m²)', demir: 'Demir (₺/kg)' }

export default function Prices() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [items, setItems] = useState<PriceItem[]>([])
  const [edited, setEdited] = useState<Record<string, number>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  const load = () => Promise.all([Api.projects.get(pid), Api.prices.list(pid)])
    .then(([p, it]) => { setProject(p); setItems(it); setEdited({}) })
    .catch((e) => setError(e.message))
  useEffect(() => { load() }, [pid]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setError(''); setSaved(false)
    try {
      await Api.prices.save(pid, Object.entries(edited).map(([key, unit_price]) => ({ key, unit_price })))
      await load(); setSaved(true)
    } catch (e) { setError((e as Error).message) }
  }

  if (!project) return <p className="muted">{error || 'Yükleniyor...'}</p>
  const kinds = ['beton', 'kalip', 'demir']

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <p className="muted">Her metraj türü için <b>genel</b> fiyat girin; belirli bir eleman grubu farklı fiyatlandırılıyorsa (örn. temel betonu) o satıra özel fiyat yazın. Özel fiyat 0 ise genel fiyat kullanılır. Fiyatlar KDV hariç; KDV oranı proje parametrelerinde.</p>
        <div className="grid2" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {kinds.map((kind) => (
            <div key={kind}>
              <h3>{KIND_LABEL[kind]}</h3>
              <table>
                <thead><tr><th>Kalem</th><th className="num">Birim fiyat (₺)</th></tr></thead>
                <tbody>
                  {items.filter((i) => i.key.startsWith(kind + ':')).map((i) => (
                    <tr key={i.key} className={i.key.endsWith(':*') ? 'total' : ''}>
                      <td>{i.name}</td>
                      <td className="num">
                        <input type="number" min={0} step="0.01" className="wide" value={edited[i.key] ?? i.unit_price}
                          onChange={(e) => { setSaved(false); setEdited({ ...edited, [i.key]: +e.target.value }) }} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={save} disabled={Object.keys(edited).length === 0}>Fiyatları kaydet</button>
          {saved && <span style={{ color: 'var(--ok)' }}>Kaydedildi.</span>}
        </div>
      </div>
    </>
  )
}
