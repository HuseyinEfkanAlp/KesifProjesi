import { useCallback, useEffect, useRef, useState } from 'react'
import { Api, type SheetPick } from '../api/client'
import { DISCIPLINES, isSheetSelection, type Discipline, type DisciplineChoice, type Drawing, type SheetInfo, type SheetSelection } from '../types'
import { planTypeGroups, usePlanTypes } from '../hooks/usePlanTypes'

/** Bir paftanın seçim durumu (çok paftalı dosya) */
interface PickState {
  checked: boolean
  label: string
  storey: number
  height: string
  planType: string
  discipline: DisciplineChoice
}

interface LogLine { file: string; kind: 'ok' | 'warn' | 'error' | 'info'; text: string }

interface Props {
  projectId: number
  storeyHeight: number
  /** Çizim eklendikten / pafta kırpıldıktan sonra */
  onChanged: () => void
  compact?: boolean
}

const UNIT_OPTIONS = [['', 'Otomatik'], ['cm', 'cm'], ['mm', 'mm'], ['m', 'm']] as const

/**
 * Plan yükleme: birden çok DXF / DWG sürükle-bırak. Her dosya sırayla yüklenir; tek paftalı dosyanın plan tipi ve
 * disiplini dosya adı / başlıktan tanınır ve hemen analiz edilir. Çok paftalı (ruhsat) dosyada paftalar listelenir,
 * tanınan plan tipine göre önceden işaretlenir; kullanıcı onaylar, sıra sonraki dosyaya geçer.
 */
export default function PlanIntake({ projectId, storeyHeight, onChanged, compact }: Props) {
  const planTypes = usePlanTypes()
  const groups = planTypeGroups(planTypes)
  const [pending, setPending] = useState<File[]>([])
  const [busy, setBusy] = useState<string>('')
  const [log, setLog] = useState<LogLine[]>([])
  const [unit, setUnit] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [picker, setPicker] = useState<(SheetSelection & { file: string }) | null>(null)
  const [picks, setPicks] = useState<Record<number, PickState>>({})
  const [showAll, setShowAll] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const changed = useRef(onChanged)
  useEffect(() => { changed.current = onChanged }, [onChanged])

  const addLog = (line: LogLine) => setLog((l) => [...l, line])

  const enqueue = (files: FileList | File[]) => {
    const list = Array.from(files).filter((f) => /\.(dxf|dwg)$/i.test(f.name))
    const skipped = Array.from(files).length - list.length
    if (skipped) addLog({ file: '', kind: 'warn', text: `${skipped} dosya atlandı (yalnızca .dxf / .dwg yüklenir)` })
    if (list.length) setPending((p) => [...p, ...list])
  }

  const describe = (d: Drawing) => {
    const pt = planTypes.find((t) => t.code === d.plan_type)
    return pt ? `${pt.group_label}: ${pt.label}` : 'plan tipi tanınamadı'
  }

  // Sıradaki dosyayı yükle (pafta seçimi açıkken bekler)
  useEffect(() => {
    if (busy || picker || pending.length === 0) return
    const file = pending[0]
    setPending((p) => p.slice(1))
    setBusy(`${file.name} yükleniyor / analiz ediliyor...`)
    Api.drawings.upload(projectId, file, { unitOverride: unit })
      .then((res) => {
        if (isSheetSelection(res)) {
          const init: Record<number, PickState> = {}
          for (const s of res.sheets) {
            init[s.index] = {
              checked: !!s.plan_type && s.analyze, label: s.title, storey: 1, height: '',
              planType: s.plan_type, discipline: (s.discipline || 'auto') as DisciplineChoice,
            }
          }
          setPicks(init)
          setShowAll(false)
          setPicker({ ...res, file: file.name })
          addLog({ file: file.name, kind: 'info', text: `${res.sheets.length} pafta bulundu; ${Object.values(init).filter((p) => p.checked).length} tanesi plan olarak tanındı, onay bekliyor` })
        } else {
          const d = res
          addLog({ file: file.name, kind: d.plan_type ? 'ok' : 'warn', text: `${describe(d)} · ${DISCIPLINES[d.discipline]} · ${d.element_count} eleman${d.plan_type ? '' : ' — çizim listesinden plan tipini seçin'}` })
          changed.current()
        }
      })
      .catch((e: Error) => addLog({ file: file.name, kind: 'error', text: e.message }))
      .finally(() => setBusy(''))
  }, [pending, busy, picker, projectId, unit, planTypes])  // eslint-disable-line react-hooks/exhaustive-deps

  const setPick = (idx: number, patch: Partial<PickState>) => setPicks((ps) => ({ ...ps, [idx]: { ...ps[idx], ...patch } }))

  const choosePlanType = (idx: number, code: string) => {
    const pt = planTypes.find((t) => t.code === code)
    setPick(idx, { planType: code, discipline: pt ? pt.discipline : picks[idx].discipline, checked: picks[idx].checked || !!code })
  }

  const confirmSheets = async (whole = false) => {
    if (!picker) return
    const sheets: SheetPick[] = whole ? [] : Object.entries(picks)
      .filter(([, p]) => p.checked)
      .map(([idx, p]) => ({
        index: Number(idx), label: p.label, storey_count: p.storey, storey_height: p.height ? +p.height : null,
        discipline: p.discipline, plan_type: p.planType || undefined,
      }))
    if (!whole && sheets.length === 0) return
    const file = picker.file
    setBusy(`${file}: ${whole ? 'tüm çizim' : `${sheets.length} pafta`} kırpılıyor ve analiz ediliyor...`)
    try {
      const ds = await Api.drawings.fromSource(projectId, picker.source.token, sheets, unit, 'auto', whole)
      for (const d of ds) addLog({ file, kind: d.plan_type ? 'ok' : 'warn', text: `${d.label}: ${describe(d)} · ${DISCIPLINES[d.discipline]} · ${d.element_count} eleman` })
      setPicker(null)
      changed.current()
    } catch (e) { addLog({ file, kind: 'error', text: (e as Error).message }) } finally { setBusy('') }
  }

  const cancelSheets = () => {
    if (picker) addLog({ file: picker.file, kind: 'warn', text: 'pafta seçimi iptal edildi; dosyadan çizim eklenmedi' })
    setPicker(null)
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false)
    if (e.dataTransfer.files?.length) enqueue(e.dataTransfer.files)
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const selectedCount = Object.values(picks).filter((p) => p.checked).length
  const visibleSheets: SheetInfo[] = picker
    ? picker.sheets.filter((s) => showAll || s.plan_type || picks[s.index]?.checked)
    : []
  const disciplineOptions = (Object.keys(DISCIPLINES) as Discipline[]).map((d) => <option key={d} value={d}>{DISCIPLINES[d]}</option>)
  const planTypeOptions = (
    <>
      <option value="">— tanınmadı / seç —</option>
      {groups.map((g) => (
        <optgroup key={g.code} label={g.label}>
          {g.types.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
        </optgroup>
      ))}
    </>
  )

  return (
    <div className="intake">
      <div className={`dropzone${dragOver ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }} onDragLeave={() => setDragOver(false)} onDrop={onDrop}
        onClick={() => inputRef.current?.click()}>
        <input ref={inputRef} type="file" multiple accept=".dxf,.dwg,.DXF,.DWG" style={{ display: 'none' }}
          onChange={(e) => { if (e.target.files) enqueue(e.target.files); e.target.value = '' }} />
        <div className="dz-title">Planları buraya bırakın ya da tıklayıp seçin</div>
        <div className="muted">
          DXF / DWG; birden çok dosya olabilir. Bütün paftaların yan yana durduğu <b>ruhsat projesi</b> dosyası da olur:
          paftalar ayrılır, başlığından plan tipi (kalıp, donatı, tava, tavan, altyapı…) tanınır, siz onaylarsınız.
        </div>
        {!compact && (
          <div className="muted" style={{ marginTop: 6 }}>
            DWG için sunucuda ODA File Converter kurulu olmalı; yoksa AutoCAD'de <b>Farklı Kaydet → DXF</b>.
          </div>
        )}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <label className="field">Çizim birimi
          <select value={unit} onChange={(e) => setUnit(e.target.value)} onClick={(e) => e.stopPropagation()}>
            {UNIT_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        {busy && <span className="busy">⏳ {busy}</span>}
        {!busy && pending.length > 0 && <span className="muted">{pending.length} dosya sırada</span>}
        {picker && pending.length > 0 && <span className="muted">(pafta seçimi onaylanınca sıradaki {pending.length} dosya yüklenecek)</span>}
      </div>

      {picker && (
        <div className="panel sheet-picker">
          <h3>Paftaları onayla — {picker.file} <span className="muted">({picker.source.size_mb} MB, {picker.sheets.length} pafta)</span></h3>
          <p className="muted">
            Her pafta başlığından plan tipi ve analiz disiplini tanındı; tanınanlar işaretli. Yanlışsa plan tipini değiştirin, tanınmayanı seçin.
            Kesit ve detay paftaları metraja girmediği için işaretlenmez. Kat kalıp planlarında "kaç kat temsil ediyor" ve kat yüksekliğini girin.
          </p>
          <div className="row" style={{ marginBottom: 8 }}>
            <button className="secondary small" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Yalnızca tanınan paftaları göster' : `Tüm paftaları göster (${picker.sheets.length})`}
            </button>
            <button className="secondary small" onClick={() => setPicks(Object.fromEntries(Object.entries(picks).map(([k, p]) => [k, { ...p, checked: true }])))}>Tümünü seç</button>
            <button className="secondary small" onClick={() => setPicks(Object.fromEntries(Object.entries(picks).map(([k, p]) => [k, { ...p, checked: false }])))}>Seçimi temizle</button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr><th></th><th>Pafta başlığı</th><th>Plan tipi</th><th>Disiplin (analiz)</th><th>Plan adı</th><th className="num">Kat</th><th className="num">H (m)</th><th className="num">Nesne</th></tr>
              </thead>
              <tbody>
                {visibleSheets.map((s) => {
                  const p = picks[s.index]
                  const alt = (s.titles ?? []).find((t) => t !== s.title)
                  return (
                    <tr key={s.index} className={p?.checked ? 'selected' : ''}>
                      <td><input type="checkbox" checked={!!p?.checked} onChange={(e) => setPick(s.index, { checked: e.target.checked })} /></td>
                      <td>
                        {s.title}{!s.titled && <span className="muted"> {s.fragment ? '(başlıksız küçük parça: detay / tablo; plan değil)' : '(başlık bulunamadı)'}</span>}
                        {alt && <div className="muted" style={{ fontSize: 12 }}>paftada: {alt}</div>}
                      </td>
                      <td>
                        <select value={p?.planType ?? ''} onChange={(e) => choosePlanType(s.index, e.target.value)} className={p?.planType ? '' : 'unset'}>
                          {planTypeOptions}
                        </select>
                      </td>
                      <td>
                        <select value={p?.discipline === 'auto' ? '' : p?.discipline} disabled={!p?.checked}
                          onChange={(e) => setPick(s.index, { discipline: (e.target.value || 'auto') as DisciplineChoice })}>
                          <option value="">(plan tipinden)</option>{disciplineOptions}
                        </select>
                      </td>
                      <td><input className="wide" value={p?.label ?? ''} onChange={(e) => setPick(s.index, { label: e.target.value })} disabled={!p?.checked} /></td>
                      <td className="num"><input type="number" min={1} value={p?.storey ?? 1} onChange={(e) => setPick(s.index, { storey: Math.max(1, +e.target.value) })} disabled={!p?.checked} /></td>
                      <td className="num"><input type="number" step="0.01" placeholder={`${storeyHeight}`} value={p?.height ?? ''} onChange={(e) => setPick(s.index, { height: e.target.value })} disabled={!p?.checked} /></td>
                      <td className="num">{s.entity_count.toLocaleString('tr-TR')}</td>
                    </tr>
                  )
                })}
                {visibleSheets.length === 0 && <tr><td colSpan={8} className="muted">Başlığından tanınan pafta yok; "Tüm paftaları göster" ile seçin.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => confirmSheets(false)} disabled={!!busy || selectedCount === 0}>
              {busy ? 'Kırpılıyor ve analiz ediliyor...' : `Seçili ${selectedCount} paftayı ekle ve analiz et`}
            </button>
            {picker.source.can_use_whole && (
              <button className="secondary" onClick={() => confirmSheets(true)} disabled={!!busy}>Tüm çizimi tek plan olarak ekle</button>
            )}
            <button className="secondary" onClick={cancelSheets} disabled={!!busy}>Bu dosyayı atla</button>
            <span className="muted">Büyük dosyalarda her pafta için kırpma + analiz 10-30 saniye sürebilir.</span>
          </div>
        </div>
      )}

      {log.length > 0 && (
        <ul className="intake-log">
          {log.map((l, i) => (
            <li key={i} className={l.kind}>
              <span className="mark">{l.kind === 'ok' ? '✔' : l.kind === 'error' ? '✖' : l.kind === 'warn' ? '⚠' : 'ℹ'}</span>
              {l.file && <span className="mono">{l.file}</span>} {l.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
