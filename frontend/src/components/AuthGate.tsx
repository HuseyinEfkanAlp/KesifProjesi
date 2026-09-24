import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Api, SESSION_LOST, type Me } from '../api/client'
import Icon from './Icon'

interface AuthCtx {
  me: Me
  logout: () => Promise<void>
  /** Görüntüleyen rolü: değişiklik yapamaz (sunucu da reddeder, bu yalnız arayüz ipucu) */
  readOnly: boolean
}

const Ctx = createContext<AuthCtx | null>(null)

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth, AuthGate içinde kullanılmalı')
  return c
}

/** Uygulamanın kapısı: ilk açılışta kurulum, oturum yoksa giriş, varsa içerik. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'setup' | 'login' | 'in' | 'down'>('loading')
  const [me, setMe] = useState<Me | null>(null)
  const [notice, setNotice] = useState('')

  const check = useCallback(() => {
    Api.auth.status()
      .then((s) => {
        setMe(s.me)
        setState(s.needs_setup ? 'setup' : s.me ? 'in' : 'login')
      })
      .catch(() => setState('down'))
  }, [])

  useEffect(() => { check() }, [check])

  useEffect(() => {
    const lost = () => {
      setMe(null)
      setNotice('Oturumunuz sona erdi. Lütfen tekrar giriş yapın.')
      setState('login')
    }
    window.addEventListener(SESSION_LOST, lost)
    return () => window.removeEventListener(SESSION_LOST, lost)
  }, [])

  const enter = (m: Me) => { setMe(m); setNotice(''); setState('in') }
  const logout = async () => {
    try { await Api.auth.logout() } catch { /* zaten düşmüş olabilir */ }
    setMe(null)
    setNotice('')
    setState('login')
  }

  if (state === 'loading') return <div className="auth-screen"><div className="auth-card" role="status">Yükleniyor…</div></div>
  if (state === 'down') {
    return (
      <AuthShell title="Sunucuya ulaşılamıyor">
        <p className="muted">Keşif sunucusu yanıt vermiyor. Sunucunun çalıştığından emin olun ve tekrar deneyin.</p>
        <button onClick={() => { setState('loading'); check() }}>Tekrar dene</button>
      </AuthShell>
    )
  }
  if (state === 'setup') return <SetupForm onDone={enter} />
  if (state === 'login' || !me) return <LoginForm onDone={enter} notice={notice} />
  return <Ctx.Provider value={{ me, logout, readOnly: me.user.role === 'goruntuleyen' }}>{children}</Ctx.Provider>
}

function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="auth-screen">
      <main className="auth-card">
        <div className="auth-brand"><span className="brand-symbol"><Icon name="layers" size={24} /></span><span>keşif<span className="brand-caption">PROJE & METRAJ</span></span></div>
        <h1>{title}</h1>
        {subtitle && <p className="muted auth-subtitle">{subtitle}</p>}
        {children}
      </main>
    </div>
  )
}

function LoginForm({ onDone, notice }: { onDone: (m: Me) => void; notice: string }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try { onDone(await Api.auth.login(email, password)) } catch (ex) { setError((ex as Error).message) } finally { setBusy(false) }
  }
  return (
    <AuthShell title="Giriş yap" subtitle="Projelerinize ve metrajlarınıza ulaşmak için giriş yapın.">
      {notice && !error && <div className="auth-notice" role="status">{notice}</div>}
      <form className="auth-form" onSubmit={submit}>
        <label className="field">E-posta<input type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field">Şifre<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <div className="error" role="alert">{error}</div>}
        <button type="submit" disabled={busy}>{busy ? 'Giriş yapılıyor…' : 'Giriş yap'}</button>
      </form>
      <p className="muted auth-foot">Şifrenizi unuttuysanız şirketinizin hesap sahibine başvurun; size yeni şifre verebilir.</p>
    </AuthShell>
  )
}

function SetupForm({ onDone }: { onDone: (m: Me) => void }) {
  const [form, setForm] = useState({ company_name: '', name: '', email: '', password: '', again: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (form.password !== form.again) { setError('Şifreler birbirini tutmuyor.'); return }
    setBusy(true)
    setError('')
    try {
      onDone(await Api.auth.setup({ company_name: form.company_name, name: form.name, email: form.email, password: form.password }))
    } catch (ex) { setError((ex as Error).message) } finally { setBusy(false) }
  }
  return (
    <AuthShell title="Hoş geldiniz" subtitle="İlk açılış. Hesabınızı oluşturun; bu hesap şirketin sahibi olur ve diğer kullanıcıları ekleyebilir. Mevcut projelerinizin hepsi bu hesaba bağlanır.">
      <form className="auth-form" onSubmit={submit}>
        <label className="field">Şirket adı<input autoComplete="organization" value={form.company_name} onChange={set('company_name')} placeholder="Örn. Turan İnşaat" /></label>
        <label className="field">Adınız soyadınız<input autoComplete="name" required value={form.name} onChange={set('name')} /></label>
        <label className="field">E-posta<input type="email" autoComplete="username" required value={form.email} onChange={set('email')} /></label>
        <label className="field">Şifre<input type="password" autoComplete="new-password" required minLength={8} value={form.password} onChange={set('password')} /><small className="muted">En az 8 karakter</small></label>
        <label className="field">Şifre (tekrar)<input type="password" autoComplete="new-password" required minLength={8} value={form.again} onChange={set('again')} /></label>
        {error && <div className="error" role="alert">{error}</div>}
        <button type="submit" disabled={busy}>{busy ? 'Oluşturuluyor…' : 'Hesabı oluştur ve başla'}</button>
      </form>
    </AuthShell>
  )
}
