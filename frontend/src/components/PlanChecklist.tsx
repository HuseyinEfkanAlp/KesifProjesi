import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Api } from '../api/client'
import type { PlanCheck, PlanLevel, PlanStatus } from '../types'

interface Props {
  projectId: number
  /** Değişince liste yeniden yüklenir (çizim eklendi / silindi) */
  refreshKey: number
  onLoaded?: (check: PlanCheck) => void
}

const STATUS_LABEL: Record<PlanStatus, string> = {
  present: 'Yüklendi', missing: 'EKSİK', skipped: 'Bu projede yok', optional_missing: 'İsteğe bağlı',
}
const LEVEL_LABEL: Record<PlanLevel, string> = { required: 'Gerekli', optional: 'İsteğe bağlı', skip: 'Bu projede yok' }

/**
 * Plan seti kontrol listesi: hangi paftalar yüklendi, hangileri eksik. Eksik zorunlu planlar için uyarı verir
 * ("Altyapı planı yüklenmedi"); kullanıcı bir tipi "bu projede yok" diye işaretleyebilir.
 */
export default function PlanChecklist({ projectId, refreshKey, onLoaded }: Props) {
  const [check, setCheck] = useState<PlanCheck | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(true)

  const load = useCallback(() => {
    Api.projects.planCheck(projectId).then((c) => { setCheck(c); onLoaded?.(c) }).catch((e) => setError(e.message))
  }, [projectId])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [load, refreshKey])

  const setLevel = async (code: string, level: PlanLevel) => {
    try {
      const c = await Api.projects.setPlanLevels(projectId, { [code]: level })
      setCheck(c); onLoaded?.(c)
    } catch (e) { setError((e as Error).message) }
  }

  if (error) return <div className="error">{error}</div>
  if (!check) return <p className="muted">Plan seti kontrol ediliyor...</p>

  return (
    <div className="plan-check">
      <div className="row between">
        <h3 style={{ margin: 0 }}>
          Plan seti kontrolü{' '}
          {check.complete
            ? <span className="badge st-present">tamam</span>
            : <span className="badge st-missing">{check.missing_required} eksik</span>}
          <span className="muted" style={{ fontWeight: 400, marginLeft: 8 }}>{check.present} plan tipi yüklendi</span>
        </h3>
        <button className="secondary small" onClick={() => setOpen(!open)}>{open ? 'Listeyi gizle' : 'Listeyi göster'}</button>
      </div>
      {check.warnings.length > 0 && (
        <div className="warn">
          <b>Eksik planlar var.</b> Yüklemediğiniz planların keşfi çıkmaz. Projede gerçekten yoksa satırında <i>Bu projede yok</i> seçin.
          <ul>{check.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      {open && (
        <div style={{ overflowX: 'auto' }}>
          <table className="plan-table">
            <thead><tr><th>Disiplin</th><th>Plan</th><th>Durum</th><th>Yüklenen çizimler</th><th>Gereklilik</th></tr></thead>
            <tbody>
              {check.groups.map((g) => g.types.map((t, i) => (
                <tr key={t.code} className={`st-${t.status}`}>
                  {i === 0 && <td rowSpan={g.types.length} className="group-cell"><b>{g.label}</b><div className="muted">{g.present} / {g.types.length}</div></td>}
                  <td title={t.hint}>{t.label}{t.hint && <div className="muted hint">{t.hint}</div>}</td>
                  <td><span className={`badge st-${t.status}`}>{STATUS_LABEL[t.status]}</span>{t.via && <div className="muted hint">{t.via} karşılıyor</div>}</td>
                  <td>
                    {t.drawings.map((d) => <Link key={d.id} to={`/projects/${projectId}/drawings/${d.id}`} className="chip">{d.label}</Link>)}
                  </td>
                  <td>
                    <select value={t.level} onChange={(e) => setLevel(t.code, e.target.value as PlanLevel)}>
                      {(Object.keys(LEVEL_LABEL) as PlanLevel[]).map((l) => <option key={l} value={l}>{LEVEL_LABEL[l]}</option>)}
                    </select>
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
