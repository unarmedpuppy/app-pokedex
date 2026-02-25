import type { ListResponse, PokemonDetail, Stats } from './types'

export async function fetchPokemon(params: {
  q?: string
  shiny?: boolean
  ot?: string
  limit?: number
  offset?: number
}): Promise<ListResponse> {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.shiny !== undefined) search.set('shiny', String(params.shiny))
  if (params.ot) search.set('ot', params.ot)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  const res = await fetch(`/api/pokemon?${search}`)
  return res.json()
}

export async function fetchPokemonDetail(id: number): Promise<PokemonDetail> {
  const res = await fetch(`/api/pokemon/${id}`)
  return res.json()
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch('/api/stats')
  return res.json()
}
