import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Api, type DrawingPatch, type SheetPick } from '../api/client'
import { ETYPE_LABELS, isSheetSelection, type Drawing, type EType, type Project, type SheetInfo, type SheetSelection } from '../types'
import ProjectNav from './ProjectNav'

interface PickState { checked: boolean; label: string; storey: number; height: string }

/** Kalıp planı paftaları önceden seçili gelir; donatı / detay / aplikasyon paftaları metraja girmez. */
const isFormworkTitle = (title: string) => {
  const t = title.toLocaleUpperCase('tr-TR')
  return t.includes('KALIP') && !t.includes('DONATI') && !t.includes('DETAY')
}
/** Ana başlık yanlış yazılmış olabilir (ör. "1.KAT DONATI PLANI" antetli kalıp planı); paftadaki diğer başlıklara da bakılır. */
const looksLikeFormworkPlan = (s: SheetInfo) => isFormworkTitle(s.title) || (s.titles ?? []).some(isFormworkTitle)

export default function ProjectDetail() {
  const id = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [drawings, setDrawings] = useState<Drawing[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // yükleme formu
  const [file, setFile] = useState<File | null>(null)
  const [label, setLabel] = useState('')
  const [storeyCount, setStoreyCount] = useState(1)
  const [unit, setUnit] = useState('')

  // pafta seçimi (çok paftalı dosya)
  const [picker, setPicker] = useState<SheetSelection | null>(null)
  const [picks, setPicks] = useState<Record<number, PickState>>({})
  const [showAllSheets, setShowAllSheets] = useState(false)

  // parametre formu
  const [params, setParams] = useState({ storey_height: 3, slab_thickness: 0.15, vat_rate: 0 })
  const [ratios, setRatios] = useState<Record<string, number>>({})

  const load = useCallback(async () => {
    try {
      const [p, ds] = await Promise.all([Api.projects.get(id), Api.drawings.list(id)])
      setProject(p)
      setDrawings(ds)
      setParams({ storey_height: p.storey_height, slab_thickness: p.slab_thickness, vat_rate: p.vat_rate })
      setRatios(p.rebar_ratios)
    } catch (e) { setError((e as Error).message) }
  }, [id])
  useEffect(() => { load() }, [load])

  const resetUploadForm = () => {
    setFile(null); setLabel(''); setStoreyCount(1); setUnit('')
    const input = document.getElementById('dxf-input') as HTMLInputElement | null
    if (input) input.value = ''
  }

  const upload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return
    setBusy(true); setError('')
    try {
      const res = await Api.drawings.upload(id, file, label, storeyCount, unit)
      if (isSheetSelection(res)) {
        const init: Record<number, PickState> = {}
        for (const s of res.sheets) {
          const alt = (s.titles ?? []).find(isFormworkTitle)
          init[s.index] = { checked: looksLikeFormworkPlan(s), label: isFormworkTitle(s.title) ? s.title : (alt ?? s.title), storey: 1, height: '' }
        }
        setPicks(init)
        setPicker(res)
        setShowAllSheets(false)
      } else {
        resetUploadForm()
        await load()
      }
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const addSheets = async (whole = false) => {
    if (!picker) return
    const sheets: SheetPick[] = whole ? [] : Object.entries(picks)
      .filter(([, p]) => p.checked)
      .map(([idx, p]) => ({ index: Number(idx), label: p.label, storey_count: p.storey, storey_height: p.height ? +p.height : null }))
    if (!whole && sheets.length === 0) { setError('En az bir pafta seçin'); return }
    setBusy(true); setError('')
    try {
      await Api.drawings.fromSource(id, picker.source.token, sheets, unit, whole)
      setPicker(null)
      resetUploadForm()
      await load()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const saveParams = async () => {
    setBusy(true); setError('')
    try {
      await Api.projects.patch(id, { ...params, rebar_ratios: ratios })
      await load()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  const patchDrawing = async (d: Drawing, body: DrawingPatch) => {
    try { await Api.drawings.patch(d.id, body); await load() } catch (err) { setError((err as Error).message) }
  }

  const removeDrawing = async (d: Drawing) => {
    if (!confirm(`"${d.label}" çizimi silinsin mi?`)) return
    await Api.drawings.remove(d.id)
    load()
  }

  if (!project) return <p className="muted">{error || 'Yükleniyor...'}</p>

  const selectedCount = Object.values(picks).filter((p) => p.checked).length
  const visibleSheets = picker
    ? picker.sheets.filter((s) => showAllSheets || looksLikeFormworkPlan(s) || picks[s.index]?.checked)
    : []

  return (
    <>
      <ProjectNav id={id} name={project.name} />
      {error && <div className="error">{error}</div>}

      {picker && (
        <div className="panel">
          <h3>Pafta seç — {picker.source.filename} ({picker.source.size_mb} MB, {picker.sheets.length} pafta)</h3>
          <p className="muted">
            Dosyada birden çok pafta var. Metraja girecek <b>kalıp planlarını</b> seçin; her pafta ayrı plan olarak kırpılıp analiz edilir.
            Donatı, detay ve aplikasyon paftaları gerekmez. Kalıp planı olduğu anlaşılan paftalar önceden işaretlendi.
          </p>
          <div className="row" style={{ marginBottom: 8 }}>
            <button className="secondary small" onClick={() => setShowAllSheets(!showAllSheets)}>
              {showAllSheets ? 'Yalnızca kalıp planlarını göster' : `Tüm paftaları göster (${picker.sheets.length})`}
            </button>
            <button className="secondary small" onClick={() => setPicks(Object.fromEntries(Object.entries(picks).map(([k, p]) => [k, { ...p, checked: false }])))}>Seçimi temizle</button>
          </div>
          <table>
            <thead>
              <tr><th></th><th>Pafta başlığı</th><th className="num">Nesne</th><th>Plan adı (metrajda görünecek)</th><th className="num">Kaç kat temsil ediyor</th><th className="num">Kat yüksekliği H (m)</th></tr>
            </thead>
            <tbody>
              {visibleSheets.map((s) => {
                const p = picks[s.index]
                const alt = (s.titles ?? []).filter(isFormworkTitle).find((t) => t !== s.title)
                return (
                  <tr key={s.index} className={p?.checked ? 'selected' : ''}>
                    <td><input type="checkbox" checked={!!p?.checked} onChange={(e) => setPicks({ ...picks, [s.index]: { ...p, checked: e.target.checked } })} /></td>
                    <td>
                      {s.title}{!s.titled && <span className="muted"> (başlık bulunamadı)</span>}
                      {alt && <div className="muted" style={{ fontSize: 12 }}>paftada: {alt}</div>}
                    </td>
                    <td className="num">{s.entity_count.toLocaleString('tr-TR')}</td>
                    <td><input className="wide" value={p?.label ?? ''} onChange={(e) => setPicks({ ...picks, [s.index]: { ...p, label: e.target.value } })} disabled={!p?.checked} /></td>
                    <td className="num"><input type="number" min={1} value={p?.storey ?? 1} onChange={(e) => setPicks({ ...picks, [s.index]: { ...p, storey: Math.max(1, +e.target.value) } })} disabled={!p?.checked} /></td>
                    <td className="num"><input type="number" step="0.01" placeholder={`proje: ${params.storey_height}`} value={p?.height ?? ''} onChange={(e) => setPicks({ ...picks, [s.index]: { ...p, height: e.target.value } })} disabled={!p?.checked} /></td>
                  </tr>
                )
              })}
              {visibleSheets.length === 0 && <tr><td colSpan={6} className="muted">Kalıp planı başlığı taşıyan pafta bulunamadı; "Tüm paftaları göster" ile seçin.</td></tr>}
            </tbody>
          </table>
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => addSheets(false)} disabled={busy || selectedCount === 0}>
              {busy ? 'Kırpılıyor ve analiz ediliyor...' : `Seçili ${selectedCount} paftayı ekle ve analiz et`}
            </button>
            {picker.source.can_use_whole && (
              <button className="secondary" onClick={() => addSheets(true)} disabled={busy}>Tüm çizimi tek plan olarak ekle</button>
            )}
            <button className="secondary" onClick={() => { setPicker(null) }} disabled={busy}>Vazgeç</button>
            <span className="muted">Büyük dosyalarda her pafta için kırpma + analiz 10-30 saniye sürebilir.</span>
          </div>
        </div>
      )}

      <div className="grid2">
        <div className="panel">
          <h3>DXF çizim yükle</h3>
          <p className="muted">
            DWG dosyasını AutoCAD'de <b>Farklı Kaydet → AutoCAD DXF</b> ile dönüştürün. Bütün paftaların yan yana durduğu tek bir
            ruhsat projesi dosyası da yüklenebilir: paftalar otomatik bulunur, kalıp planlarını seçersiniz.
          </p>
          <form className="upload" onSubmit={upload}>
            <label className="field">Dosya<input id="dxf-input" type="file" accept=".dxf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
            <label className="field">Plan adı<input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Zemin Kat / Temel" /></label>
            <label className="field">Kaç kat temsil ediyor<input type="number" min={1} value={storeyCount} onChange={(e) => setStoreyCount(+e.target.value)} /></label>
            <label className="field">Birim
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                <option value="">Otomatik</option><option value="cm">cm</option><option value="mm">mm</option><option value="m">m</option>
              </select>
            </label>
            <button type="submit" disabled={!file || busy}>{busy ? 'Yükleniyor / analiz ediliyor...' : 'Yükle ve analiz et'}</button>
          </form>
        </div>

        <div className="panel">
          <h3>Metraj parametreleri</h3>
          <div className="row">
            <label className="field">Kat yüksekliği H (m)<input type="number" step="0.05" value={params.storey_height} onChange={(e) => setParams({ ...params, storey_height: +e.target.value })} /></label>
            <label className="field">Döşeme kalınlığı d (m)<input type="number" step="0.01" value={params.slab_thickness} onChange={(e) => setParams({ ...params, slab_thickness: +e.target.value })} /></label>
            <label className="field">KDV oranı (0.20 = %20)<input type="number" step="0.01" value={params.vat_rate} onChange={(e) => setParams({ ...params, vat_rate: +e.target.value })} /></label>
          </div>
          <h3>Demir oranları (kg/m³ beton)</h3>
          <div className="row">
            {(Object.keys(ETYPE_LABELS) as EType[]).map((k) => (
              <label className="field" key={k}>{ETYPE_LABELS[k]}<input type="number" value={ratios[k] ?? 0} onChange={(e) => setRatios({ ...ratios, [k]: +e.target.value })} /></label>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={saveParams} disabled={busy}>Kaydet</button>
            <span className="muted">
              Döşemeler kiriş ağından (net alan) çıkarıldığında kolon/perde betonu tam kat yüksekliğiyle, kalıbı kiriş altına kadar (H − kiriş yüksekliği) hesaplanır.
              Döşeme kalınlığı etiketi olmayan döşemelerde d kullanılır.
            </span>
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Çizimler</h3>
        {drawings.length === 0 && <p className="muted">Henüz çizim yüklenmedi.</p>}
        {drawings.length > 0 && (
          <table>
            <thead>
              <tr><th>Plan</th><th>Dosya</th><th>Birim</th><th className="num">Kat sayısı</th><th className="num">Kat yüksekliği H (m)</th><th className="num">Eleman</th><th>Uyarı</th><th></th></tr>
            </thead>
            <tbody>
              {drawings.map((d) => (
                <tr key={d.id}>
                  <td><input className="wide" defaultValue={d.label} onBlur={(e) => e.target.value !== d.label && patchDrawing(d, { label: e.target.value })} /></td>
                  <td className="mono">{d.filename}</td>
                  <td>
                    <select value={d.unit_override ?? ''} onChange={(e) => patchDrawing(d, { unit_override: e.target.value })}>
                      <option value="">Otomatik ({d.unit}{d.unit_detected ? '' : ', tahmin'})</option>
                      <option value="cm">cm</option><option value="mm">mm</option><option value="m">m</option>
                    </select>
                  </td>
                  <td className="num"><input type="number" min={1} defaultValue={d.storey_count} onBlur={(e) => +e.target.value !== d.storey_count && patchDrawing(d, { storey_count: +e.target.value })} /></td>
                  <td className="num">
                    <input type="number" step="0.01" placeholder={`proje: ${params.storey_height}`} defaultValue={d.storey_height ?? ''}
                      title="Boş bırakılırsa projenin kat yüksekliği kullanılır"
                      onBlur={(e) => { const v = e.target.value ? +e.target.value : null; if (v !== d.storey_height) patchDrawing(d, { storey_height: v }) }} />
                  </td>
                  <td className="num">{d.element_count}</td>
                  <td>{d.warnings.length > 0 ? <span title={d.warnings.join('\n')}>⚠ {d.warnings.length}</span> : <span className="muted">-</span>}</td>
                  <td className="row">
                    <Link className="btn" to={`/projects/${id}/drawings/${d.id}`}>Elemanlar</Link>
                    <button className="danger small" onClick={() => removeDrawing(d)}>Sil</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
