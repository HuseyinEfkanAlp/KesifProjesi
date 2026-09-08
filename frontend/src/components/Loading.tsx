/** Sayfa yüklenirken düzenin şeklini koruyan iskelet; hata varsa hata metni. */
export default function Loading({ error, rows = 4 }: { error?: string; rows?: number }) {
  if (error) return <div className="error" role="alert">{error}</div>
  return (
    <div className="skeleton-page" role="status" aria-live="polite" aria-label="Yükleniyor">
      <div className="skeleton title" />
      <div className="skeleton nav" />
      <div className="panel">
        {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton line" style={{ width: `${88 - (i % 3) * 14}%` }} />)}
      </div>
    </div>
  )
}
