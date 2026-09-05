import type { Boq, CostResult, Discipline, Drawing, Element, PriceIn, PriceItem, Project, QuantitiesResponse, QuantitySummary, UploadResult } from '../types'

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
  discipline?: Discipline
}

export interface DrawingPatch {
  label?: string
  storey_count?: number
  storey_height?: number | null
  unit_override?: string
  discipline?: Discipline
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
  },
  drawings: {
    list: (pid: number) => request<Drawing[]>(`/api/projects/${pid}/drawings`),
    get: (id: number) => request<Drawing>(`/api/drawings/${id}`),
    /** Tek paftalı dosya: doğrudan çizim döner. Çok paftalı / büyük dosya: pafta listesi döner (SheetSelection). */
    upload: (pid: number, file: File, label: string, storeyCount: number, unitOverride: string, discipline: Discipline) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('label', label)
      fd.append('storey_count', String(storeyCount))
      fd.append('discipline', discipline)
      if (unitOverride) fd.append('unit_override', unitOverride)
      return request<UploadResult>(`/api/projects/${pid}/drawings`, { method: 'POST', body: fd })
    },
    /** Kaynak dosyadan seçilen paftaları kırpıp ayrı çizimler olarak ekler */
    fromSource: (pid: number, token: string, sheets: SheetPick[], unitOverride: string, discipline: Discipline, whole = false) =>
      request<Drawing[]>(`/api/projects/${pid}/drawings/from-source`, {
        method: 'POST', body: json({ token, sheets, whole, unit_override: unitOverride || null, discipline }),
      }),
    patch: (id: number, body: DrawingPatch) =>
      request<Drawing>(`/api/drawings/${id}`, { method: 'PATCH', body: json(body) }),
    remove: (id: number) => request<void>(`/api/drawings/${id}`, { method: 'DELETE' }),
    reanalyze: (id: number) => request<Drawing>(`/api/drawings/${id}/reanalyze`, { method: 'POST' }),
    elements: (id: number) => request<Element[]>(`/api/drawings/${id}/elements`),
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
}

export const fmt = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? '-' : v.toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
export const cm = (v: number | null | undefined) => (v === null || v === undefined ? '-' : Math.round(v * 100).toString())
