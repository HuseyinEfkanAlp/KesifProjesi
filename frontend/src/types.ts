export type EType = 'column' | 'shear_wall' | 'beam' | 'slab' | 'foundation'

export const ETYPE_LABELS: Record<EType, string> = {
  column: 'Kolon',
  shear_wall: 'Perde',
  beam: 'Kiriş',
  slab: 'Döşeme',
  foundation: 'Temel',
}

/** Katman eşlemede seçilebilen tipler: elemanlar + yardımcı tipler (döşeme boşluğu) */
export const LAYER_TYPE_LABELS: Record<string, string> = { ...ETYPE_LABELS, hole: 'Döşeme boşluğu (şaft)' }

export interface Project {
  id: number
  name: string
  description: string
  storey_height: number
  slab_thickness: number
  vat_rate: number
  rebar_ratios: Record<string, number>
  drawing_count: number
  created_at: string
}

export interface LayerInfo {
  name: string
  count: number
  etype: EType | null
  etype_label: string | null
}

export interface Drawing {
  id: number
  project_id: number
  filename: string
  label: string
  storey_count: number
  storey_height: number | null
  unit: string
  unit_override: string | null
  unit_detected: boolean
  layers: LayerInfo[]
  warnings: string[]
  element_count: number
}

/** Çok paftalı dosyada tespit edilen bir pafta (çerçeve ya da nesne kümesi) */
export interface SheetInfo {
  index: number
  title: string
  bbox: number[]
  entity_count: number
  text_count: number
  titled: boolean
  source: 'frame' | 'cluster'
  /** Paftadaki diğer başlık adayları (ana başlık yanlış yazılmışsa kalıp planını bunlardan tanırız) */
  titles: string[]
}

export interface SourceInfo {
  token: string
  filename: string
  size_mb: number
  entity_count: number
  can_use_whole: boolean
}

/** Yükleme yanıtı: dosya çok paftalıysa önce pafta seçilir */
export interface SheetSelection {
  needs_sheet_selection: true
  source: SourceInfo
  sheets: SheetInfo[]
}

export type UploadResult = Drawing | SheetSelection

export const isSheetSelection = (r: UploadResult): r is SheetSelection =>
  (r as SheetSelection).needs_sheet_selection === true

export interface Element {
  id: number
  drawing_id: number
  etype: EType
  subtype: string | null
  name: string | null
  layer: string
  b: number | null
  h: number | null
  thickness: number | null
  area: number
  length: number
  perimeter: number
  count: number
  confidence: number
  warnings: string[]
  label_raw: string | null
  source: string
  points: number[][]
  included: boolean
  manual: boolean
}

export interface QuantityGroup {
  key: string
  label: string
  etype: string
  element_count: number
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
}

export interface QuantitySummary {
  groups: QuantityGroup[]
  totals: { concrete_m3: number; formwork_m2: number; rebar_kg: number }
}

export interface QuantityLine {
  element_id: number
  etype: EType
  name: string | null
  subtype: string | null
  count: number
  multiplier: number
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
  total_concrete_m3: number
  total_formwork_m2: number
  total_rebar_kg: number
  notes: string[]
  drawing?: string
  drawing_id?: number
  layer?: string
  b?: number | null
  h?: number | null
  thickness?: number | null
  area?: number
  length?: number
  warnings: string[]
}

export interface PriceItem {
  id: number
  key: string
  name: string
  unit: string
  unit_price: number
}

export interface CostLine {
  key: string
  kind: string
  kind_label: string
  group: string
  group_label: string
  unit: string
  quantity: number
  unit_price: number
  price_source: string
  total: number
}

export interface CostResult {
  lines: CostLine[]
  subtotal: number
  vat_rate: number
  vat: number
  grand_total: number
  by_kind: Record<string, number>
  missing_prices: string[]
}
