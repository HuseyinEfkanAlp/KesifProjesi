import { Link, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">Keşif</Link>
        <span className="muted">DXF planından keşif, maliyet ve süre</span>
        <span style={{ flex: 1 }} />
        <Link to="/standard" className="topnav">Çizim standardı (KÇS)</Link>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
