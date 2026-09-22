import QualitySummary from '../components/QualitySummary'
import type { QualityReport } from '../types'
import { Fragment, useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { Link, useParams } from 'react-router-dom'
import { Api, fmt } from '../api/client'
import { ETYPE_LABELS, SUBTYPE_LABELS, type Boq, type HeadlineSection, type Project, type QuantityLine, type QuantitySummary } from '../types'
import ProjectNav from './ProjectNav'
import SystemsPanel from '../components/SystemsPanel'


const REBAR_SOURCE_LABEL: Record<string, string> = {
  oran: 'oranla tahmin', tablo: 'donatı tablosu', poz: 'poz yazıları', elle: 'elle girildi',
  'tablo+poz': 'tablo + poz', 'tablo+oran': 'tablo + oran', 'poz+oran': 'poz + oran', 'tablo+poz+oran': 'tablo + poz + oran',
}
const REBAR_SOURCE_HINT: Record<string, string> = {
  oran: 'Beton × kg/m³ tahmini (düşük güven); donatı paftası yüklenince tablodan alınır',
  tablo: 'Donatı paftasındaki metraj tablosundan okundu (yüksek güven)',
  poz: 'Adetli poz yazılarından hesaplandı (kanca / bindirme yazıda yoksa eksik olabilir)',
  elle: 'Kullanıcı elle girdi',
  'tablo+oran': 'Bazı katların donatı paftası yok: o katlar oranla',
  'poz+oran': 'Bazı katların donatı paftası yok: o katlar oranla',
}

/** Keşif kalemlerini türe göre bloklar: aynı türün (beton, kalıp, demir…) kalemleri tek başlık altında,
 *  başlıkta türün toplamı. Sıra korunur; "sistem" / "bilgi" satırları toplama girmez. */
function kindBlocks(items: Boq['items']) {
  const order: string[] = []
  const by = new Map<string, Boq['items']>()
  for (const it of items) {
    if (!by.has(it.kind)) { by.set(it.kind, []); order.push(it.kind) }
    by.get(it.kind)!.push(it)
  }
  return order.map((kind) => {
    const rows = by.get(kind)!
    const real = rows.filter((x) => !x.detail?.system && !x.detail?.info)
    return {
      kind, kindLabel: rows[0].kind_label, unit: rows[0].unit, rows,
      total: real.reduce((s, x) => s + x.quantity, 0),
      count: real.reduce((s, x) => s + x.count, 0),
    }
  })
}

export default function Quantities() {
  const pid = Number(useParams().id)
  const [project, setProject] = useState<Project | null>(null)
  const [summary, setSummary] = useState<QuantitySummary | null>(null)
  const [lines, setLines] = useState<QuantityLine[]>([])
  const [boq, setBoq] = useState<Boq | null>(null)
  const [rebarMix, setRebarMix] = useState<Record<string, { dia_mm: number; share: number }[]>>({})
  const [headline, setHeadline] = useState<HeadlineSection[]>([])
  // Ana kalemlerden hangisinin dökümü açık; ilk yüklemede en büyüğü (demir) açılır
  const [openKind, setOpenKind] = useState('demir')
  const [error, setError] = useState('')
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [showLines, setShowLines] = useState(false)
  // Keşif listesinde tür (beton, kalıp, demir…) önce toplamıyla görünür; kalem ayrıntısı katlanır.
  const [openKinds, setOpenKinds] = useState<Record<string, boolean>>({})
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    Promise.all([Api.projects.get(pid), Api.quantities(pid)])
      .then(([p, q]) => { setProject(p); setSummary(q.summary); setLines(q.lines); setBoq(q.boq); setQuality(q.quality); setRebarMix(q.rebar_mix ?? {}); setHeadline(q.headline ?? []) })
      .catch((e) => setError(e.message))
  }, [pid, refresh])

  if (!project || !summary || !boq) return <Loading error={error} />
  const open1 = headline.find((h) => h.kind === openKind) ?? null
  const hasStructural = summary.groups.length > 0
  const wallH = project.params?.wall_height

  return (
    <>
      <ProjectNav id={pid} name={project.name} />
      <QualitySummary report={quality} projectId={pid} />
      {error && <div className="error">{error}</div>}

      {boq.items.length === 0 && (
        <div className="panel empty-state">
          <h2>Henüz metraj yok</h2>
          <p>Çizimler ve Parametreler sayfasından plan yükleyin; keşif iş grubu, poz ve reçeteleriyle burada listelenir.</p>
          <Link className="btn" to={`/projects/${pid}`}>Plan yükle</Link>
        </div>
      )}
      {headline.length > 0 && (
        <div className="panel headline-panel">
          <h3 style={{ marginTop: 0 }}>Ana kalemler <span className="muted" style={{ fontWeight: 400 }}>· ne kadar, neyden, ne kadarı ölçüldü</span></h3>
          <div className="headline-cards">
            {headline.map((h) => (
              <button key={h.kind} className={`headline-card${openKind === h.kind ? ' on' : ''}`}
                onClick={() => setOpenKind(openKind === h.kind ? '' : h.kind)}>
                <div className="label">{h.label}</div>
                <div className="value">{fmt(h.total, h.unit === 'kg' ? 0 : 1)} <span>{h.unit}</span></div>
                <div className="split">
                  {h.waste > 0 && <>ölçülen {fmt(h.net, h.unit === 'kg' ? 0 : 1)} + fire {fmt(h.waste, h.unit === 'kg' ? 0 : 1)}</>}
                  {h.kind === 'duvar' && <>brüt {fmt(h.gross ?? 0, 1)} − düşülen {fmt(h.deducted ?? 0, 1)}</>}
                  {h.waste === 0 && h.kind !== 'duvar' && <>tamamı ölçüldü</>}
                </div>
                {(h.estimated ?? 0) > 0 && <div className="est">bunun {fmt(h.estimated ?? 0, 0)} {h.unit}'ı oranla tahmin</div>}
                {(h.already_net ?? 0) > 0 && <div className="est">boşluk çizimde kesilmiş: {fmt(h.already_net ?? 0, 1)} m²</div>}
                <div className="hours">{fmt(h.labour_hours, 0)} saat işçilik</div>
              </button>
            ))}
          </div>

          {open1 && (
            <div style={{ overflowX: 'auto', marginTop: 14 }}>
              {open1.kind === 'demir' ? (
                <table className="table-compact rebar-table">
                  <thead><tr><th>Çap</th><th className="num">Sipariş (kg)</th><th className="num">ton</th>
                    <th className="num">Ölçülen (kg)</th><th className="num">Oranla (kg)</th><th className="num">Fire (kg)</th>
                    <th className="num">Uzunluk (m)</th><th>Nerede</th></tr></thead>
                  <tbody>
                    {open1.rows.map((r) => (
                      <tr key={r.label}>
                        <td><b>{r.label}</b></td>
                        <td className="num"><b>{fmt(r.order_kg ?? r.quantity, 0)}</b></td>
                        <td className="num"><b>{fmt((r.order_kg ?? r.quantity) / 1000, 1)}</b></td>
                        <td className="num">{fmt(r.metraj_kg ?? 0, 0)}</td>
                        <td className="num muted">{r.ratio_kg ? fmt(r.ratio_kg, 0) : '-'}</td>
                        <td className="num muted">{r.fire_kg ? fmt(r.fire_kg, 0) : '-'}</td>
                        <td className="num muted">{r.length_m ? fmt(r.length_m, 0) : '-'}</td>
                        <td className="muted">{Object.entries(r.targets ?? {}).sort((a, b) => b[1] - a[1])
                          .map(([k, v]) => `${k} ${fmt(v / 1000, 1)} t`).join(' · ') || '-'}</td>
                      </tr>
                    ))}
                    {open1.unsized && (
                      <tr><td><b>çapsız</b></td>
                        <td className="num"><b>{fmt(open1.unsized.metraj_kg + open1.unsized.ratio_kg + open1.unsized.fire_kg, 0)}</b></td>
                        <td className="num"></td><td className="num">{fmt(open1.unsized.metraj_kg, 0)}</td>
                        <td className="num muted">{fmt(open1.unsized.ratio_kg, 0)}</td>
                        <td className="num muted">{fmt(open1.unsized.fire_kg, 0)}</td><td className="num muted">-</td>
                        <td className="muted">çapa bölünemedi: {open1.unsized.groups.join(', ')}</td></tr>
                    )}
                    <tr className="total"><td>TOPLAM</td><td className="num">{fmt(open1.total, 0)}</td>
                      <td className="num">{fmt(open1.total / 1000, 1)}</td><td className="num">{fmt(open1.net - (open1.estimated ?? 0), 0)}</td>
                      <td className="num">{fmt(open1.estimated ?? 0, 0)}</td><td className="num">{fmt(open1.waste, 0)}</td>
                      <td className="num"></td><td></td></tr>
                  </tbody>
                </table>
              ) : open1.kind === 'duvar' ? (
                <table className="table-compact rebar-table">
                  <thead><tr><th>Malzeme / kalınlık</th><th className="num">Net (m²)</th><th className="num">Brüt (m²)</th>
                    <th className="num">Düşülen boşluk</th><th className="num">Çizimde kesilmiş</th><th></th></tr></thead>
                  <tbody>
                    {open1.rows.map((r) => (
                      <tr key={r.label}>
                        <td>{r.label}</td>
                        <td className="num"><b>{fmt(r.quantity, 1)}</b></td>
                        <td className="num">{fmt(r.gross_m2 ?? 0, 1)}</td>
                        <td className="num muted">{r.openings_m2 ? fmt(r.openings_m2, 1) : '-'}</td>
                        <td className="num muted">{r.already_net_m2 ? fmt(r.already_net_m2, 1) : '-'}</td>
                        <td className="muted">{r.review ? '⚠ boşluk eşleşmesi kontrol edilmeli' : ''}</td>
                      </tr>
                    ))}
                    <tr className="total"><td>TOPLAM</td><td className="num">{fmt(open1.net, 1)}</td>
                      <td className="num">{fmt(open1.gross ?? 0, 1)}</td><td className="num">{fmt(open1.deducted ?? 0, 1)}</td>
                      <td className="num">{fmt(open1.already_net ?? 0, 1)}</td><td></td></tr>
                  </tbody>
                </table>
              ) : (
                <table className="table-compact rebar-table">
                  <thead><tr><th>Kalem</th><th className="num">Miktar ({open1.unit})</th><th className="num">Adet</th></tr></thead>
                  <tbody>
                    {open1.rows.map((r) => (
                      <tr key={r.label}><td>{r.label}</td><td className="num"><b>{fmt(r.quantity, 1)}</b></td>
                        <td className="num muted">{r.count ? fmt(r.count, 0) : ''}</td></tr>
                    ))}
                    {open1.waste > 0 && <tr><td className="muted">Fire</td><td className="num muted">{fmt(open1.waste, 1)}</td><td></td></tr>}
                    <tr className="total"><td>TOPLAM</td><td className="num">{fmt(open1.total, 1)}</td><td></td></tr>
                  </tbody>
                </table>
              )}
              <p className="muted hint">
                {open1.labour.length > 0 && <>İşçilik: {open1.labour.map((l) => `${l.label} ${fmt(l.hours, 0)} saat`).join(' · ')}. </>}
                {open1.extras.length > 0 && <>Bağlı sarf: {open1.extras.map((e) => `${e.label} ${fmt(e.quantity, 0)} ${e.unit}`).join(' · ')}. </>}
                {open1.kind === 'demir' && <><b>Ölçülen</b> donatı tablosundan / poz yazılarından okunur; <b>oranla</b> donatı paftası olmayan elemanın beton × kg/m³ tahminidir; <b>fire</b> kesim artığıdır.</>}
                {open1.kind === 'duvar' && <><b>Net</b> = brüt − düşülen boşluk. "Çizimde kesilmiş", kapı / pencerenin duvar parçaları arasındaki açıklıkta gösterildiği, yani alanın <b>zaten</b> net olduğu anlamına gelir; ikinci kez düşülmez.</>}
              </p>
            </div>
          )}
        </div>
      )}


      {Object.keys(rebarMix).length > 0 && (
        <div className="panel" style={{ paddingTop: 10, paddingBottom: 10 }}>
          <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
            <b>Çizimden okunan donatı çapları</b>
            {(rebarMix['*'] ?? []).map((d) => (
              <span key={d.dia_mm} className="count-pill">Ø{d.dia_mm} %{Math.round(d.share * 100)}</span>
            ))}
          </div>
          <details style={{ marginTop: 6 }}>
            <summary className="muted">Eleman tipine göre dağılım · donatı tablosu olmayan elemanların oran demiri bu dağılıma göre çaplara bölündü</summary>
            <table className="table-compact" style={{ marginTop: 8, maxWidth: 520 }}>
              <thead><tr><th>Eleman</th><th>Çap dağılımı</th></tr></thead>
              <tbody>
                {Object.entries(rebarMix).filter(([k]) => k !== '*').map(([k, ds]) => (
                  <tr key={k}>
                    <td>{ETYPE_LABELS[k as keyof typeof ETYPE_LABELS] ?? k}</td>
                    <td>{ds.map((d) => `Ø${d.dia_mm} %${Math.round(d.share * 100)}`).join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted hint">Çap payı, donatı yazılarındaki adet × çap² toplamından çıkar (ağırlık değil, karışım oranı).
              Donatı tablosu okunan elemanlarda demir zaten çap bazındadır; bu dağılım yalnız oranla hesaplanan demiri böler.</p>
          </details>
        </div>
      )}

      {boq.kind_totals.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Tür toplamları <span className="muted" style={{ fontWeight: 400 }}>· proje geneli</span></h3>
          <div className="totals-grid">
            {boq.by_group.map((g) => {
              const rows = boq.kind_totals.filter((t) => t.work_group === g.group)
              if (rows.length === 0) return null
              return (
                <div key={g.group} className="totals-block">
                  <div className="eyebrow">{g.label}</div>
                  <table className="table-compact totals-table">
                    <tbody>
                      {rows.map((t) => (
                        <tr key={t.kind}>
                          <td>{t.label}{t.items > 1 && <span className="muted hint"> · {t.items} kalem</span>}</td>
                          <td className="num"><b>{fmt(t.quantity, t.unit === 'adet' || t.unit === 'kg' ? 0 : 1)}</b> {t.unit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {boq.by_group.map((g) => (
        <div className="panel" key={g.group}>
          <h3>{g.label} <span className="muted" style={{ fontWeight: 400 }}>· {g.items.length} kalem</span></h3>
          <table>
            <thead><tr><th>Poz</th><th>Disiplin</th><th>Tür</th><th>Kalem</th><th className="num">Miktar</th><th>Birim</th><th className="num">Adet / hat</th><th title="Sayının nereden geldiği">Kaynak</th><th>Not</th></tr></thead>
            <tbody>
              {kindBlocks(g.items).map(({ kind, kindLabel, unit, rows, total, count }) => {
                const key = `${g.group}:${kind}`
                const open = rows.length === 1 || openKinds[key]
                return (
                <Fragment key={key}>
                {rows.length > 1 && (
                  <tr className="subtotal" style={{ cursor: 'pointer' }} onClick={() => setOpenKinds({ ...openKinds, [key]: !openKinds[key] })}>
                    <td colSpan={3}><b>{open ? '▾' : '▸'} {kindLabel}</b></td>
                    <td className="muted">{rows.length} kalem{open ? '' : ' — ayrıntı için tıklayın'}</td>
                    <td className="num"><b>{fmt(total, unit === 'adet' || unit === 'kg' ? 0 : 2)}</b></td>
                    <td><b>{unit}</b></td>
                    <td className="num">{count ? fmt(count, 0) : ''}</td>
                    <td></td>
                    <td></td>
                  </tr>
                )}
                {open && rows.map((it) => (
                <tr key={it.key} className={it.detail?.system ? 'system-row' : ''}>
                  <td className="mono" title={it.poz_name}>{it.poz || <span className="muted">-</span>}</td>
                  <td><span className={`badge disc-${it.discipline.split(':')[0]}`}>{it.discipline_label.split(' (')[0]}</span></td>
                  <td>{it.kind_label}{it.detail?.system ? <span className="badge none" style={{ marginLeft: 6 }}>sistem</span> : null}{it.detail?.info ? <span className="badge none" style={{ marginLeft: 6 }}>bilgi</span> : null}{it.detail?.recipe ? <span className="badge recipe" style={{ marginLeft: 6 }} title={`Reçeteden türetildi: ${String(it.detail.parent ?? '')}`}>reçete</span> : null}</td>
                  <td>{it.label}{it.detail?.system_code && !it.detail?.system ? <span className="muted hint"> ← {String(it.detail.system_code)}</span> : null}{it.detail?.recipe ? <span className="muted hint"> ← {String(it.detail.parent ?? '').split(':')[0]}</span> : null}</td>
                  <td className="num"><b>{fmt(it.quantity, it.unit === 'adet' || it.unit === 'kg' ? 0 : 2)}</b></td>
                  <td>{it.unit}</td>
                  <td className="num">{it.count ? fmt(it.count, 0) : '-'}</td>
                  <td className="nowrap" title={it.confidence.note}>
                    <span className={`badge conf-${it.confidence.code}`}>{it.confidence.icon} {it.confidence.label}</span>
                  </td>
                  <td className="muted">{it.notes.join('; ')}</td>
                </tr>
                ))}
                </Fragment>
                )
              })}
            </tbody>
          </table>
          {g.group === 'INCE' && (
            <p className="muted">
              Duvar m² = uzunluk × duvar yüksekliği ({wallH ? `${wallH} m` : `H − d = ${(project.storey_height - project.slab_thickness).toFixed(2)} m`}) × kat sayısı − 0,10 m² ve üstü boşluklar.
              Sıva ve boya: tüm boşluklar düşülür, × yüz sayısı ({project.params?.plaster_sides ?? 2} / {project.params?.paint_sides ?? 2}). Parametreler proje sayfasında.
            </p>
          )}
          {g.group === 'ELK' && (
            <p className="muted">
              Kablo m = (hat uzunluğu + iniş payı {project.params?.cable_drop ?? 0} m) × kat sayısı × (1 + fire %{project.params?.cable_waste_pct ?? 0}).
              Tava fire %{project.params?.tray_waste_pct ?? 0}. Kesit / boyut etiketten ya da katman adından okunur; bilinmeyenler "belirsiz" grubunda toplanır.
            </p>
          )}
        </div>
      ))}
      {boq.items.length > 0 && (
        <details className="section">
          <summary>Katmanlı sistemler ve tamlık kontrolü<span className="muted">çatı / cephe bileşenleri, türetilmiş kalemler, çizimden çıkmayan işler</span></summary>
          <div className="panel"><SystemsPanel projectId={pid} refreshKey={0} onChanged={() => setRefresh((r) => r + 1)} /></div>
        </details>
      )}
      {boq.items.length > 0 && (
        <details className="section">
          <summary>Ölçü kuralları<span className="muted">ÇŞB birim fiyat tariflerine göre; poz numarası katalogdan ya da varsayılan eşlemeden</span></summary>
          <div className="panel">
            <ul className="muted" style={{ margin: 0 }}>
              {Object.values(boq.rules).map((r) => <li key={r.text}>{r.text} <span className="hint">({r.source})</span></li>)}
            </ul>
            <p className="muted hint" style={{ marginBottom: 0 }}>Poz numarası boş olan kalemler için Standart sayfasındaki katalogda kaleme poz girin; sezgisel kalemlerde (beton, kalıp, gazbeton duvar, sıva, boya, demir) varsayılan ÇŞB pozları kullanılır.</p>
            <p className="muted hint" style={{ marginBottom: 0 }}><b>Reçete</b> rozetli satırlar ana kalemden türetilen alt işlerdir (iskele, ankraj, tij / somun / pul, kaynak, antipas, montaj saati…); çarpanlar katalogda kalemin "Reçete" alanından düzenlenir, tümünü kapatmak için proje parametrelerinde <code className="layer">derived_off</code> listesine <code className="layer">recete</code> yazın.</p>
          </div>
        </details>
      )}

      {hasStructural && (
        <>
          <div className="cards">
            <div className="card"><div className="label">Toplam beton</div><div className="value">{fmt(summary.totals.concrete_m3)} m³</div></div>
            <div className="card"><div className="label">Toplam kalıp</div><div className="value">{fmt(summary.totals.formwork_m2)} m²</div></div>
            <div className="card"><div className="label">Toplam demir (oran ile)</div><div className="value">{fmt(summary.totals.rebar_kg, 0)} kg</div></div>
          </div>

          <div className="panel">
            <h3>Statik: kat / pafta bazında</h3>
            <div style={{ overflow: 'auto' }}>
              <table>
                <thead>
                  <tr><th>Plan</th><th>Kot</th><th className="num">Kolon m³</th><th className="num">Perde m³</th><th className="num">Kiriş m³</th><th className="num">Döşeme m³</th><th className="num">Temel m³</th><th className="num">Beton m³</th><th className="num">Kalıp m²</th><th className="num">Demir (oran) t</th><th className="num">Demir (tablo) t</th><th>Çap bazında (kg)</th></tr>
                </thead>
                <tbody>
                  {summary.by_drawing.map((r) => (
                    <tr key={r.drawing}>
                      <td>{r.drawing_id ? <Link to={`/projects/${pid}/drawings/${r.drawing_id}`}>{r.drawing}</Link> : r.drawing}</td>
                      <td>{r.kot ?? '-'}</td>
                      {(['column', 'shear_wall', 'beam', 'slab', 'foundation'] as const).map((et) => (
                        <td className="num" key={et}>{r.groups[et] ? fmt(r.groups[et].concrete_m3, 1) : '-'}</td>
                      ))}
                      <td className="num"><b>{r.concrete_m3 ? fmt(r.concrete_m3, 1) : '-'}</b></td>
                      <td className="num">{r.formwork_m2 ? fmt(r.formwork_m2, 0) : '-'}</td>
                      <td className="num">{r.rebar_kg ? fmt(r.rebar_kg / 1000, 1) : '-'}</td>
                      <td className="num">{r.rebar_table_kg ? <b>{fmt(r.rebar_table_kg / 1000, 1)}</b> : '-'}{r.rebar_target && <span className="muted"> ({ETYPE_LABELS[r.rebar_target as keyof typeof ETYPE_LABELS] ?? r.rebar_target})</span>}</td>
                      <td className="muted">{Object.entries(r.rebar_by_dia).map(([d, kg]) => `Ø${d}: ${fmt(kg, 0)}`).join(' · ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">
              Her kalıp planı o kottaki döşeme ve kirişleri, altındaki katın kolon ve perdelerini içerir. "Demir (oran)" beton × kg/m³ tahminidir;
              "Demir (tablo)" donatı paftasındaki metraj tablosundan okunan gerçek değerdir ve ilgili eleman tipinin oran tahminini geçersiz kılar.
            </p>
          </div>

          {summary.rebar_by_dia.length > 0 && (
            <div className="panel">
              <h3>Demir: çap bazında (donatı paftalarından, {fmt(summary.rebar_table_total_kg / 1000, 1)} t)</h3>
              {summary.rebar_by_source && (
                <p className="muted">Kaynak: {Object.entries(summary.rebar_by_source).map(([k, v]) => `${REBAR_SOURCE_LABEL[k] ?? k} ${fmt(v / 1000, 1)} t`).join(' · ')}</p>
              )}
              {summary.warnings && summary.warnings.length > 0 && (
                <ul className="warnings">{summary.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              )}
              <table>
                <thead><tr><th>Çap</th><th className="num">Toplam boy (m)</th><th className="num">Ağırlık (kg)</th><th className="num">Ton</th><th>Dağılım</th></tr></thead>
                <tbody>
                  {summary.rebar_by_dia.map((d) => (
                    <tr key={d.dia_mm}>
                      <td><b>Ø{d.dia_mm}</b></td>
                      <td className="num">{fmt(d.length_m, 0)}</td>
                      <td className="num">{fmt(d.weight_kg, 0)}</td>
                      <td className="num">{fmt(d.weight_kg / 1000, 2)}</td>
                      <td className="muted">{Object.entries(d.targets).map(([k, v]) => `${ETYPE_LABELS[k as keyof typeof ETYPE_LABELS] ?? k} ${fmt(v / 1000, 1)} t`).join(' · ')}{d.sources && Object.keys(d.sources).length > 0 ? ` — ${Object.entries(d.sources).map(([k, v]) => `${REBAR_SOURCE_LABEL[k] ?? k} ${fmt(v / 1000, 1)} t`).join(', ')}` : ''}</td>
                    </tr>
                  ))}
                  <tr className="total"><td>TOPLAM</td><td></td><td className="num">{fmt(summary.rebar_table_total_kg, 0)}</td><td className="num">{fmt(summary.rebar_table_total_kg / 1000, 2)}</td><td className="muted">{summary.rebar_ratio_total_kg > 0 ? `+ oranla tahmin edilen ${fmt(summary.rebar_ratio_total_kg / 1000, 1)} t (tablosu olmayan elemanlar)` : ''}</td></tr>
                </tbody>
              </table>
            </div>
          )}

          {summary.sections && summary.sections.length > 0 && (
            <div className="panel">
              <h3 style={{ marginTop: 0 }}>Statik: kesit bazında <span className="muted" style={{ fontWeight: 400 }}>· aynı kesitteki elemanlar tek satır</span></h3>
              <table className="table-compact">
                <thead><tr><th>Eleman</th><th>Kesit / kalınlık</th><th className="num">Adet (kat dahil)</th><th className="num">Uzunluk (m)</th><th className="num">Alan (m²)</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th></tr></thead>
                <tbody>
                  {summary.sections.map((sg) => (
                    <tr key={sg.key}>
                      <td><span className={`badge ${sg.etype}`}>{sg.label}</span></td>
                      <td><b>{sg.section}</b></td>
                      <td className="num">{sg.element_count}</td>
                      <td className="num">{sg.length_m ? fmt(sg.length_m, 1) : '-'}</td>
                      <td className="num">{sg.area_m2 ? fmt(sg.area_m2, 1) : '-'}</td>
                      <td className="num"><b>{fmt(sg.concrete_m3, 1)}</b></td>
                      <td className="num">{fmt(sg.formwork_m2, 0)}</td>
                      <td className="num">{fmt(sg.rebar_kg, 0)}</td>
                    </tr>
                  ))}
                  <tr className="total"><td>TOPLAM</td><td></td><td className="num">{summary.sections.reduce((s, x) => s + x.element_count, 0)}</td><td></td><td></td><td className="num">{fmt(summary.totals.concrete_m3, 1)}</td><td className="num">{fmt(summary.totals.formwork_m2, 0)}</td><td className="num">{fmt(summary.totals.rebar_kg, 0)}</td></tr>
                </tbody>
              </table>
            </div>
          )}

          <details className="section">
            <summary>Statik: eleman grubuna göre özet<span className="muted">kolon / perde / kiriş / döşeme / temel toplamları</span></summary>
          <div className="panel">
            <h3>Statik: eleman grubuna göre özet</h3>
            <table>
              <thead><tr><th>Grup</th><th className="num">Adet (kat dahil)</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th></tr></thead>
              <tbody>
                {summary.groups.map((g) => (
                  <tr key={g.key}><td><span className={`badge ${g.etype}`}>{g.label}</span></td><td className="num">{g.element_count}</td><td className="num">{fmt(g.concrete_m3, 3)}</td><td className="num">{fmt(g.formwork_m2)}</td><td className="num">{fmt(g.rebar_kg, 0)} <span className="muted" title={REBAR_SOURCE_HINT[g.rebar_source] ?? g.rebar_source}>({REBAR_SOURCE_LABEL[g.rebar_source] ?? g.rebar_source}{g.rebar_kots_ratio && g.rebar_kots_ratio.length > 0 ? `; oranla: ${g.rebar_kots_ratio.join(', ')}` : ''})</span></td></tr>
                ))}
                <tr className="total"><td>TOPLAM</td><td></td><td className="num">{fmt(summary.totals.concrete_m3, 3)}</td><td className="num">{fmt(summary.totals.formwork_m2)}</td><td className="num">{fmt(summary.totals.rebar_kg, 0)}</td></tr>
              </tbody>
            </table>
            <p className="muted">H = {project.levels?.effective ?? project.storey_height} m ({project.levels?.source ?? 'parametre'}), d = {Math.round(project.slab_thickness * 100)} cm. Temel kat sayısıyla çarpılmaz. Demir: "tablo" = donatı paftasından okundu, "oran" = beton × kg/m³ tahmini. Fire, bağ teli, plywood, kalıp yağı ve çivi keşif listesinde ayrı kalemlerdir.</p>
          </div>
          </details>

          <div className="panel">
            <div className="row between">
              <h3>Statik: eleman bazında metraj ({lines.length} satır)</h3>
              <button className="secondary small" onClick={() => setShowLines(!showLines)}>{showLines ? 'Gizle' : 'Göster'}</button>
            </div>
            {showLines && (
              <div style={{ overflow: 'auto' }}>
                <table>
                  <thead>
                    <tr><th>Çizim</th><th>Tip</th><th>Ad</th><th className="num">b (cm)</th><th className="num">h (cm)</th><th className="num">Kal. (cm)</th><th className="num">Uzunluk (m)</th><th className="num">Alan (m²)</th><th className="num">Adet</th><th className="num">Kat</th><th className="num">Beton (m³)</th><th className="num">Kalıp (m²)</th><th className="num">Demir (kg)</th><th>Not</th></tr>
                  </thead>
                  <tbody>
                    {lines.map((l) => (
                      <tr key={l.element_id}>
                        <td>{l.drawing_id ? <Link to={`/projects/${pid}/drawings/${l.drawing_id}`}>{l.drawing}</Link> : l.drawing}</td>
                        <td><span className={`badge ${l.etype}`}>{ETYPE_LABELS[l.etype]}</span>{l.subtype && <span className="muted"> {SUBTYPE_LABELS[l.subtype] ?? l.subtype}</span>}</td>
                        <td>{l.name ?? '-'}</td>
                        <td className="num">{l.b != null ? Math.round(l.b * 100) : '-'}</td>
                        <td className="num">{l.h != null ? Math.round(l.h * 100) : '-'}</td>
                        <td className="num">{l.thickness != null ? Math.round(l.thickness * 100) : '-'}</td>
                        <td className="num">{l.length ? fmt(l.length) : '-'}</td>
                        <td className="num">{l.area ? fmt(l.area, 3) : '-'}</td>
                        <td className="num">{l.count}</td>
                        <td className="num">×{l.multiplier}</td>
                        <td className="num">{fmt(l.total_concrete_m3, 3)}</td>
                        <td className="num">{fmt(l.total_formwork_m2)}</td>
                        <td className="num">{fmt(l.total_rebar_kg, 0)}</td>
                        <td className="muted">{[...l.notes, ...l.warnings].join('; ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </>
  )
}
