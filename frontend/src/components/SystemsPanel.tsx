import { useCallback, useEffect, useState } from 'react'
import { Api, fmt } from '../api/client'
import type { ComponentSource, ProjectSystems, SystemComponent } from '../types'

interface Props {
  projectId: number
  refreshKey: number
  onChanged?: () => void
}

const SOURCE_LABEL: Record<ComponentSource, string> = {
  project: 'Projede yazıyor', manual: 'Elle eklendi', default: 'Sistem varsayılanı', missing: 'PROJEDE YOK', excluded: 'Çıkarıldı',
}

/**
 * Katmanlı sistemler (kenet çatı, mantolama…): sistem miktarı çizimden, bileşenler çizim yazılarından.
 * Projede yazmayan bileşen için kullanıcıya sorulur: ekle (elle) ya da yok bırak. Özellik (kalınlık) düzenlenebilir.
 */
export default function SystemsPanel({ projectId, refreshKey, onChanged }: Props) {
  const [data, setData] = useState<ProjectSystems | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    Api.projects.systems(projectId).then(setData).catch((e) => setError(e.message))
  }, [projectId])
  useEffect(() => { load() }, [load, refreshKey])

  const decide = async (sys: string, comp: string, dec: { include?: boolean | null; spec?: string | null }) => {
    setBusy(true); setError('')
    try {
      setData(await Api.projects.setSystems(projectId, { [sys]: { [comp]: dec } }))
      onChanged?.()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Sistemler kontrol ediliyor...</p>
  const SOURCE = { measured: 'görünüşten ölçüldü', manual: 'elle girildi', estimated: 'kalıp planından tahmin', none: '' }
  const facade = data.facade && data.facade.gross > 0 ? (
    <div className="facade-info">
      <b>Cephe brüt alanı:</b> {fmt(data.facade.gross)} m² <span className="muted">({SOURCE[data.facade.source]})</span>
      {data.facade.glass > 0 && <> − cam {fmt(data.facade.glass)} m² = <b>net {fmt(data.facade.net)} m²</b></>}
      <div className="muted hint">{data.facade.detail}{data.facade.per_drawing.length > 0 && <> · {data.facade.per_drawing.map((d) => `${d.drawing}: çevre ${fmt(d.perimeter)} m × ${d.storey_height} m × ${d.storey_count} kat`).join('; ')}</>}
        {' '}Cephe sistemi (mantolama, kompozit…) proje parametrelerinden seçilir; miktarı net alandan gelir.</div>
    </div>
  ) : null
  if (data.systems.length === 0) {
    return (
      <div className="systems">
        <h3>Katmanlı sistemler <span className="muted" style={{ fontWeight: 400 }}>(kenet / kiremit / teras çatı, mantolama)</span></h3>
        {facade}
        <p className="muted">
          Bu projede henüz katmanlı sistem ölçülmedi. Çatı ya da cephe paftasında ilgili katmanı bir sistem kalemine eşleyin
          (Elemanlar sayfası, katman eşleme: örn. <code className="layer">ÇATI → Kenet çatı sistemi</code>); program çizim yazılarından
          bileşenleri (OSB, taşyünü, buhar kesici, mertek…) bulur, yazmayanları size sorar.
          {data.evidence_codes.length > 0 && <> Çizim yazılarında tanınan malzemeler: <code className="layer">{data.evidence_codes.join(', ')}</code>.</>}
        </p>
      </div>
    )
  }

  const specTitle = (c: SystemComponent) => c.evidence.length ? `Çizimde: ${c.evidence.join(' | ')}` : (c.default_spec ? `Sistem varsayılanı: ${c.default_spec}` : '')

  return (
    <div className="systems">
      <h3>
        Katmanlı sistemler{' '}
        {data.missing > 0
          ? <span className="badge st-missing">{data.missing} bileşen projede yazmıyor</span>
          : <span className="badge st-present">bileşenler tamam</span>}
      </h3>
      {facade}
      {data.warnings.length > 0 && (
        <div className="warn">
          <b>Projede yazmayan bileşenler var.</b> Sistem bu bileşenleri keşfe almadı. Projede var olduğunu biliyorsanız <i>Ekle</i> deyin,
          yoksa öyle bırakın.
          <ul>{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      {data.systems.map((sy) => (
        <div key={sy.key} className="system-block">
          <div className="row between">
            <div>
              <b>{sy.name}</b>{sy.spec && <span className="muted"> · {sy.spec}</span>}
              <span className="muted"> · {sy.discipline_label}</span>
              <span style={{ marginLeft: 10 }}>{fmt(sy.quantity)} {sy.unit}</span>
              {sy.system_evidence.length > 0 && <div className="muted hint">Çizimde: {sy.system_evidence.slice(0, 3).join(' | ')}</div>}
            </div>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="plan-table">
              <thead><tr><th>Bileşen</th><th>Durum</th><th>Özellik (kalınlık / tip)</th><th className="num">Çarpan</th><th className="num">Miktar</th><th>Birim</th><th>Karar</th></tr></thead>
              <tbody>
                {sy.components.map((c) => (
                  <tr key={c.code} className={c.source === 'missing' ? 'st-missing' : c.source === 'excluded' ? 'st-skipped' : ''}>
                    <td>{c.name}{c.evidence.length > 0 && <div className="muted hint">{c.evidence.slice(0, 2).join(' | ')}</div>}</td>
                    <td><span className={`badge st-${c.source === 'missing' ? 'missing' : c.source === 'excluded' ? 'skipped' : 'present'}`}>{SOURCE_LABEL[c.source]}</span></td>
                    <td>
                      <input className="wide" defaultValue={c.spec} placeholder={c.default_spec || '-'} title={specTitle(c)} disabled={busy}
                        onBlur={(e) => e.target.value.trim() !== c.spec && decide(sy.code, c.code, { spec: e.target.value })} />
                    </td>
                    <td className="num">× {c.factor}</td>
                    <td className="num">{c.include ? <b>{fmt(c.quantity, c.unit === 'adet' ? 0 : 2)}</b> : <span className="muted">-</span>}</td>
                    <td>{c.unit}</td>
                    <td className="row">
                      {!c.include && <button className="small" disabled={busy} onClick={() => decide(sy.code, c.code, { include: true })}>Ekle (projede var)</button>}
                      {c.include && <button className="small secondary" disabled={busy} onClick={() => decide(sy.code, c.code, { include: false })}>Çıkar</button>}
                      {(c.source === 'manual' || c.source === 'excluded') && (
                        <button className="small secondary" disabled={busy} title="Kararı sil, çizim kanıtına dön" onClick={() => decide(sy.code, c.code, {})}>Geri al</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <p className="muted hint">
        Sistem satırı keşifte görünür ama fiyatlanmaz; dahil edilen her bileşen ayrı iş kalemidir (miktar = sistem miktarı × çarpan) ve Birim Fiyatlar sayfasında fiyatlanır.
        Bileşen listesi ve çarpanlar Çizim standardı sayfasındaki katalogdan düzenlenir.
      </p>
    </div>
  )
}
