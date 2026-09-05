export type Discipline = 'structural' | 'architectural' | 'electrical' | 'standard' | 'rebar' | 'mapped'

export const DISCIPLINES: Record<Discipline, string> = {
  structural: 'Statik (kalıp planı)',
  rebar: 'Donatı planı (demir metraj tablosu)',
  architectural: 'Mimari (sezgisel)',
  electrical: 'Elektrik (sezgisel)',
  standard: 'KSF standart çizim (tüm disiplinler)',
  mapped: 'Katman eşlemeli (cephe / çatı / peyzaj / diğer)',
}

export type EType =
  | 'column' | 'shear_wall' | 'beam' | 'slab' | 'foundation'
  | 'wall' | 'door' | 'window'
  | 'tray' | 'cable' | 'conduit' | 'fixture'

export const ETYPE_LABELS: Record<EType, string> = {
  column: 'Kolon',
  shear_wall: 'Perde',
  beam: 'Kiriş',
  slab: 'Döşeme',
  foundation: 'Temel',
  wall: 'Duvar',
  door: 'Kapı',
  window: 'Pencere',
  tray: 'Kablo tavası',
  cable: 'Kablo',
  conduit: 'Boru',
  fixture: 'Armatür / priz / anahtar',
}

export const ETYPES_BY_DISCIPLINE: Record<Discipline, EType[]> = {
  structural: ['column', 'shear_wall', 'beam', 'slab', 'foundation'],
  architectural: ['wall', 'door', 'window'],
  electrical: ['tray', 'cable', 'conduit', 'fixture'],
  standard: [],   // KSF çiziminde tipler katman adından gelir (katalog kalem kodu)
  rebar: [],      // donatı paftası: yalnız metraj tablosu okunur
  mapped: [],     // katman -> katalog kalemi eşlemesi
}

/** Statik tipler (beton/kalıp/demir metrajı) */
export const STRUCTURAL_ETYPES = ETYPES_BY_DISCIPLINE.structural

/** Katman eşlemede seçilebilen tipler: disiplinin elemanları (+ statikte döşeme boşluğu) */
export function layerTypeLabels(discipline: Discipline): Record<string, string> {
  const out: Record<string, string> = {}
  if (discipline === 'standard' || discipline === 'rebar' || discipline === 'mapped') return out
  for (const t of ETYPES_BY_DISCIPLINE[discipline]) out[t] = ETYPE_LABELS[t]
  if (discipline === 'structural') out.hole = 'Döşeme boşluğu (şaft)'
  return out
}

export const ETYPE_COLORS: Record<EType, string> = {
  column: '#d62728', shear_wall: '#9467bd', beam: '#1f77b4', slab: '#2ca02c', foundation: '#ff7f0e',
  wall: '#8c564b', door: '#e377c2', window: '#17becf',
  tray: '#bcbd22', cable: '#ff9896', conduit: '#c5b0d5', fixture: '#7f7f7f',
}

/** Alt tip açıklaması (statik: temel tipi; mimari: malzeme; elektrik: boyut/kesit/kategori) */
export const SUBTYPE_LABELS: Record<string, string> = {
  raft: 'radye', strip: 'sürekli', net: 'net alan',
  ytong: 'Ytong / gazbeton', tugla: 'Tuğla', bims: 'Bims', alcipan: 'Alçıpan', beton: 'Betonarme', tas: 'Taş',
  armatur: 'Aydınlatma armatürü', acil: 'Acil aydınlatma', priz: 'Priz', anahtar: 'Anahtar', buat: 'Buat', pano: 'Pano',
  data: 'Data / telefon', yangin: 'Yangın algılama', diger: 'Diğer',
}

export interface ProjectParams {
  wall_height: number | null
  plaster_sides: number
  paint_sides: number
  cable_drop: number
  cable_waste_pct: number
  tray_waste_pct: number
  work_hours_per_day: number
  concrete_waste_pct: number
  rebar_waste_pct: number
  tie_wire_kg_per_t: number
  plywood_sheet_m2: number
  formwork_reuse: number
  formwork_oil_l_per_m2: number
  nails_kg_per_m2: number
}

export interface Project {
  id: number
  name: string
  description: string
  storey_height: number
  slab_thickness: number
  vat_rate: number
  rebar_ratios: Record<string, number>
  params: ProjectParams
  drawing_count: number
  created_at: string
}

export interface LayerInfo {
  name: string
  count: number
  etype: string | null
  etype_label: string | null
  suggested?: string | null
  mapped_code?: string | null
  mapped_measure?: string | null
}

export interface Drawing {
  id: number
  project_id: number
  filename: string
  label: string
  discipline: Discipline
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
  meta?: Record<string, unknown>
}

export interface QuantityGroup {
  key: string
  label: string
  etype: string
  element_count: number
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
  rebar_source: 'oran' | 'tablo'
}

export interface RebarDia {
  dia_mm: number
  weight_kg: number
  length_m: number
  targets: Record<string, number>
}

export interface DrawingSummary {
  drawing: string
  drawing_id: number | null
  kot: string | null
  groups: Record<string, { concrete_m3: number; formwork_m2: number; rebar_kg: number; count: number }>
  concrete_m3: number
  formwork_m2: number
  rebar_kg: number
  rebar_by_dia: Record<string, number>
  rebar_table_kg?: number
  rebar_target?: string
}

export interface QuantitySummary {
  groups: QuantityGroup[]
  totals: { concrete_m3: number; formwork_m2: number; rebar_kg: number }
  rebar_by_dia: RebarDia[]
  rebar_table_total_kg: number
  rebar_ratio_total_kg: number
  by_drawing: DrawingSummary[]
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

/** Keşif kalemi (tüm disiplinler) */
export interface BoqItem {
  key: string
  kind: string
  kind_label: string
  group: string
  label: string
  unit: string
  quantity: number
  count: number
  discipline: string
  discipline_label: string
  notes: string[]
  detail: Record<string, unknown>
}

export interface Boq {
  items: BoqItem[]
  by_discipline: { discipline: string; label: string; items: BoqItem[] }[]
  kinds: Record<string, { label: string; unit: string; discipline: string }>
}

export interface QuantitiesResponse {
  summary: QuantitySummary
  lines: QuantityLine[]
  boq: Boq
  params: { storey_height: number; slab_thickness: number } & ProjectParams
}

export interface PriceItem {
  id: number
  key: string
  name: string
  unit: string
  unit_price: number
  labor_price: number
  brand: string
  hours_per_unit: number
  crew_size: number
  kind: string
  kind_label: string
  discipline: string
  discipline_label: string
  is_general: boolean
}

/** KÇS kataloğu */
export interface CatalogItem {
  code: string
  discipline: string
  name: string
  measure: 'count' | 'length' | 'area' | 'wall_area' | 'volume'
  measure_label: string
  unit: string
  spec_label: string
  example: string
  custom: boolean
}

export interface Catalog {
  disciplines: Record<string, string>
  items: CatalogItem[]
  measures: Record<string, { label: string; unit: string }>
  by_discipline: { code: string; name: string; items: CatalogItem[] }[]
}

export interface LayerCheck {
  valid: boolean
  reason?: string
  discipline?: string
  discipline_name?: string
  code?: string
  spec?: string | null
  known?: boolean
  item?: CatalogItem | null
  measure?: string
}

export interface PriceIn {
  key: string
  unit_price?: number
  labor_price?: number
  brand?: string
  hours_per_unit?: number
  crew_size?: number
}

export interface CostLine {
  key: string
  kind: string
  kind_label: string
  group: string
  group_label: string
  discipline: string
  discipline_label: string
  unit: string
  quantity: number
  brand: string
  unit_price: number
  labor_price: number
  material_total: number
  labor_total: number
  total: number
  price_source: string
  labor_source: string
  hours_per_unit: number
  crew_size: number
  hours: number
  days: number
}

export interface CostResult {
  lines: CostLine[]
  material_subtotal: number
  labor_subtotal: number
  subtotal: number
  vat_rate: number
  vat: number
  grand_total: number
  by_kind: Record<string, number>
  by_discipline: { discipline: string; label: string; material: number; labor: number; total: number; hours: number; days: number }[]
  missing_prices: string[]
  missing_labor: string[]
  duration: { hours_per_day: number; total_hours: number; sequential_days: number; parallel_days: number; missing_rates: string[] }
}
