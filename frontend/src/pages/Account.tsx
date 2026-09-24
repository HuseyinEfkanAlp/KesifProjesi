import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Api, type Role, type UserRow } from '../api/client'
import { useAuth } from '../components/AuthGate'

const ROLE_NAMES: Record<Role, string> = { sahibi: 'Sahibi', uzman: 'Uzman', goruntuleyen: 'Görüntüleyen' }
const ROLE_HELP: Record<Role, string> = {
  sahibi: 'Her şeyi yapar, kullanıcı ekler ve çıkarır',
  uzman: 'Proje açar, çizim yükler, metrajı onaylar',
  goruntuleyen: 'Yalnız bakar ve rapor indirir',
}

const when = (iso: string | null) => (iso ? new Date(iso + 'Z').toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }) : 'Hiç girmedi')

export default function Account() {
  const { me } = useAuth()
  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">HESAP</div><h1>Hesap ve ekip</h1><p className="muted">{me.company.name}</p></div></div>
      <div className="grid2">
        <section className="panel" aria-label="Hesabım">
          <h2>Hesabım</h2>
          <dl className="account-facts">
            <dt>Ad</dt><dd>{me.user.name || '—'}</dd>
            <dt>E-posta</dt><dd>{me.user.email}</dd>
            <dt>Rol</dt><dd>{ROLE_NAMES[me.user.role]} <span className="muted">— {ROLE_HELP[me.user.role]}</span></dd>
          </dl>
        </section>
        <PasswordForm />
      </div>
      {me.user.role === 'sahibi' && <Team myId={me.user.id} />}
    </>
  )
}

function PasswordForm() {
  const [f, setF] = useState({ current: '', next: '', again: '' })
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (f.next !== f.again) { setMsg({ ok: false, text: 'Yeni şifreler birbirini tutmuyor.' }); return }
    setBusy(true)
    try {
      await Api.auth.changePassword(f.current, f.next)
      setF({ current: '', next: '', again: '' })
      setMsg({ ok: true, text: 'Şifreniz değişti. Diğer cihazlardaki oturumlarınız kapatıldı.' })
    } catch (ex) { setMsg({ ok: false, text: (ex as Error).message }) } finally { setBusy(false) }
  }
  return (
    <section className="panel" aria-label="Şifre değiştir">
      <h2>Şifre değiştir</h2>
      <form className="stack-form" onSubmit={submit}>
        <label className="field">Mevcut şifre<input type="password" autoComplete="current-password" required value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></label>
        <label className="field">Yeni şifre<input type="password" autoComplete="new-password" required minLength={8} value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></label>
        <label className="field">Yeni şifre (tekrar)<input type="password" autoComplete="new-password" required minLength={8} value={f.again} onChange={(e) => setF({ ...f, again: e.target.value })} /></label>
        {msg && <div className={msg.ok ? 'success' : 'error'} role={msg.ok ? 'status' : 'alert'}>{msg.text}</div>}
        <div><button type="submit" disabled={busy}>Şifreyi değiştir</button></div>
      </form>
    </section>
  )
}

function Team({ myId }: { myId: number }) {
  const [users, setUsers] = useState<UserRow[]>([])
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [f, setF] = useState<{ name: string; email: string; password: string; role: Role }>({ name: '', email: '', password: '', role: 'uzman' })
  const load = useCallback(() => Api.users.list().then(setUsers).catch((e) => setError(e.message)), [])
  useEffect(() => { load() }, [load])

  const act = async (fn: () => Promise<unknown>, done = '') => {
    setError('')
    setInfo('')
    try { await fn(); await load(); if (done) setInfo(done) } catch (ex) { setError((ex as Error).message) }
  }
  const add = (e: FormEvent) => {
    e.preventDefault()
    act(async () => {
      await Api.users.add(f)
      setF({ name: '', email: '', password: '', role: 'uzman' })
    }, `${f.email} eklendi. E-posta ve şifreyi kişiye siz iletin; girdikten sonra şifresini değiştirebilir.`)
  }
  const reset = (u: UserRow) => {
    const pw = prompt(`${u.email} için yeni şifre (en az 8 karakter):`)
    if (!pw) return
    act(() => Api.users.resetPassword(u.id, pw), `${u.email} için yeni şifre kaydedildi; açık oturumları kapatıldı.`)
  }

  return (
    <section className="panel" aria-label="Ekip">
      <h2>Ekip <span className="count-pill">{users.filter((u) => u.active).length}</span></h2>
      <p className="muted">Şirketinizdeki kullanıcılar ve yetkileri. Kullanıcılar silinmez, kapatılır: onayladıkları metrajlarda adları durur.</p>
      {error && <div className="error" role="alert">{error}</div>}
      {info && <div className="success" role="status">{info}</div>}
      <div className="table-scroll">
        <table>
          <thead><tr><th>Kullanıcı</th><th>Rol</th><th>Son giriş</th><th>Durum</th><th /></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.id} className={u.active ? '' : 'muted'}>
              <td><strong>{u.name || u.email}</strong>{u.name && <div className="muted">{u.email}</div>}{u.id === myId && <span className="chip">siz</span>}</td>
              <td>
                <select aria-label={`${u.email} rolü`} value={u.role} disabled={!u.active} onChange={(e) => act(() => Api.users.patch(u.id, { role: e.target.value as Role }))}>
                  {(Object.keys(ROLE_NAMES) as Role[]).map((r) => <option key={r} value={r}>{ROLE_NAMES[r]}</option>)}
                </select>
              </td>
              <td>{when(u.last_login)}</td>
              <td>{u.active ? 'Etkin' : 'Kapalı'}</td>
              <td><div className="row">
                {u.active && u.id !== myId && <button className="secondary small" onClick={() => reset(u)}>Şifre ver</button>}
                {u.id !== myId && (u.active
                  ? <button className="secondary small" onClick={() => confirm(`${u.email} hesabı kapatılsın mı? Kişi giriş yapamaz, açık oturumu düşer.`) && act(() => Api.users.patch(u.id, { active: false }))}>Kapat</button>
                  : <button className="secondary small" onClick={() => act(() => Api.users.patch(u.id, { active: true }))}>Yeniden aç</button>)}
              </div></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <h3>Kullanıcı ekle</h3>
      <form className="row add-user-form" onSubmit={add}>
        <label className="field">Ad soyad<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label className="field">E-posta<input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label className="field">Başlangıç şifresi<input type="text" required minLength={8} autoComplete="off" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
        <label className="field">Rol
          <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            {(Object.keys(ROLE_NAMES) as Role[]).map((r) => <option key={r} value={r}>{ROLE_NAMES[r]} — {ROLE_HELP[r]}</option>)}
          </select>
        </label>
        <button type="submit">Ekle</button>
      </form>
    </section>
  )
}
