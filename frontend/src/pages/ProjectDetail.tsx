import { useCallback, useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { Link, useParams } from 'react-router-dom'
import { Api, type DrawingPatch } from '../api/client'
import { DISCIPLINES, DRAWING_STATUS, ETYPE_LABELS, HEURISTIC_DISCIPLINES, STRUCTURAL_ETYPES, type CatalogItem, type Discipline, type Drawing, type Project, type ProjectParams } from '../types'
import Icon from '../components/Icon'
import PlanChecklist from '../components/PlanChecklist'
import PlanIntake from '../components/PlanIntake'
import SystemsPanel from '../components/SystemsPanel'
import { planTypeGroups, usePlanTypes } from '../hooks/usePlanTypes'
import ProjectNav from './ProjectNav'

const PARAM_FIELDS: Array<{ key: keyof ProjectParams; label: string; step: string; hint: string }> = [
  { key: 'wall_height', label: 'Duvar yüksekliği (m)', step: '0.05', hint: 'Boş: H − d' },
  { key: 'plaster_sides', label: 'Sıva yüzü', step: '1', hint: '0 = sıva yok' },
  { key: 'paint_sides', label: 'Boya yüzü', step: '1', hint: '' },
  { key: 'cable_drop', label: 'Kablo iniş payı (m/hat)', step: '0.5', hint: 'Her hatta eklenir' },
  { key: 'cable_waste_pct', label: 'Kablo fire (%)', step: '1', hint: '' },
  { key: 'tray_waste_pct', label: 'Tava fire (%)', step: '1', hint: '' },
  { key: 'work_hours_per_day', label: 'Günlük çalışma (saat)', step: '0.5', hint: 'Süre hesabı' },
]
const SARF_FIELDS: Array<{ key: keyof ProjectParams; label: string; step: string; hint: string }> = [
  { key: 'concrete_waste_pct', label: 'Beton fire (%)', step: '0.5', hint: '' },
  { key: 'rebar_waste_pct', label: 'Demir fire / bindirme (%)', step: '0.5', hint: '' },
  { key: 'tie_wire_kg_per_t', label: 'Bağ teli (kg / ton demir)', step: '0.5', hint: 'yaygın 6–10' },
  { key: 'plywood_sheet_m2', label: 'Plywood levha (m²)', step: '0.005', hint: '125×250 = 3.125' },
  { key: 'formwork_reuse', label: 'Kalıp kullanım sayısı', step: '1', hint: 'levha kaç kez kullanılır' },
  { key: 'formwork_oil_l_per_m2', label: 'Kalıp yağı (L / m²)', step: '0.01', hint: '' },
  { key: 'nails_kg_per_m2', label: 'Çivi / aksesuar (kg / m²)', step: '0.01', hint: '' },
]

export default function ProjectDetail() {
  const id = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [drawings, setDrawings] = useState<Drawing[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const planTypes = usePlanTypes()
  const planGroups = planTypeGroups(planTypes)
  const [facadeItems, setFacadeItems] = useState<CatalogItem[]>([])
  const [roofItems, setRoofItems] = useState<CatalogItem[]>([])
  useEffect(() => {
    Api.catalog.get().then((c) => {
      setFacadeItems(c.items.filter((i) => i.discipline === 'CEP' && i.measure === 'area' && i.code !== 'CEPHE_BRUT'))
      setRoofItems(c.items.filter((i) => i.discipline === 'CAT' && i.measure === 'area'))
    }).catch(() => {})
  }, [])

  // parametre formu
  const [params, setParams] = useState({ storey_height: 3, slab_thickness: 0.15, vat_rate: 0 })
  const [ratios, setRatios] = useState<Record<string, number>>({})
  const [dparams, setDparams] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    try {
      const [p, ds] = await Promise.all([Api.projects.get(id), Api.drawings.list(id)])
      setProject(p)
      setDrawings(ds)
      setParams({ storey_height: p.storey_height, slab_thickness: p.slab_thickness, vat_rate: p.vat_rate })
      setRatios(p.rebar_ratios)
      setDparams(Object.fromEntries(Object.entries(p.params ?? {}).map(([k, v]) => [k, v === null || v === undefined ? '' : String(v)])))
    } catch (e) { setError((e as Error).message) }
  }, [id])
  useEffect(() => { load() }, [load])

  const drawingsChanged = async () => { await load(); setRefresh((r) => r + 1) }

  const saveParams = async () => {
    setBusy(true); setError('')
    try {
      const cleaned: Record<string, number | null> = {}
      for (const [k, v] of Object.entries(dparams)) cleaned[k] = v === '' ? null : (['facade_system', 'roof_system', 'derived_off', 'finish_rooms'].includes(k) ? (v as unknown as number) : +v)
      await Api.projects.patch(id, { ...params, rebar_ratios: ratios, params: cleaned as unknown as ProjectParams })
      await load()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const patchDrawing = async (d: Drawing, body: DrawingPatch) => {
    setBusy(true)
    try { await Api.drawings.patch(d.id, body); await drawingsChanged() } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const removeDrawing = async (d: Drawing) => {
    if (!confirm(`"${d.label}" çizimi silinsin mi?`)) return
    await Api.drawings.remove(d.id)
    drawingsChanged()
  }

  if (!project) return <Loading error={error} />

  const disciplineOptions = (Object.keys(DISCIPLINES) as Discipline[]).map((d) => <option key={d} value={d}>{DISCIPLINES[d]}</option>)
  const planTypeOptions = (
    <>
      <option value="">— tanınmadı —</option>
      {planGroups.map((g) => (
        <optgroup key={g.code} label={g.label}>{g.types.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}</optgroup>
      ))}
    </>
  )

  const statusOf = (d: Drawing) => DRAWING_STATUS[d.status ?? (d.plan_type ? (d.element_count > 0 ? 'ok' : 'empty') : 'untyped')]
  const counts = { ok: 0, empty: 0, problem: 0, untyped: 0 }
  for (const d of drawings) counts[d.status ?? (d.plan_type ? (d.element_count > 0 ? 'ok' : 'empty') : 'untyped')] += 1

  return (
    <>
      <ProjectNav id={id} name={project.name} />
      {error && <div className="error">{error}</div>}

      {project.storey_height <= 0 && project.levels && project.levels.levels.length >= 2 && (
        <div className="info">
          <b>Kat yüksekliği çizimdeki kotlardan alındı:</b> {project.levels.effective.toLocaleString('tr-TR')} m ({project.levels.source}).
          Seviyeler: {project.levels.levels.map((v) => (v >= 0 ? '+' : '') + v.toFixed(2)).join(' · ')}; kat farkları: {project.levels.heights.map((v) => v.toFixed(2)).join(' · ')} m.
          Her paftanın kendi kotu ile hesaplanır; düzeltmek isterseniz <b>Metraj parametreleri</b>'nden H girin.
        </div>
      )}
      {project.storey_height <= 0 && !(project.levels && project.levels.levels.length >= 2) && (
        <div className="warn">
          <b>Kat yüksekliği girilmedi ve çizimlerde kot yazısı bulunamadı.</b> Duvar, sıva, boya ve kalıp iskelesi için 3,0 m varsayılıyor;
          <b> Metraj parametreleri</b>'nden kat yüksekliğini (H) girin ya da kotlu plan / kesit yükleyin.
        </div>
      )}
      {drawings.length === 0 && (
        <div className="panel empty-state">
          <span className="empty-icon"><Icon name="layers" size={32} /></span>
          <h2>Henüz çizim yok</h2>
          <p>Aşağıya DXF ya da DWG planlarınızı bırakın: pafta tipi başlıktan tanınır, metraj ve reçeteli keşif kendiliğinden çıkar.</p>
        </div>
      )}
      {drawings.length > 0 && (
        <div className="panel summary">
          <div className="row between">
            <h3 style={{ margin: 0 }}>Çizimlerden ne anlaşıldı</h3>
            <span className="muted">
              {drawings.length} pafta · <span className="ok">{counts.ok} okundu</span>
              {counts.problem > 0 && <> · <span className="bad">{counts.problem} sorunlu</span></>}
              {counts.empty > 0 && <> · {counts.empty} boş</>}
              {counts.untyped > 0 && <> · {counts.untyped} tipi seçilmedi</>}
            </span>
          </div>
          <table className="summary-table">
            <tbody>
              {drawings.map((d) => {
                const st = statusOf(d)
                const pt = planTypes.find((t) => t.code === d.plan_type)
                return (
                  <tr key={d.id}>
                    <td className="st"><span className={`dot ${st.cls}`} title={st.label} /></td>
                    <td className="name" title={d.filename}><Link to={`/projects/${id}/drawings/${d.id}`}>{d.label}</Link></td>
                    <td className="type muted">{pt ? pt.label : <span className="bad">tip seçilmedi</span>}</td>
                    <td className="found">{d.found || <span className="muted">{st.label === 'Okundu' ? `${d.element_count} eleman` : st.label.toLowerCase()}</span>}</td>
                    <td className="note" title={d.warnings.join('\n')}>{d.note || (d.warnings[0] ?? '')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid2">
        <div className="panel">
          <h3>Plan yükle</h3>
          <p className="muted">
            Plan tipi ve disiplin dosya adı / pafta başlığından tanınır; ruhsat projesi dosyasında paftalar ayrılır ve siz onaylarsınız.
            Yanlış tanındıysa aşağıdaki çizim listesinden plan tipini ve disiplini değiştirin.
          </p>
          <PlanIntake projectId={id} storeyHeight={params.storey_height} onChanged={drawingsChanged} compact />
        </div>

        <div className="panel">
          <h3>Metraj parametreleri</h3>
          <div className="row">
            <label className="field">Kat yüksekliği H (m)<input type="number" step="0.05" value={params.storey_height} onChange={(e) => setParams({ ...params, storey_height: +e.target.value })} /></label>
            <label className="field">Döşeme kalınlığı d (m)<input type="number" step="0.01" value={params.slab_thickness} onChange={(e) => setParams({ ...params, slab_thickness: +e.target.value })} /></label>
            <label className="field">KDV oranı (0.20 = %20)<input type="number" step="0.01" value={params.vat_rate} onChange={(e) => setParams({ ...params, vat_rate: +e.target.value })} /></label>
          </div>
          <div className="params-grid">
            {PARAM_FIELDS.map((f) => (
              <label className="field" key={f.key} title={f.hint}>{f.label}
                <input type="number" step={f.step} value={dparams[f.key] ?? ''} placeholder={f.hint}
                  onChange={(e) => setDparams({ ...dparams, [f.key]: e.target.value })} />
              </label>
            ))}
          </div>
          <details style={{ marginTop: 8 }}>
            <summary className="muted" style={{ cursor: 'pointer' }}>Cephe, çatı, şap / kaplama, demir oranları, sarf ve fire…</summary>
            <h3>Cephe</h3>
            <div className="row">
              <label className="field" title="Boş: görünüşte CEPHE_BRUT eşlenmişse o alan, yoksa kalıp planındaki kolon/perde dış hattı çevresi × kat yüksekliği">
                Brüt cephe alanı (m²)
                <input type="number" step="1" value={dparams.facade_gross_m2 ?? ''} placeholder="otomatik" onChange={(e) => setDparams({ ...dparams, facade_gross_m2: e.target.value })} />
              </label>
              <label className="field" title="Seçilirse miktarı net cephe alanı (brüt − cam) olan bir kalem üretilir; katmanlı sistemse bileşenleri sorulur">
                Cephe sistemi
                <select value={dparams.facade_system ?? ''} onChange={(e) => setDparams({ ...dparams, facade_system: e.target.value })}>
                  <option value="">— yok / görünüşten ölçülecek —</option>
                  {facadeItems.map((i) => <option key={i.code} value={i.code}>{i.name}{i.is_system ? ' (katmanlı)' : ''}</option>)}
                </select>
              </label>
            </div>
            <h3>Çatı ve türetilmiş kalemler</h3>
            <div className="row">
              <label className="field" title="Boş: çizimde ölçülen çatı kalemi, yoksa en üst kat planı oturumu">
                Çatı alanı (m²)
                <input type="number" step="1" value={dparams.roof_area_m2 ?? ''} placeholder="otomatik" onChange={(e) => setDparams({ ...dparams, roof_area_m2: e.target.value })} />
              </label>
              <label className="field" title="Boş: kesit / detay notlarındaki kanıttan (kenet / kiremit / teras)">
                Çatı sistemi
                <select value={dparams.roof_system ?? ''} onChange={(e) => setDparams({ ...dparams, roof_system: e.target.value })}>
                  <option value="">— notlardan / seçilmedi —</option>
                  {roofItems.map((i) => <option key={i.code} value={i.code}>{i.name}{i.is_system ? ' (katmanlı)' : ''}</option>)}
                </select>
              </label>
              <label className="field" title="Şap ve döşeme kaplaması yalnız bu mahal türlerine uygulanır (plandaki mahal alanı yazılarından). Boş: LOBİ, VİTRİN, GİRİŞ, HOL, KORİDOR, FUAYE">
                Şap / kaplama mahalleri
                <input style={{ width: 240 }} value={dparams.finish_rooms ?? ''} placeholder="LOBİ, VİTRİN, GİRİŞ, HOL, KORİDOR" onChange={(e) => setDparams({ ...dparams, finish_rooms: e.target.value })} />
              </label>
              <label className="field" title="Doluysa mahal yazıları kullanılmaz">Şap / kaplama alanı (m²)<input type="number" step="1" value={dparams.finish_area_m2 ?? ''} placeholder="mahallerden" onChange={(e) => setDparams({ ...dparams, finish_area_m2: e.target.value })} /></label>
              <label className="field">Şap kalınlığı (cm)<input type="number" step="0.5" value={dparams.screed_cm ?? ''} placeholder="5" onChange={(e) => setDparams({ ...dparams, screed_cm: e.target.value })} /></label>
              <label className="field">Grobeton (cm)<input type="number" step="1" value={dparams.lean_concrete_cm ?? ''} placeholder="10" onChange={(e) => setDparams({ ...dparams, lean_concrete_cm: e.target.value })} /></label>
            </div>
            <h3>Demir oranları (kg/m³ beton)</h3>
            <div className="row">
              {STRUCTURAL_ETYPES.map((k) => (
                <label className="field" key={k}>{ETYPE_LABELS[k]}<input type="number" value={ratios[k] ?? 0} onChange={(e) => setRatios({ ...ratios, [k]: +e.target.value })} /></label>
              ))}
            </div>
            <h3>Statik sarf ve fire (bağ teli, plywood, kalıp yağı, çivi)</h3>
            <div className="params-grid">
              {SARF_FIELDS.map((f) => (
                <label className="field" key={f.key} title={f.hint}>{f.label}
                  <input type="number" step={f.step} value={dparams[f.key] ?? ''} placeholder={f.hint}
                    onChange={(e) => setDparams({ ...dparams, [f.key]: e.target.value })} />
                </label>
              ))}
            </div>
          </details>
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={saveParams} disabled={busy}>Kaydet</button>
            <span className="muted">Duvar m² = uzunluk × duvar yüksekliği − kapı / pencere boşlukları; kablo m = hat + iniş payı + fire.</span>
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Çizimler</h3>
        {drawings.length === 0 && <p className="muted">Henüz çizim yüklenmedi.</p>}
        {drawings.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr><th>Plan</th><th>Plan tipi</th><th>Disiplin</th><th>Dosya</th><th>Birim</th><th className="num">Kat</th><th className="num">H (m)</th><th className="num">Eleman</th><th>Uyarı</th><th></th></tr>
              </thead>
              <tbody>
                {drawings.map((d) => (
                  <tr key={d.id}>
                    <td><input className="wide" defaultValue={d.label} onBlur={(e) => e.target.value !== d.label && patchDrawing(d, { label: e.target.value })} /></td>
                    <td>
                      <select value={d.plan_type} disabled={busy} className={`narrow${d.plan_type ? '' : ' unset'}`} title="Plan seti kontrolünde hangi paftayı karşıladığı"
                        onChange={(e) => patchDrawing(d, { plan_type: e.target.value })}>{planTypeOptions}</select>
                    </td>
                    <td>
                      <select value={d.discipline} disabled={busy} className="narrow" title="Değiştirilirse çizim yeniden analiz edilir"
                        onChange={(e) => patchDrawing(d, { discipline: e.target.value as Discipline })}>{disciplineOptions}</select>
                      {HEURISTIC_DISCIPLINES.filter((x) => x !== d.discipline && ((d.disciplines ?? []).includes(x) || (d.discipline_hints?.[x] ?? 0) > 0)).length > 0 && (
                        <div className="extra-disc">
                          {HEURISTIC_DISCIPLINES.filter((x) => x !== d.discipline).map((x) => {
                            const on = (d.disciplines ?? []).includes(x)
                            const hint = d.discipline_hints?.[x] ?? 0
                            if (!on && !hint) return null
                            const name = DISCIPLINES[x].split(' (')[0]
                            return (
                              <button key={x} type="button" disabled={busy} className={`chip-btn${on ? ' on' : ''}`}
                                title={on ? `${name} bu paftada da analiz ediliyor; kapatmak için tıklayın` : `Bu paftada ${name.toLowerCase()} katmanları da var (${hint} nesne); aynı paftada çizilmişse açın`}
                                onClick={() => patchDrawing(d, { disciplines: on ? (d.disciplines ?? []).filter((y) => y !== x) : [...(d.disciplines ?? []), x] })}>
                                {on ? '✓ ' : '+ '}{name}
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </td>
                    <td className="mono" title={d.filename}>{d.filename.split(' › ')[0]}</td>
                    <td>
                      <select value={d.unit_override ?? ''} title={d.unit_detected ? 'Birim çizim başlığından' : 'Birim yazı yüksekliklerinden tahmin edildi'}
                        onChange={(e) => patchDrawing(d, { unit_override: e.target.value })}>
                        <option value="">Oto ({d.unit})</option>
                        <option value="cm">cm</option><option value="mm">mm</option><option value="m">m</option>
                      </select>
                    </td>
                    <td className="num"><input type="number" min={1} defaultValue={d.storey_count} onBlur={(e) => +e.target.value !== d.storey_count && patchDrawing(d, { storey_count: +e.target.value })} /></td>
                    <td className="num">
                      <input type="number" step="0.01" placeholder={project.levels?.per_drawing[String(d.id)] ? `${project.levels.per_drawing[String(d.id)].height}` : `proje: ${params.storey_height}`} defaultValue={d.storey_height ?? ''}
                        title={project.levels?.per_drawing[String(d.id)] ? `Boş: ${project.levels.per_drawing[String(d.id)].height} m (${project.levels.per_drawing[String(d.id)].source})` : 'Boş bırakılırsa projenin kat yüksekliği kullanılır'}
                        onBlur={(e) => { const v = e.target.value ? +e.target.value : null; if (v !== d.storey_height) patchDrawing(d, { storey_height: v }) }} />
                    </td>
                    <td className="num">{d.element_count}</td>
                    <td>{d.warnings.length > 0 ? <span title={d.warnings.join('\n')}>⚠ {d.warnings.length}</span> : <span className="muted">-</span>}</td>
                    <td className="row">
                      <Link className="btn small" to={`/projects/${id}/drawings/${d.id}`}>Elemanlar</Link>
                      <button className="danger small" onClick={() => removeDrawing(d)}>Sil</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <details className="section">
        <summary>Plan seti kontrolü<span className="muted">hangi plan tipleri yüklendi, hangileri eksik</span></summary>
        <div className="panel"><PlanChecklist projectId={id} refreshKey={refresh} /></div>
      </details>

      <details className="section">
        <summary>Katmanlı sistemler ve türetilmiş kalemler<span className="muted">çatı / cephe bileşenleri, tamlık kontrolü</span></summary>
        <div className="panel"><SystemsPanel projectId={id} refreshKey={refresh} /></div>
      </details>
    </>
  )
}
