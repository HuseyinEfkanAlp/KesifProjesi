import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import Icon from './components/Icon'
import { useAuth } from './components/AuthGate'

export default function App() {
  const { pathname } = useLocation()
  const { me, logout, readOnly } = useAuth()
  const section = pathname === '/account' ? 'Hesap ve ekip' : pathname === '/standard' ? 'Çizim standardı' : pathname === '/pricebook' ? 'Fiyatlar ve tedarikçiler'
    : pathname === '/projects/new' ? 'Yeni proje' : pathname === '/' ? 'Projeler' : 'Proje çalışma alanı'
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">İçeriğe geç</a>
      <aside className="sidebar">
        <Link to="/" className="brand"><span className="brand-symbol"><Icon name="layers" size={26} /></span><span>keşif<span className="brand-caption">PROJE & METRAJ</span></span></Link>
        <div className="nav-label">ÇALIŞMA ALANI</div>
        <nav className="side-nav" aria-label="Ana menü">
          <NavLink to="/" end className={() => !['/standard', '/pricebook', '/account'].includes(pathname) ? 'active' : ''}><Icon name="grid" />Projeler</NavLink>
          <NavLink to="/pricebook"><Icon name="tag" />Fiyatlar ve tedarikçiler</NavLink>
          <NavLink to="/standard"><Icon name="book" />Çizim standardı</NavLink>
          <NavLink to="/account"><Icon name="user" />{me.user.role === 'sahibi' ? 'Hesap ve ekip' : 'Hesabım'}</NavLink>
        </nav>
        <div className="sidebar-footer"><span className="workspace-avatar" aria-hidden="true">{(me.user.name || me.user.email).charAt(0).toLocaleUpperCase('tr-TR')}</span><div className="sidebar-user"><div title={me.user.email}>{me.user.name || me.user.email}</div><small>{me.company.name}</small></div><button className="logout" onClick={logout}>Çıkış</button></div>
      </aside>
      <div className="workspace">
        <header className="topbar"><div className="breadcrumb"><span>Çalışma alanı</span><span className="breadcrumb-slash">/</span><strong>{section}</strong></div>{readOnly ? <span className="readonly-tag" title="Hesabınız yalnız görüntüleme yetkisine sahip">Yalnız görüntüleme</span> : <span className="workspace-tag">DXF / DWG</span>}</header>
        <main className="content" id="main-content"><Outlet /></main>
      </div>
    </div>
  )
}
