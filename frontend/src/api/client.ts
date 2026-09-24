import type { QualityReport, Boq, Catalog, CatalogItem, CostResult, Discipline, DisciplineChoice, Drawing, Element, JobRow, LayerCheck, MaterialIn, MaterialOptions, MaterialPrice, PlanCheck, PlanLevel, PlanType, PozBook, PozImportResult, PriceBook, PriceBookIn, PriceIn, PriceItem, Project, ProjectSystems, Supplier, SupplierIn, QuantitiesResponse, QuantitySummary, UploadResult, SpaceBreakdown } from '../types'

/** Sunucu 401 döndüğünde yayılan olay; AuthGate dinler ve giriş ekranını gösterir. */
export const SESSION_LOST = 'kesif:oturum-dustu'

export type Role = 'sahibi' | 'uzman' | 'goruntuleyen'

export interface Me {
  user: { id: number; email: string; name: string; role: Role; role_label: string }
  company: { slug: string; name: string }
}

export interface AuthStatus {
  needs_setup: boolean
  me: Me | null
  roles: Record<Role, string>
}

export interface UserRow {
  id: number
  email: string
  name: string
  role: Role
  active: boolean
  created_at: string | null
  last_login: string | null
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    // Oturum düştü (süresi doldu, hesap kapatıldı, şifre değişti): giriş ekranına dönülür.
    window.dispatchEvent(new Event(SESSION_LOST))
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch { /* boş */ }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const json = (body: unknown) => JSON.stringify(body)

export interface SheetPick {
  index: number
  label?: string
  storey_count?: number
  storey_height?: number | null
  discipline?: DisciplineChoice
  plan_type?: string
}

export interface DrawingPatch {
  /** Ek sezgisel disiplinler (aynı paftada mimari + elektrik) */
  disciplines?: Discipline[]
  label?: string
  storey_count?: number
  storey_height?: number | null
  unit_override?: string
  discipline?: Discipline
  plan_type?: string
  /** Yapı bloğu ('' = ortak / tüm bina) */
  block?: string
}

export interface UploadOptions {
  label?: string
  storeyCount?: number
  unitOverride?: string
  /** 'auto' (varsayılan): plan tipi dosya adı / başlıktan tanınır, disiplin ondan gelir */
  discipline?: DisciplineChoice
  planType?: string
}

export interface ReviewIn {
  item_key: string
  status?: 'onaylandi' | 'kontrol' | 'reddedildi'
  /** null = hesaplanan değer kullanılsın */
  quantity?: number | null
  /** değiştirildiği andaki hesaplanan değer — raporda "hesaplanan X · elle Y" için saklanır */
  computed?: number | null
  reason?: string
  author?: string
}

export interface ReviewRow extends ReviewIn {
  status: 'onaylandi' | 'kontrol' | 'reddedildi'
  updated_at: string
}

export const Api = {
  auth: {
    status: () => request<AuthStatus>('/api/auth/status'),
    login: (email: string, password: string) => request<Me>('/api/auth/login', { method: 'POST', body: json({ email, password }) }),
    setup: (body: { email: string; password: string; name: string; company_name: string }) =>
      request<Me>('/api/auth/setup', { method: 'POST', body: json(body) }),
    logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
    changePassword: (current: string, next: string) =>
      request<void>('/api/auth/password', { method: 'POST', body: json({ current, new: next }) }),
  },
  users: {
    list: () => request<UserRow[]>('/api/users'),
    add: (body: { email: string; password: string; name: string; role: Role }) =>
      request<UserRow>('/api/users', { method: 'POST', body: json(body) }),
    patch: (id: number, body: { name?: string; role?: Role; active?: boolean }) =>
      request<UserRow>(`/api/users/${id}`, { method: 'PATCH', body: json(body) }),
    resetPassword: (id: number, password: string) =>
      request<void>(`/api/users/${id}/password`, { method: 'POST', body: json({ password }) }),
  },
  projects: {
    list: () => request<Project[]>('/api/projects'),
    get: (id: number) => request<Project>(`/api/projects/${id}`),
    create: (body: Partial<Project>) => request<Project>('/api/projects', { method: 'POST', body: json(body) }),
    patch: (id: number, body: Partial<Project>) => request<Project>(`/api/projects/${id}`, { method: 'PATCH', body: json(body) }),
    remove: (id: number) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
    mapLayer: (id: number, layer: string, etype: string | null) =>
      request<{ profile: Record<string, string[]> }>(`/api/projects/${id}/layer-profile/map`, { method: 'POST', body: json({ layer, etype }) }),
    planCheck: (id: number) => request<PlanCheck>(`/api/projects/${id}/plan-check`),
    setPlanLevels: (id: number, levels: Record<string, PlanLevel>) =>
      request<PlanCheck>(`/api/projects/${id}/plan-set`, { method: 'PUT', body: json(levels) }),
    /** Projedeki yapı blokları (["C1","C2"]); hiç çizimi yüklenmemiş blok ancak buradan bilinir */
    setBlocks: (id: number, blocks: string[]) =>
      request<PlanCheck>(`/api/projects/${id}/blocks`, { method: 'PUT', body: json(blocks) }),
    planTypes: () => request<{ groups: Record<string, string>; types: PlanType[]; levels: PlanLevel[] }>('/api/projects/meta/plan-types'),
    /** mahal bazında keşif: mimari plandan çıkan mahaller + her mahalin kalemleri */
    spaces: (id: number) => request<SpaceBreakdown>(`/api/projects/${id}/spaces`),
    systems: (id: number) => request<ProjectSystems>(`/api/projects/${id}/systems`),
    /** {sistem: {bileşen: {include?, spec?}}}; boş nesne kararı siler (kanıta döner) */
    setSystems: (id: number, body: Record<string, Record<string, { include?: boolean | null; spec?: string | null }>>) =>
      request<ProjectSystems>(`/api/projects/${id}/systems`, { method: 'PUT', body: json(body) }),
  },
  drawings: {
    list: (pid: number) => request<Drawing[]>(`/api/projects/${pid}/drawings`),
    get: (id: number) => request<Drawing>(`/api/drawings/${id}`),
    /** Tek paftalı dosya: doğrudan çizim döner. Çok paftalı / büyük dosya: pafta listesi döner (SheetSelection). */
    upload: (pid: number, file: File, opts: UploadOptions = {}) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('label', opts.label ?? '')
      fd.append('storey_count', String(opts.storeyCount ?? 1))
      fd.append('discipline', opts.discipline ?? 'auto')
      if (opts.planType) fd.append('plan_type', opts.planType)
      if (opts.unitOverride) fd.append('unit_override', opts.unitOverride)
      return request<UploadResult>(`/api/projects/${pid}/drawings`, { method: 'POST', body: fd })
    },
    /** Kaynak dosyadan seçilen paftaları kırpıp ayrı çizimler olarak ekler (disiplin 'auto': her pafta kendi plan tipinden) */
    fromSource: (pid: number, token: string, sheets: SheetPick[], unitOverride: string, discipline: DisciplineChoice = 'auto', whole = false) =>
      request<Drawing[]>(`/api/projects/${pid}/drawings/from-source`, {
        method: 'POST', body: json({ token, sheets, whole, unit_override: unitOverride || null, discipline }),
      }),
    patch: (id: number, body: DrawingPatch) =>
      request<Drawing>(`/api/drawings/${id}`, { method: 'PATCH', body: json(body) }),
    remove: (id: number) => request<void>(`/api/drawings/${id}`, { method: 'DELETE' }),
    reanalyze: (id: number) => request<Drawing>(`/api/drawings/${id}/reanalyze`, { method: 'POST' }),
    makeCurrent: (id: number) => request<Drawing>(`/api/drawings/${id}/make-current`, { method: 'POST' }),
    elements: (id: number) => request<Element[]>(`/api/drawings/${id}/elements`),
    boq: (id: number) => request<Boq>(`/api/drawings/${id}/boq`),
    addElement: (id: number, body: Partial<Element>) => request<Element>(`/api/drawings/${id}/elements`, { method: 'POST', body: json(body) }),
    previewSvg: (id: number) => fetch(`/api/drawings/${id}/preview.svg?width=1400`).then((r) => r.text()),
  },
  elements: {
    patch: (id: number, body: Partial<Element>) => request<Element>(`/api/elements/${id}`, { method: 'PATCH', body: json(body) }),
    remove: (id: number) => request<void>(`/api/elements/${id}`, { method: 'DELETE' }),
  },
  jobs: {
    get: (id: number) => request<JobRow>(`/api/jobs/${id}`),
    list: (pid: number, active = false) =>
      request<JobRow[]>(`/api/projects/${pid}/jobs${active ? '?active=true' : ''}`),
    /** İş bitene kadar aralıklı sorar. Uzun analizde (dakikalar) tek uzun istek yerine kısa sorgular. */
    wait: async (id: number, onProgress?: (j: JobRow) => void, everyMs = 1500): Promise<JobRow> => {
      for (;;) {
        const j = await request<JobRow>(`/api/jobs/${id}`)
        onProgress?.(j)
        if (j.status === 'bitti' || j.status === 'hata') return j
        await new Promise((r) => setTimeout(r, everyMs))
      }
    },
  },
  quantities: (pid: number) => request<QuantitiesResponse>(`/api/projects/${pid}/quantities`),
  /** Metraj kontrolü: keşif satırını onaylama / reddetme / elle düzeltme */
  review: {
    save: (pid: number, body: ReviewIn) =>
      request<ReviewRow>(`/api/projects/${pid}/review`, { method: 'PUT', body: json(body) }),
    clear: (pid: number, itemKey: string) =>
      request<void>(`/api/projects/${pid}/review/${itemKey}`, { method: 'DELETE' }),
  },
  prices: {
    list: (pid: number) => request<PriceItem[]>(`/api/projects/${pid}/prices`),
    save: (pid: number, items: PriceIn[]) =>
      request<PriceItem[]>(`/api/projects/${pid}/prices`, { method: 'PUT', body: json(items) }),
  },
  materials: {
    list: (pid: number) => request<MaterialPrice[]>(`/api/projects/${pid}/materials`),
    save: (pid: number, items: MaterialIn[]) =>
      request<MaterialPrice[]>(`/api/projects/${pid}/materials`, { method: 'PUT', body: json(items) }),
    options: (pid: number) => request<MaterialOptions>(`/api/projects/${pid}/material-options`),
  },
  pricebook: {
    get: (scope: 'material' | 'labor' = 'material') => request<PriceBook>(`/api/pricebook?scope=${scope}`),
    save: (rows: PriceBookIn[]) => request<PriceBook>('/api/pricebook', { method: 'PUT', body: json(rows) }),
    remove: (rowId: number) => request<void>(`/api/pricebook/${rowId}`, { method: 'DELETE' }),
    /** İçeri alınmış ÇŞB / firma birim fiyat listesi (poz bedelleri) */
    pozList: () => request<PozBook>('/api/pricebook/poz'),
    pozImport: (text: string, supplier_id?: number | null, note = '') =>
      request<PozImportResult>('/api/pricebook/poz-import', { method: 'POST', body: json({ text, supplier_id: supplier_id ?? null, note }) }),
    pozClear: () => request<void>('/api/pricebook/poz', { method: 'DELETE' }),
    /** bankadaki güncel fiyatları bir projeye uygula */
    applyTo: (pid: number, overwrite = false) =>
      request<{ materials: number; labor: number }>(`/api/projects/${pid}/apply-pricebook?overwrite=${overwrite}`, { method: 'POST' }),
  },
  suppliers: {
    list: () => request<Supplier[]>('/api/suppliers'),
    create: (body: SupplierIn) => request<Supplier>('/api/suppliers', { method: 'POST', body: json(body) }),
    update: (id: number, body: SupplierIn) => request<Supplier>(`/api/suppliers/${id}`, { method: 'PATCH', body: json(body) }),
    remove: (id: number) => request<void>(`/api/suppliers/${id}`, { method: 'DELETE' }),
  },
  cost: {
    get: (pid: number) => request<{ summary: QuantitySummary; boq: Boq; cost: CostResult; quality: QualityReport }>(`/api/projects/${pid}/cost`),
    excelUrl: (pid: number) => `/api/projects/${pid}/cost.xlsx`,
    /** mahal bazında metraj tablosu (mahal listesi + mahal × kalem) */
    spacesExcelUrl: (pid: number) => `/api/projects/${pid}/spaces.xlsx`,
  },
  catalog: {
    get: () => request<Catalog>('/api/catalog'),
    upsertItem: (body: Partial<Omit<CatalogItem, 'components'>> & { components?: string | CatalogItem['components'] }) =>
      request<CatalogItem>('/api/catalog/items', { method: 'PUT', body: json(body) }),
    removeItem: (code: string) => request<void>(`/api/catalog/items/${encodeURIComponent(code)}`, { method: 'DELETE' }),
    upsertDiscipline: (code: string, name: string) => request<{ disciplines: Record<string, string> }>('/api/catalog/disciplines', { method: 'PUT', body: json({ code, name }) }),
    reset: () => request<Catalog>('/api/catalog/reset', { method: 'POST' }),
    checkLayer: (name: string) => request<LayerCheck>(`/api/catalog/check-layer?name=${encodeURIComponent(name)}`),
    templateUrl: '/api/catalog/template.dxf',
  },
}

export const fmt = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? '-' : v.toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
export const cm = (v: number | null | undefined) => (v === null || v === undefined ? '-' : Math.round(v * 100).toString())
