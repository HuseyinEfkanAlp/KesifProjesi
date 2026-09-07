import { useEffect, useState } from 'react'
import { Api } from '../api/client'
import type { PlanType } from '../types'

let cache: PlanType[] | null = null
let inflight: Promise<PlanType[]> | null = null

/** Plan seti kataloğu (planset.py); bir kez yüklenir, sayfalar arasında paylaşılır. */
export function usePlanTypes(): PlanType[] {
  const [types, setTypes] = useState<PlanType[]>(cache ?? [])
  useEffect(() => {
    if (cache) { setTypes(cache); return }
    inflight ??= Api.projects.planTypes().then((r) => { cache = r.types; return r.types })
    inflight.then(setTypes).catch(() => { /* katalog yoksa seçim listesi boş kalır */ })
  }, [])
  return types
}

/** Plan tipi seçim listesi: grup başlıklarıyla (optgroup) */
export function planTypeGroups(types: PlanType[]): { code: string; label: string; types: PlanType[] }[] {
  const out: { code: string; label: string; types: PlanType[] }[] = []
  for (const t of types) {
    let g = out.find((x) => x.code === t.group)
    if (!g) { g = { code: t.group, label: t.group_label, types: [] }; out.push(g) }
    g.types.push(t)
  }
  return out
}
