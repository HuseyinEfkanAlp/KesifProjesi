import { Link, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">Keşif</Link>
        <span className="muted">DXF planından metraj ve maliyet</span>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
