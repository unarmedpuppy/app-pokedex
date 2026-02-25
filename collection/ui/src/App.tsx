import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchPokemon, fetchPokemonDetail, fetchStats } from './api'
import type { PokemonDetail, PokemonSummary, Stats } from './types'

const LIMIT = 60

// ─── Helpers ──────────────────────────────────────────────────────────────────

function genderSymbol(g: string | null) {
  if (g === 'male') return '♂'
  if (g === 'female') return '♀'
  return ''
}

function dexNum(n: number | null) {
  if (!n) return ''
  return `#${String(n).padStart(4, '0')}`
}

// ─── Card ─────────────────────────────────────────────────────────────────────

function PokemonCard({
  p,
  onClick,
}: {
  p: PokemonSummary
  onClick: () => void
}) {
  const displayName = p.nickname ? `"${p.nickname}"` : p.species_name
  const isShiny = Boolean(p.is_shiny)

  return (
    <button className={`card ${isShiny ? 'card--shiny' : ''}`} onClick={onClick}>
      {p.image_url ? (
        <div className="card-img-wrap">
          <img src={p.image_url} alt={p.species_name} className="card-img" />
        </div>
      ) : (
        <div className="card-img-wrap card-img-placeholder">?</div>
      )}
      <div className="card-body">
        <div className="card-name">
          {isShiny && <span className="shiny-star">★</span>}
          {displayName}
          {p.form_name && <span className="form-tag">{p.form_name}</span>}
        </div>
        {p.nickname && <div className="card-species">{p.species_name}</div>}
        <div className="card-meta">
          <span>{dexNum(p.dex_number)}</span>
          <span>Lv.{p.level ?? '?'}</span>
          <span className="gender">{genderSymbol(p.gender)}</span>
        </div>
        <div className="card-ot">OT: {p.original_trainer ?? '—'}</div>
      </div>
    </button>
  )
}

// ─── Detail panel ─────────────────────────────────────────────────────────────

function DetailPanel({
  id,
  onClose,
}: {
  id: number
  onClose: () => void
}) {
  const [detail, setDetail] = useState<PokemonDetail | null>(null)

  useEffect(() => {
    setDetail(null)
    fetchPokemonDetail(id).then(setDetail)
  }, [id])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  if (!detail) {
    return (
      <div className="detail-overlay" onClick={onClose}>
        <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
          <div className="detail-loading">Loading...</div>
        </div>
      </div>
    )
  }

  const isShiny = Boolean(detail.is_shiny)
  const moves = [detail.move1, detail.move2, detail.move3, detail.move4].filter(Boolean)

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose}>✕</button>

        <div className="detail-inner">
          {/* Screenshot */}
          <div className="detail-screenshot-wrap">
            {detail.image_url && (
              <img src={detail.image_url} alt={detail.species_name} className="detail-screenshot" />
            )}
          </div>

          {/* Metadata */}
          <div className="detail-meta">
            <div className="detail-title">
              {isShiny && <span className="shiny-star">★</span>}
              {detail.nickname ? (
                <>
                  <span className="detail-nickname">"{detail.nickname}"</span>
                  <span className="detail-species">{detail.species_name}</span>
                </>
              ) : (
                <span className="detail-species">{detail.species_name}</span>
              )}
              {detail.form_name && (
                <span className="form-tag">{detail.form_name}</span>
              )}
            </div>

            <div className="detail-dex">
              {dexNum(detail.dex_number)} · Lv.{detail.level ?? '?'} · {genderSymbol(detail.gender) || '—'}
            </div>

            <table className="detail-table">
              <tbody>
                <Row label="Nature" val={detail.nature} />
                <Row label="Ability" val={detail.ability} />
                <Row label="Ball" val={detail.ball_type} />
                <Row label="Held Item" val={detail.held_item} />
                <Row label="Mark" val={detail.mark} />
                <Row label="Game" val={detail.game_of_origin} />
              </tbody>
            </table>

            {moves.length > 0 && (
              <div className="detail-section">
                <div className="detail-section-label">Moves</div>
                <div className="detail-moves">
                  {moves.map((m, i) => (
                    <span key={i} className="move-tag">{m}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="detail-section">
              <div className="detail-section-label">Trainer</div>
              <table className="detail-table">
                <tbody>
                  <Row label="OT" val={detail.original_trainer} />
                  <Row label="ID" val={detail.trainer_id} />
                </tbody>
              </table>
            </div>

            <div className="detail-location">
              Box {detail.box_number} · Slot {detail.box_slot}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, val }: { label: string; val: string | null | undefined }) {
  if (!val) return null
  return (
    <tr>
      <td className="row-label">{label}</td>
      <td className="row-val">{val}</td>
    </tr>
  )
}

// ─── Filter bar ───────────────────────────────────────────────────────────────

interface Filters {
  q: string
  shiny: boolean | undefined
  ot: string
}

function FilterBar({
  filters,
  onChange,
  stats,
}: {
  filters: Filters
  onChange: (f: Filters) => void
  stats: Stats | null
}) {
  return (
    <div className="filters">
      <input
        className="filter-search"
        type="search"
        placeholder="Search species, nickname, OT..."
        value={filters.q}
        onChange={(e) => onChange({ ...filters, q: e.target.value })}
      />
      <button
        className={`filter-btn ${filters.shiny === true ? 'filter-btn--active' : ''}`}
        onClick={() =>
          onChange({ ...filters, shiny: filters.shiny === true ? undefined : true })
        }
      >
        ★ Shiny only {stats ? `(${stats.shiny})` : ''}
      </button>
      <button
        className={`filter-btn ${filters.shiny === false ? 'filter-btn--active' : ''}`}
        onClick={() =>
          onChange({ ...filters, shiny: filters.shiny === false ? undefined : false })
        }
      >
        Non-shiny
      </button>
    </div>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [filters, setFilters] = useState<Filters>({ q: '', shiny: undefined, ot: '' })
  const [items, setItems] = useState<PokemonSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)

  // Debounce search
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(
    async (f: Filters, off: number, replace: boolean) => {
      setLoading(true)
      try {
        const res = await fetchPokemon({
          q: f.q || undefined,
          shiny: f.shiny,
          ot: f.ot || undefined,
          limit: LIMIT,
          offset: off,
        })
        setTotal(res.total)
        setItems((prev) => (replace ? res.items : [...prev, ...res.items]))
        setOffset(off + res.items.length)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  // Initial load + stats
  useEffect(() => {
    load(filters, 0, true)
    fetchStats().then(setStats)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // React to filter changes with debounce on search text
  const handleFilterChange = (f: Filters) => {
    setFilters(f)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setOffset(0)
      load(f, 0, true)
    }, 300)
  }

  const handleClose = useCallback(() => setSelectedId(null), [])

  const hasMore = items.length < total

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">
          <span className="header-icon">⬡</span>
          Pokemon HOME Collection
        </div>
        {stats && (
          <div className="header-stats">
            <span>{stats.total.toLocaleString()} Pokemon</span>
            <span className="stat-dot">·</span>
            <span>★ {stats.shiny} shiny</span>
          </div>
        )}
      </header>

      <div className="layout">
        <aside className="sidebar">
          <FilterBar filters={filters} onChange={handleFilterChange} stats={stats} />

          {stats && stats.top_trainers.length > 0 && (
            <div className="sidebar-section">
              <div className="sidebar-section-label">Top Trainers</div>
              {stats.top_trainers.map((t) => (
                <button
                  key={t.original_trainer}
                  className={`ot-btn ${filters.ot === t.original_trainer ? 'ot-btn--active' : ''}`}
                  onClick={() =>
                    handleFilterChange({
                      ...filters,
                      ot: filters.ot === t.original_trainer ? '' : t.original_trainer,
                    })
                  }
                >
                  <span className="ot-name">{t.original_trainer}</span>
                  <span className="ot-count">{t.n}</span>
                </button>
              ))}
            </div>
          )}
        </aside>

        <main className="main">
          <div className="results-bar">
            {loading && <span className="loading-dot" />}
            <span>{total.toLocaleString()} results</span>
          </div>

          <div className="grid">
            {items.map((p) => (
              <PokemonCard key={p.id} p={p} onClick={() => setSelectedId(p.id)} />
            ))}
          </div>

          {hasMore && (
            <button
              className="load-more"
              disabled={loading}
              onClick={() => load(filters, offset, false)}
            >
              {loading ? 'Loading...' : `Load more (${total - items.length} remaining)`}
            </button>
          )}
        </main>
      </div>

      {selectedId !== null && (
        <DetailPanel id={selectedId} onClose={handleClose} />
      )}
    </div>
  )
}
