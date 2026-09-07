import { useEffect, useState } from 'react'
import { Api } from '../api/client'
import type { Catalog, CatalogItem, LayerCheck } from '../types'

const MEASURE_HINT: Record<string, string> = {
  count: 'blok yerleştir', length: 'çizgi / polyline', area: 'kapalı polyline / tarama', wall_area: 'eksen çizgisi (× yükseklik)', volume: 'kapalı alan (× kalınlık)',
}

export default function Standard() {
  const [cat, setCat] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')
  const [disc, setDisc] = useState('')
  const [form, setForm] = useState({ code: '', discipline: 'HAV', name: '', measure: 'length', spec_label: '', components: '' })
  const [dform, setDform] = useState({ code: '', name: '' })
  const [test, setTest] = useState('KSF-HAV-HAVA_KANAL-600x400')
  const [check, setCheck] = useState<LayerCheck | null>(null)

  const load = () => Api.catalog.get().then(setCat).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const run = async (fn: () => Promise<unknown>) => {
    setError('')
    try { await fn(); await load() } catch (e) { setError((e as Error).message) }
  }
  const addItem = (e: React.FormEvent) => {
    e.preventDefault()
    run(() => Api.catalog.upsertItem(form as Partial<CatalogItem> & { components: string })).then(() => setForm({ ...form, code: '', name: '', spec_label: '', components: '' }))
  }
  const addDisc = (e: React.FormEvent) => {
    e.preventDefault()
    run(() => Api.catalog.upsertDiscipline(dform.code, dform.name)).then(() => setDform({ code: '', name: '' }))
  }
  const doCheck = async () => {
    try { setCheck(await Api.catalog.checkLayer(test)) } catch (e) { setError((e as Error).message) }
  }

  if (!cat) return <p className="muted">{error || 'Yükleniyor...'}</p>
  const f = filter.toLocaleLowerCase('tr-TR')
  const groups = cat.by_discipline
    .filter((g) => !disc || g.code === disc)
    .map((g) => ({ ...g, items: g.items.filter((i) => !f || i.code.toLowerCase().includes(f) || i.name.toLocaleLowerCase('tr-TR').includes(f) || i.example.toLowerCase().includes(f)) }))
    .filter((g) => g.items.length > 0)

  return (
    <>
      <div className="row between">
        <h1>Keşif Çizim Standardı (KÇS)</h1>
        <div className="row">
          <a className="btn" href={Api.catalog.templateUrl}>Şablon DXF indir</a>
          <a className="btn secondary" href="https://github.com/HuseyinEfkanAlp/KesifProjesi/blob/main/docs/KESIF_CIZIM_STANDARDI.md" target="_blank" rel="noreferrer">Standart dokümanı</a>
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="grid2">
        <div className="panel">
          <h3>Kural</h3>
          <p>
            Katman adı kalemi tanımlar, geometri miktarı verir: <code className="layer">KSF-&lt;DİSİPLİN&gt;-&lt;KALEM&gt;-&lt;ÖZELLİK&gt;</code>.
            Alan ayracı tire, kelime içi alt çizgi. <code className="layer">KSF-</code> ile başlamayan katmanlar metraja girmez.
          </p>
          <ul className="muted" style={{ margin: '6px 0 0 18px', padding: 0 }}>
            <li><b>Adet</b> kalemleri blok (INSERT) olarak yerleştirilir.</li>
            <li><b>Uzunluk</b> kalemleri tek eksen çizgisi / polyline (çift çizgi değil).</li>
            <li><b>Alan</b> kalemleri kapalı polyline ya da tarama.</li>
            <li><b>Duvar</b> kalemleri eksen çizgisi; özellikte kalınlık[xyükseklik] cm: <code className="layer">KSF-MIM-DUVAR_YTONG-20x300</code>.</li>
            <li><b>Hacim</b> kalemleri kapalı alan; özellikte kalınlık cm: <code className="layer">KSF-STA-DOLGU-30</code>.</li>
            <li>Birim mm, her plan ayrı pafta, xref yok, teslim DXF.</li>
          </ul>
          <p className="muted">Programa yüklerken disiplin olarak <b>KSF standart çizim</b> seçilir; katman eşleme gerekmez. Tanınmayan kalemler geometriye göre ölçülür ve uyarı verir.</p>
        </div>
        <div className="panel">
          <h3>Katman adı dene</h3>
          <div className="row">
            <input className="wide" style={{ width: 340 }} value={test} onChange={(e) => setTest(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doCheck()} />
            <button onClick={doCheck}>Kontrol et</button>
          </div>
          {check && (
            <div className={check.valid ? 'warn' : 'error'} style={{ marginTop: 8 }}>
              {check.valid ? (
                <>
                  <div><b className="ok">Geçerli.</b> Disiplin: {check.discipline_name} ({check.discipline}) · Kalem: <code className="layer">{check.code}</code> · Özellik: {check.spec ?? '-'}</div>
                  <div className="muted">{check.known ? `${check.item?.name} · ${check.measure} · birim ${check.item?.unit}` : check.measure}</div>
                </>
              ) : <span>Geçersiz: {check.reason}</span>}
            </div>
          )}
          <h3>Yeni kalem ekle</h3>
          <form className="row" onSubmit={addItem}>
            <label className="field">Disiplin
              <select value={form.discipline} onChange={(e) => setForm({ ...form, discipline: e.target.value })}>
                {Object.entries(cat.disciplines).map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}
              </select>
            </label>
            <label className="field">Kalem kodu<input style={{ width: 150 }} value={form.code} placeholder="HAVA_KANAL" onChange={(e) => setForm({ ...form, code: e.target.value })} required /></label>
            <label className="field">Ad<input style={{ width: 180 }} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
            <label className="field">Ölçüm
              <select value={form.measure} onChange={(e) => setForm({ ...form, measure: e.target.value })}>
                {Object.entries(cat.measures).map(([m, v]) => <option key={m} value={m}>{v.label} ({v.unit})</option>)}
              </select>
            </label>
            <label className="field">Özellik anlamı<input style={{ width: 160 }} value={form.spec_label} placeholder="çap (mm)" onChange={(e) => setForm({ ...form, spec_label: e.target.value })} /></label>
            <label className="field" title="Katmanlı sistem: bu kalem ölçülünce ayrı iş kalemi olarak yazılacak bileşenler. Biçim: KOD×çarpan:özellik; …">
              Bileşenler (katmanlı sistem)
              <input style={{ width: 300 }} value={form.components} placeholder="OSB×1:11; TASYUNU×1:10; MERTEK×1.7:5x10" onChange={(e) => setForm({ ...form, components: e.target.value })} />
            </label>
            <button type="submit">Ekle</button>
          </form>
          <p className="muted hint">
            Bileşenli kalem ölçüldüğünde (ör. çatı alanı) her bileşen için miktar = alan × çarpan yazılır; bileşen kodları katalogda olmalı.
            Var olan bir sistemi değiştirmek için aynı kodla yeniden ekleyin.
          </p>
          <h3>Yeni disiplin</h3>
          <form className="row" onSubmit={addDisc}>
            <label className="field">Kod (3 harf)<input style={{ width: 70 }} value={dform.code} maxLength={3} onChange={(e) => setDform({ ...dform, code: e.target.value.toUpperCase() })} required /></label>
            <label className="field">Ad<input style={{ width: 220 }} value={dform.name} onChange={(e) => setDform({ ...dform, name: e.target.value })} required /></label>
            <button type="submit">Ekle</button>
            <button type="button" className="secondary" onClick={() => { if (confirm('Katalog varsayılana döndürülsün mü? Eklediğiniz kalemler silinir.')) run(() => Api.catalog.reset()) }}>Varsayılana dön</button>
          </form>
        </div>
      </div>

      <div className="panel">
        <div className="row between">
          <h3>Kalem kataloğu ({cat.items.length} kalem, {Object.keys(cat.disciplines).length} disiplin)</h3>
          <div className="row">
            <select value={disc} onChange={(e) => setDisc(e.target.value)}>
              <option value="">Tüm disiplinler</option>
              {Object.entries(cat.disciplines).map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}
            </select>
            <input placeholder="ara: kanal, boru, PVC…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
        </div>
        {groups.map((g) => (
          <div key={g.code}>
            <h2>{g.code} · {g.name}</h2>
            <table>
              <thead><tr><th>Katman adı (örnek)</th><th>Kalem</th><th>Ölçüm</th><th>Birim</th><th>Özellik</th><th>Bileşenler</th><th>Nasıl çizilir</th><th></th></tr></thead>
              <tbody>
                {g.items.map((it) => (
                  <tr key={it.code}>
                    <td><code className="layer">{it.example}</code></td>
                    <td>{it.name}{it.custom && <span className="muted"> (eklendi)</span>}</td>
                    <td>{it.measure_label}</td>
                    <td>{it.unit}</td>
                    <td className="muted">{it.spec_label || '-'}</td>
                    <td className="muted hint">{it.is_system ? it.components.map((c) => `${cat.items.find((x) => x.code === c.code)?.name ?? c.code} ×${c.factor}${c.spec ? ` (${c.spec})` : ''}`).join('; ') : '-'}</td>
                    <td className="muted">{MEASURE_HINT[it.measure]}</td>
                    <td><button className="danger small" onClick={() => { if (confirm(`${it.code} katalogdan silinsin mi?`)) run(() => Api.catalog.removeItem(it.code)) }}>Sil</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </>
  )
}
