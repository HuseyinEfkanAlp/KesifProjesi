import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Api } from '../api/client'
import type { QualityReport, SelfCheck } from '../types'

/** Kontrol listesindeki tek tıkla düzeltmeler. Hepsi bir proje parametresini değiştirir; hesap yeniden çalışır. */
const FIXES: Record<string, { patch: Record<string, number>; done: string }> = {
  storey_height_auto: { patch: { storey_height: 0 }, done: 'Kat yükseklikleri artık kotlardan hesaplanıyor.' },
}

export default function QualitySummary({ report, projectId, onFixed }: {
  report: QualityReport | null; projectId: number; onFixed?: () => void
}) {
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  if (!report) return null
  const blockers = report.issues.filter((i) => i.severity === 'blocking')

  const applyFix = async (action: string) => {
    const fix = FIXES[action]
    if (!fix) return
    setBusy(action); setError('')
    try {
      await Api.projects.patch(projectId, fix.patch)
      setNote(fix.done)
      onFixed ? onFixed() : window.location.reload()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  return <section className="warn" aria-label="Metraj kontrol durumu">
    <div className="row between"><strong>Hesap taslağı · {report.label}</strong><Link to={`/projects/${projectId}`}>Çizimleri ve parametreleri kontrol et →</Link></div>
    <p>{report.notice}</p>
    <div>{blockers.length} eksik kontrolü · {report.issues.length - blockers.length} inceleme notu{report.estimated_rebar_kg > 0 && ` · ${(report.estimated_rebar_kg / 1000).toLocaleString('tr-TR', { maximumFractionDigits: 2 })} ton demir oranla tahmin`}</div>
    {note && <div className="hint" style={{ marginTop: 8 }}>{note}</div>}
    {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
    {report.selfcheck && <SelfCheckBlock sc={report.selfcheck} />}
    <details style={{ marginTop: 12 }}>
      <summary>Kontrol listesi ve hesap kabulleri</summary>
      <ul>{report.issues.map((issue, index) => <li key={index} style={{ marginBottom: 8 }}>
        <strong>{issue.severity === 'blocking' ? 'Eksik: ' : 'İncelenmeli: '}</strong>
        {issue.drawing_id && <><Link to={`/projects/${projectId}/drawings/${issue.drawing_id}`}>{issue.drawing}</Link> — </>}{issue.message}
        {issue.fix && <> <button type="button" className="link" disabled={!!busy} onClick={() => applyFix(issue.fix!.action)}>
          {busy === issue.fix.action ? 'Uygulanıyor…' : issue.fix.label}
        </button></>}
      </li>)}</ul>
      {report.assumptions.length > 0 && <div style={{ overflowX: 'auto', marginTop: 16 }}><table>
        <thead><tr><th>Hesap parametresi</th><th>Değer</th><th>Kaynak</th></tr></thead>
        <tbody>{report.assumptions.map((a) => <tr key={a.key}><td>{a.label}</td><td>{String(a.value)}</td><td>{a.source === 'user' ? 'Kullanıcı girişi' : a.source === 'drawing' ? 'Kotlardan türetildi' : 'Program varsayılanı'}</td></tr>)}</tbody>
      </table><p>Kullanıcı girişi, bağımsız olarak doğrulanmış ölçü anlamına gelmez.</p></div>}
    </details>
  </section>
}

const ISARET: Record<string, string> = { destekliyor: '✓', celisiyor: '✗', kararsiz: '–' }

/** Bağımsız kontroller: sonucu ikinci bir yoldan sınar. Çelişenler önce, dairesel olanlar sebebiyle birlikte. */
function SelfCheckBlock({ sc }: { sc: SelfCheck }) {
  const sira = { celisiyor: 0, destekliyor: 1, kararsiz: 2 } as const
  const checks = [...sc.checks].sort((a, b) => sira[a.sonuc] - sira[b.sonuc])
  return <div style={{ marginTop: 12 }}>
    <strong>Bağımsız kontroller</strong>
    <div>{sc.ozet}</div>
    <details style={{ marginTop: 6 }} open={sc.celisen > 0}>
      <summary>{sc.destekleyen} destekliyor · {sc.celisen} çelişiyor · {sc.kararsiz} karar veremedi</summary>
      <ul>{checks.map((c, i) => <li key={i} style={{ marginBottom: 6 }}>
        <strong>{ISARET[c.sonuc]} {c.ad} — {c.kapsam}:</strong> {c.aciklama}
        {c.olculen !== null && c.beklenen && <> <span className="muted">(ölçülen {c.olculen.toLocaleString('tr-TR')}, beklenen {c.beklenen})</span></>}
        <div className="muted hint">Bağımsızlık: {c.bagimsizlik}</div>
      </li>)}</ul>
      <p className="muted hint">{sc.notice}</p>
    </details>
  </div>
}
