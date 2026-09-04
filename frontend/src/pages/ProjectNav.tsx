import { NavLink } from 'react-router-dom'

export default function ProjectNav({ id, name }: { id: number; name?: string }) {
  const cls = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')
  return (
    <>
      <div className="row between">
        <h1>{name ?? 'Proje'}</h1>
        <span className="muted">Proje #{id}</span>
      </div>
      <nav className="subnav">
        <NavLink to={`/projects/${id}`} end className={cls}>Çizimler ve Parametreler</NavLink>
        <NavLink to={`/projects/${id}/quantities`} className={cls}>Metraj</NavLink>
        <NavLink to={`/projects/${id}/prices`} className={cls}>Birim Fiyatlar</NavLink>
        <NavLink to={`/projects/${id}/cost`} className={cls}>Maliyet</NavLink>
      </nav>
    </>
  )
}
