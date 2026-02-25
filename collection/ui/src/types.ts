export interface PokemonSummary {
  id: number
  box_number: number
  box_slot: number
  species_name: string
  dex_number: number | null
  form_name: string | null
  nickname: string | null
  level: number | null
  nature: string | null
  is_shiny: number // SQLite stores as 0/1
  gender: string | null
  original_trainer: string | null
  trainer_id: string | null
  ball_type: string | null
  image_url: string | null
}

export interface PokemonDetail extends PokemonSummary {
  ability: string | null
  held_item: string | null
  mark: string | null
  move1: string | null
  move2: string | null
  move3: string | null
  move4: string | null
  game_of_origin: string | null
  parsed_at: string | null
}

export interface ListResponse {
  total: number
  items: PokemonSummary[]
}

export interface Stats {
  total: number
  shiny: number
  top_trainers: { original_trainer: string; n: number }[]
}
