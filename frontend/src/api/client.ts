import type { Boq, Catalog, CatalogItem, CostResult, Discipline, DisciplineChoice, Drawing, Element, LayerCheck, PlanCheck, PlanLevel, PlanType, PriceIn, PriceItem, Project, ProjectSystems, QuantitiesResponse, QuantitySummary, UploadResult } from '../types'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
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
}

export interface UploadOptions {
  label?: string
  storeyCount?: number
  unitOverride?: string
  /** 'auto' (varsayılan): plan tipi dosya adı / başlıktan tanınır, disiplin ondan gelir */
  discipline?: DisciplineChoice
  planType?: string
}

export const Api = {
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
    planTypes: () => request<{ groups: Record<string, string>; types: PlanType[]; levels: PlanLevel[] }>('/api/projects/meta/plan-types'),
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
    elements: (id: number) => request<Element[]>(`/api/drawings/${id}/elements`),
    boq: (id: number) => request<Boq>(`/api/drawings/${id}/boq`),
    addElement: (id: number, body: Partial<Element>) => request<Element>(`/api/drawings/${id}/elements`, { method: 'POST', body: json(body) }),
    previewSvg: (id: number) => fetch(`/api/drawings/${id}/preview.svg?width=1400`).then((r) => r.text()),
  },
  elements: {
    patch: (id: number, body: Partial<Element>) => request<Element>(`/api/elements/${id}`, { method: 'PATCH', body: json(body) }),
    remove: (id: number) => request<void>(`/api/elements/${id}`, { method: 'DELETE' }),
  },
  quantities: (pid: number) => request<QuantitiesResponse>(`/api/projects/${pid}/quantities`),
  prices: {
    list: (pid: number) => request<PriceItem[]>(`/api/projects/${pid}/prices`),
    save: (pid: number, items: PriceIn[]) =>
      request<PriceItem[]>(`/api/projects/${pid}/prices`, { method: 'PUT', body: json(items) }),
  },
  cost: {
    get: (pid: number) => request<{ summary: QuantitySummary; boq: Boq; cost: CostResult }>(`/api/projects/${pid}/cost`),
    excelUrl: (pid: number) => `/api/projects/${pid}/cost.xlsx`,
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
