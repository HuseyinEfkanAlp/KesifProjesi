import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import Icon from './components/Icon'

export default function App() {
  const { pathname } = useLocation()
  const section = pathname === '/standard' ? 'Çizim standardı' : pathname === '/pricebook' ? 'Fiyatlar ve tedarikçiler'
    : pathname === '/projects/new' ? 'Yeni proje' : pathname === '/' ? 'Projeler' : 'Proje çalışma alanı'
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">İçeriğe geç</a>
      <aside className="sidebar">
        <Link to="/" className="brand"><span className="brand-symbol"><Icon name="layers" size={26} /></span><span>keşif<span className="brand-caption">PROJE & METRAJ</span></span></Link>
        <div className="nav-label">ÇALIŞMA ALANI</div>
        <nav className="side-nav" aria-label="Ana menü">
          <NavLink to="/" end className={() => pathname !== '/standard' && pathname !== '/pricebook' ? 'active' : ''}><Icon name="grid" />Projeler</NavLink>
          <NavLink to="/pricebook"><Icon name="tag" />Fiyatlar ve tedarikçiler</NavLink>
          <NavLink to="/standard"><Icon name="book" />Çizim standardı</NavLink>
        </nav>
        <div className="sidebar-footer"><span className="workspace-avatar">K</span><div>Keşif çalışma alanı<small>Metraj · Maliyet · Planlama</small></div></div>
      </aside>
      <div className="workspace">
        <header className="topbar"><div className="breadcrumb"><span>Çalışma alanı</span><span className="breadcrumb-slash">/</span><strong>{section}</strong></div><span className="workspace-tag">DXF / DWG</span></header>
        <main className="content" id="main-content"><Outlet /></main>
      </div>
    </div>
  )
}
