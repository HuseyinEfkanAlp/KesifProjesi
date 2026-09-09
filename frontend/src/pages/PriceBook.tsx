import { Fragment, useEffect, useState } from 'react'
import Loading from '../components/Loading'
import { Api, fmt } from '../api/client'
import Icon from '../components/Icon'
import type { PriceBook, PriceBookIn, PriceBookProduct, Supplier, SupplierIn } from '../types'

type Tab = 'material' | 'labor' | 'suppliers'
type Edit = { price?: number | string; brand?: string; supplier_id?: number | null; hours_per_unit?: number | string; crew_size?: number | string }

const GROUP_ORDER = ['KABA', 'INCE', 'MEK', 'ELK', 'ALT']
const EMPTY_SUPPLIER: SupplierIn = { name: '', contact: '', phone: '', email: '', note: '' }

export default function PriceBook() {
  const [tab, setTab] = useState<Tab>('material')
  const [book, setBook] = useState<PriceBook | null>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [edited, setEdited] = useState<Record<string, Edit>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')
  const [group, setGroup] = useState('')
  const [onlyPriced, setOnlyPriced] = useState(false)
  const [openKey, setOpenKey] = useState('')
  const [form, setForm] = useState<SupplierIn>(EMPTY_SUPPLIER)
  const [editSupplier, setEditSupplier] = useState<number | null>(null)

  const scope: 'material' | 'labor' = tab === 'labor' ? 'labor' : 'material'
  const load = (s: 'material' | 'labor' = scope) => Promise.all([Api.pricebook.get(s), Api.suppliers.list()])
    .then(([b, sup]) => { setBook(b); setSuppliers(sup); setEdited({}) })
    .catch((e) => setError(e.message))
  useEffect(() => { load(scope) }, [scope]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key: string, field: keyof Edit, value: string) => {
    setSaved(false)
    const v = field === 'brand' ? value : field === 'supplier_id' ? (value === '' ? null : +value) : (value === '' ? '' : +value)
    setEdited({ ...edited, [key]: { ...(edited[key] || {}), [field]: v } })
  }
  const val = (p: PriceBookProduct, field: keyof Edit) => {
    const e = edited[p.key]
    if (e && field in e) return e[field] as string | number | null
    if (field === 'brand') return p.brand
    if (field === 'supplier_id') return p.rows.length === 1 ? p.rows[0].supplier_id : null
    if (field === 'price') return p.price > 0 ? p.price : ''
    return p[field as 'hours_per_unit' | 'crew_size'] > 0 ? p[field as 'hours_per_unit' | 'crew_size'] : ''
  }

  const save = async () => {
    setError(''); setSaved(false); setBusy(true)
    try {
      const num = (v: number | string | null | undefined) => v === '' || v == null ? 0 : +v
      const rows: PriceBookIn[] = Object.entries(edited).map(([ek, e]) => {
        // "row:<id>": var olan teklif satırı; yoksa ürünün tek satırı ya da yeni satır
        const rowId = ek.startsWith('row:') ? +ek.slice(4) : 0
        const p = (book?.products ?? []).find((x) => rowId ? x.rows.some((r) => r.id === rowId) : x.key === ek)
        const key = p?.key ?? ek
        const base = rowId ? p?.rows.find((r) => r.id === rowId) : (p && p.rows.length === 1 ? p.rows[0] : undefined)
        return {
          key, scope, ...(base ? { id: base.id } : {}),
          ...(e.supplier_id !== undefined ? { supplier_id: e.supplier_id } : {}),
          ...(e.brand !== undefined ? { brand: e.brand } : {}),
          ...(e.price !== undefined ? (scope === 'material' ? { unit_price: num(e.price) } : { labor_price: num(e.price) }) : {}),
          ...(e.hours_per_unit !== undefined ? { hours_per_unit: num(e.hours_per_unit) } : {}),
          ...(e.crew_size !== undefined ? { crew_size: num(e.crew_size) } : {}),
        }
      })
      await Api.pricebook.save(rows)
      await load(); setSaved(true)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const addQuote = async (p: PriceBookProduct, supplierId: number) => {
    setBusy(true); setError('')
    try {
      await Api.pricebook.save([{ key: p.key, scope, supplier_id: supplierId, unit_price: 0 }])
      await load(); setOpenKey(p.key)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const rowAction = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await fn(); await load() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const saveSupplier = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) return
    await rowAction(() => editSupplier ? Api.suppliers.update(editSupplier, form) : Api.suppliers.create(form))
    setForm(EMPTY_SUPPLIER); setEditSupplier(null)
  }

  if (!book) return <Loading error={error} />
  const dirty = Object.keys(edited).length
  const qq = q.trim().toLocaleLowerCase('tr-TR')
  const match = (p: PriceBookProduct) => (!qq || p.name.toLocaleLowerCase('tr-TR').includes(qq) || p.key.includes(qq))
    && (!onlyPriced || p.price > 0 || p.rows.length > 0)
  const groupKeys = Array.from(new Set(book.products.map((p) => p.work_group)))
    .sort((a, b) => (GROUP_ORDER.indexOf(a) === -1 ? 99 : GROUP_ORDER.indexOf(a)) - (GROUP_ORDER.indexOf(b) === -1 ? 99 : GROUP_ORDER.indexOf(b)))
  const groups = groupKeys.filter((g) => !group || g === group)
    .map((g) => ({ g, label: book.products.find((p) => p.work_group === g)?.work_group_label ?? g, rows: book.products.filter((p) => p.work_group === g && match(p)) }))
    .filter((x) => x.rows.length > 0)
  const priced = book.products.filter((p) => p.price > 0).length

  const supplierSelect = (value: number | null, onChange: (v: string) => void) => (
    <select value={value ?? ''} onChange={(e) => onChange(e.target.value)} style={{ maxWidth: 150 }}>
      <option value="">tedarikçi yok</option>
      {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  )

  return (
    <>
      <div className="row between" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Fiyatlar ve tedarikçiler</h2>
        <div className="chips" style={{ margin: 0 }}>
          <button className={`chip-btn${tab === 'material' ? ' on' : ''}`} onClick={() => setTab('material')}>Malzeme (ürün)</button>
          <button className={`chip-btn${tab === 'labor' ? ' on' : ''}`} onClick={() => setTab('labor')}>İşçilik</button>
          <button className={`chip-btn${tab === 'suppliers' ? ' on' : ''}`} onClick={() => setTab('suppliers')}>Tedarikçiler ({suppliers.length})</button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      {tab === 'suppliers' && (
        <div className="panel">
          <h3>Tedarikçiler ve taşeronlar</h3>
          <p className="muted hint">Fiyat satırları tedarikçiye bağlanır; aynı ürüne birden çok tedarikçi fiyatı girip karşılaştırabilirsiniz.</p>
          <form className="row" onSubmit={saveSupplier} style={{ flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            <input placeholder="firma adı" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ width: 200 }} />
            <input placeholder="yetkili" value={form.contact ?? ''} onChange={(e) => setForm({ ...form, contact: e.target.value })} style={{ width: 140 }} />
            <input placeholder="telefon" value={form.phone ?? ''} onChange={(e) => setForm({ ...form, phone: e.target.value })} style={{ width: 130 }} />
            <input placeholder="e-posta" value={form.email ?? ''} onChange={(e) => setForm({ ...form, email: e.target.value })} style={{ width: 170 }} />
            <input placeholder="not" value={form.note ?? ''} onChange={(e) => setForm({ ...form, note: e.target.value })} style={{ width: 200 }} />
            <button type="submit" disabled={busy || !form.name.trim()}>{editSupplier ? 'Güncelle' : 'Ekle'}</button>
            {editSupplier && <button type="button" className="secondary" onClick={() => { setEditSupplier(null); setForm(EMPTY_SUPPLIER) }}>Vazgeç</button>}
          </form>
          {suppliers.length === 0 && <p className="muted">Henüz tedarikçi yok.</p>}
          {suppliers.length > 0 && (
            <table className="table-compact">
              <thead><tr><th>Firma</th><th>Yetkili</th><th>Telefon</th><th>E-posta</th><th>Not</th><th className="num">Fiyat satırı</th><th></th></tr></thead>
              <tbody>
                {suppliers.map((s) => (
                  <tr key={s.id}>
                    <td><b>{s.name}</b></td><td>{s.contact}</td><td className="mono">{s.phone}</td><td>{s.email}</td>
                    <td className="muted">{s.note}</td><td className="num">{s.price_count ?? 0}</td>
                    <td className="row" style={{ gap: 4 }}>
                      <button className="icon-button" title="Düzenle" onClick={() => { setEditSupplier(s.id); setForm({ name: s.name, contact: s.contact, phone: s.phone, email: s.email, note: s.note }) }}><Icon name="edit" size={15} /></button>
                      <button className="icon-button" title="Sil" onClick={() => { if (confirm(`"${s.name}" silinsin mi? Fiyat satırları kalır, tedarikçi bağlantısı boşalır.`)) rowAction(() => Api.suppliers.remove(s.id)) }}><Icon name="trash" size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab !== 'suppliers' && (
        <div className="panel">
          <div className="row between sticky-bar">
            <div className="row" style={{ gap: 12 }}>
              <h3 style={{ margin: 0 }}>{tab === 'material' ? 'Ürün fiyatları' : 'İşçilik fiyatları'}</h3>
              <span className="count-pill">{priced} / {book.products.length} fiyatlı</span>
              <input placeholder="ara: beton, ytong, kablo…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 210 }} />
              <button className={`chip-btn${onlyPriced ? ' on' : ''}`} onClick={() => setOnlyPriced(!onlyPriced)}>yalnız fiyatı girilenler</button>
            </div>
            <div className="row">
              {saved && !dirty && <span className="ok">Kaydedildi</span>}
              {dirty > 0 && <span className="muted">{dirty} satır değişti</span>}
              <button onClick={save} disabled={dirty === 0 || busy}>Kaydet</button>
            </div>
          </div>
          <p className="muted hint">
            {tab === 'material'
              ? <>Buraya girilen fiyatlar bütün projelerde kullanılır: yeni bir projede ürün fiyatları buradan dolar.
                Bir ürüne birden çok tedarikçi fiyatı girebilirsiniz; geçerli fiyat <b>seçtiğiniz</b> satır, seçim yoksa en düşük olandır.
                Türün genel satırı ("… tür geneli") o türün özellikli ürünlerine de uygulanır.</>
              : <>İşçilik birim fiyatı, adam-saat / birim ve ekip kalem türü bazında. Yeni projede kalemlerin genel satırları buradan dolar.</>}
          </p>
          <div className="chips" style={{ margin: '6px 0 10px' }}>
            <button className={`chip-btn${group === '' ? ' on' : ''}`} onClick={() => setGroup('')}>Tümü</button>
            {groupKeys.map((g) => (
              <button key={g} className={`chip-btn${group === g ? ' on' : ''}`} onClick={() => setGroup(group === g ? '' : g)}>
                {book.products.find((p) => p.work_group === g)?.work_group_label} ({book.products.filter((p) => p.work_group === g).length})
              </button>
            ))}
          </div>
          {groups.length === 0 && <p className="muted">Aramayla eşleşen ürün yok.</p>}
          {groups.map(({ g, label, rows }) => (
            <details key={g} className="catalog-group" open={groups.length <= 2 || !!qq || !!group}>
              <summary><b>{label}</b><span className="muted"> · {rows.length} kalem · {rows.filter((p) => p.price > 0).length} fiyatlı</span></summary>
              <table className="table-compact price-table">
                <thead>
                  <tr>
                    <th>Ürün</th><th>Birim</th>
                    {tab === 'material' ? <><th>Marka</th><th>Tedarikçi</th><th className="num">₺ / birim</th><th></th></>
                      : <><th className="num">₺ / birim</th><th className="num">A-saat / birim</th><th className="num">Ekip</th><th>Tedarikçi / taşeron</th></>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p) => {
                    const open = openKey === p.key
                    return (
                      <Fragment key={p.key}>
                        <tr>
                          <td>
                            <b>{p.name}</b>
                            {p.in_projects && <span className="badge recipe" style={{ marginLeft: 6 }}>projede</span>}
                            {p.rows.length > 1 && (
                              <span className="muted hint" style={{ marginLeft: 6, cursor: 'pointer' }} onClick={() => setOpenKey(open ? '' : p.key)}>
                                · {p.rows.length} teklif {open ? '▴' : '▾'}
                              </span>
                            )}
                          </td>
                          <td>{p.unit}</td>
                          {tab === 'material' ? (
                            <>
                              <td><input className="wide" value={val(p, 'brand') as string} placeholder="marka" onChange={(e) => set(p.key, 'brand', e.target.value)} /></td>
                              <td>{p.rows.length > 1 ? <span className="muted">{p.supplier_name || '-'}</span>
                                : supplierSelect(val(p, 'supplier_id') as number | null, (v) => set(p.key, 'supplier_id', v))}</td>
                              <td className="num">
                                {p.rows.length > 1
                                  ? <b title="Seçili teklifin fiyatı; tekliflerden değiştirin">{fmt(p.price)}</b>
                                  : <input type="number" min={0} step="0.01" className={`wide${edited[p.key]?.price !== undefined ? ' dirty' : ''}`}
                                      value={val(p, 'price') as number} placeholder="0" onChange={(e) => set(p.key, 'price', e.target.value)} />}
                              </td>
                              <td>
                                {suppliers.length > 0 && (
                                  <select value="" onChange={(e) => e.target.value && addQuote(p, +e.target.value)} title="Bu ürüne başka tedarikçinin fiyatını ekle" style={{ width: 110 }}>
                                    <option value="">+ teklif</option>
                                    {suppliers.filter((s) => !p.rows.some((r) => r.supplier_id === s.id)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                                  </select>
                                )}
                              </td>
                            </>
                          ) : (
                            <>
                              <td className="num"><input type="number" min={0} step="0.01" className={`wide${edited[p.key]?.price !== undefined ? ' dirty' : ''}`}
                                value={val(p, 'price') as number} placeholder="0" onChange={(e) => set(p.key, 'price', e.target.value)} /></td>
                              <td className="num"><input type="number" min={0} step="0.001" className="wide" value={val(p, 'hours_per_unit') as number} placeholder="0"
                                onChange={(e) => set(p.key, 'hours_per_unit', e.target.value)} /></td>
                              <td className="num"><input type="number" min={0} step="1" className="wide" value={val(p, 'crew_size') as number} placeholder="0"
                                onChange={(e) => set(p.key, 'crew_size', e.target.value)} /></td>
                              <td>{supplierSelect(val(p, 'supplier_id') as number | null, (v) => set(p.key, 'supplier_id', v))}</td>
                            </>
                          )}
                        </tr>
                        {open && p.rows.map((r) => {
                          const rk = `row:${r.id}`
                          const price = edited[rk]?.price !== undefined ? edited[rk].price : ((scope === 'material' ? r.unit_price : r.labor_price) || '')
                          return (
                            <tr key={rk} className="general">
                              <td style={{ paddingLeft: 26 }} className="muted">
                                {r.supplier_name || 'tedarikçi yok'}
                                {r.preferred && <span className="badge recipe" style={{ marginLeft: 6 }}>seçili</span>}
                              </td>
                              <td className="muted">{r.unit}</td>
                              <td><input className="wide" value={(edited[rk]?.brand ?? r.brand) as string} placeholder="marka"
                                onChange={(e) => set(rk, 'brand', e.target.value)} /></td>
                              <td className="muted">{r.note}</td>
                              <td className="num"><input type="number" min={0} step="0.01" className={`wide${edited[rk]?.price !== undefined ? ' dirty' : ''}`}
                                value={price as number} placeholder="0" onChange={(e) => set(rk, 'price', e.target.value)} /></td>
                              <td className="row" style={{ gap: 4 }}>
                                {!r.preferred && <button className="chip-btn" title="Bu tedarikçinin fiyatını kullan"
                                  onClick={() => rowAction(() => Api.pricebook.save([{ key: p.key, scope, id: r.id, preferred: true }]))}>bunu kullan</button>}
                                <button className="icon-button" title="Teklifi sil" onClick={() => rowAction(() => Api.pricebook.remove(r.id))}><Icon name="trash" size={15} /></button>
                              </td>
                            </tr>
                          )
                        })}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </details>
          ))}
          <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}>
            <button onClick={save} disabled={dirty === 0 || busy}>Kaydet</button>
          </div>
        </div>
      )}
    </>
  )
}
