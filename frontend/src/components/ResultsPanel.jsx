import React, { useEffect, useMemo, useState } from 'react'

const palette = {
  govBlue: '#004E92',
  green: '#2E7D32',
  yellow: '#F9A825',
  red: '#C62828',
  border: '#E5E7EB',
}

function StatusIcon({ category }) {
  if (category === 'safe') {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M9 16.17l-3.5-3.5a1 1 0 10-1.41 1.41l4.2 4.2a1 1 0 001.41 0l9-9a1 1 0 10-1.41-1.41L9 16.17z" />
      </svg>
    )
  }
  if (category === 'caution') {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
      </svg>
    )
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 14h-2v-2h2v2zm0-4h-2V6h2v6z" />
    </svg>
  )
}

function categoryStyle(category) {
  if (category === 'safe') return { bg: '#E8F5E9', fg: palette.green, label: 'SAFE' }
  if (category === 'caution') return { bg: '#FFF8E1', fg: palette.yellow, label: 'CAUTION' }
  if (category === 'unsafe') return { bg: '#FFEBEE', fg: palette.red, label: 'UNSAFE' }
  return { bg: '#F3F4F6', fg: palette.govBlue, label: 'UNKNOWN' }
}

function Gauge({ value }) {
  const max = 200
  const v = Math.max(0, Math.min(value ?? 0, max))
  const pct = v / max
  const r = 48
  const c = 2 * Math.PI * r
  const dash = c * pct
  let stroke = palette.green
  if (value >= 150) stroke = palette.red
  else if (value >= 100) stroke = palette.yellow
  return (
    <svg width="140" height="90" viewBox="0 0 120 80" aria-label="HPI gauge">
      <path d="M10,70 A50,50 0 0,1 110,70" fill="none" stroke="#E5E7EB" strokeWidth="12" />
      <g transform="translate(60,70)">
        <circle cx="0" cy="0" r={r} fill="none" stroke="transparent" strokeWidth="0" />
        <g transform="rotate(-180)">
          <circle cx="0" cy="0" r={r} fill="none" stroke={stroke} strokeWidth="12" strokeDasharray={`${dash} ${c}`} strokeDashoffset={0} />
        </g>
      </g>
      <text x="60" y="45" textAnchor="middle" fontSize="12" fill={palette.govBlue}>HPI</text>
      <text x="60" y="60" textAnchor="middle" fontSize="14" fontWeight="600" fill={palette.govBlue}>{value?.toFixed ? value.toFixed(2) : value}</text>
    </svg>
  )
}

export default function ResultsPanel({ data }) {
  if (!data) return null
  const category = data?.indices?.category || 'unknown'
  const { bg, fg, label } = categoryStyle(category)
  const hpi = data?.indices?.hpi
  const hei = data?.indices?.hei
  const pli = data?.indices?.pli
  const assessments = data?.assessments || {}
  const extractedMetals = data?.extracted_metals || {}
  const thresholds = data?.indices?.thresholds || {}
  const severeOverride = !!data?.indices?.severe_exceed

  const exceeded = Object.entries(assessments).filter(([, a]) => (a?.exceeds === 1 || a?.exceeds === '1'))
  const exceededList = exceeded.map(([m]) => m).join(', ')
  const exceededCount = exceeded.length

  const API_BASE = import.meta?.env?.VITE_API_URL || 'http://localhost:8000'
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState('')
  const [statsLoading, setStatsLoading] = useState(false)
  const [corrMethod, setCorrMethod] = useState('pearson')
  const [corr, setCorr] = useState(null)
  const [corrError, setCorrError] = useState('')
  const [corrLoading, setCorrLoading] = useState(false)
  const [trends, setTrends] = useState(null)
  const [trendsError, setTrendsError] = useState('')
  const [trendsLoading, setTrendsLoading] = useState(false)
  const [trendMetal, setTrendMetal] = useState('')
  const [geo, setGeo] = useState(null)
  const [geoError, setGeoError] = useState('')
  const [geoLoading, setGeoLoading] = useState(false)
  const [geoMetal, setGeoMetal] = useState('')
  const [geoGrid, setGeoGrid] = useState(0)
  const [pca, setPca] = useState(null)
  const [pcaError, setPcaError] = useState('')
  const [pcaLoading, setPcaLoading] = useState(false)
  const [cluster, setCluster] = useState(null)
  const [clusterError, setClusterError] = useState('')
  const [clusterLoading, setClusterLoading] = useState(false)
  const [clusterK, setClusterK] = useState(3)

  useEffect(() => {
    if (!serverData || !serverData.extracted_metals) return
    
    let aborted = false
    async function fetchStats() {
      try {
        setStatsLoading(true)
        setStatsError('')
        const resp = await fetch(`${API_BASE}/api/stats/summary`)
        if (!resp.ok) throw new Error('Failed to load statistics')
        const json = await resp.json()
        if (!aborted) setStats(json)
      } catch (e) {
        if (!aborted) setStatsError(typeof e?.message === 'string' ? e.message : 'Failed to load statistics')
      } finally {
        if (!aborted) setStatsLoading(false)
      }
    }
    fetchStats()
    return () => { aborted = true }
  }, [API_BASE, serverData])

  const statEntries = useMemo(() => Object.entries(stats || {}), [stats])

  function Histogram({ counts, bins }) {
    if (!counts || !bins || counts.length === 0) return null
    const width = 220
    const height = 60
    const maxCount = Math.max(...counts, 1)
    const barW = width / counts.length
    return (
      <svg width={width} height={height} aria-label="Histogram">
        {counts.map((c, i) => {
          const h = (c / maxCount) * (height - 4)
          const x = i * barW
          const y = height - h
          return (
            <rect key={i} x={x} y={y} width={Math.max(barW - 2, 1)} height={h} fill="#93C5FD" />
          )
        })}
      </svg>
    )
  }

  function BoxPlot({ min, q1, median, q3, max }) {
    if ([min, q1, median, q3, max].some((v) => v === undefined || v === null)) return null
    const width = 220
    const height = 40
    const pad = 8
    const lo = Math.min(min, q1, median, q3, max)
    const hi = Math.max(min, q1, median, q3, max)
    const scale = (v) => pad + ((v - lo) / (hi - lo || 1)) * (width - 2 * pad)
    const xMin = scale(min)
    const xQ1 = scale(q1)
    const xMed = scale(median)
    const xQ3 = scale(q3)
    const xMax = scale(max)
    return (
      <svg width={width} height={height} aria-label="Box plot">
        <line x1={xMin} y1={height / 2} x2={xMax} y2={height / 2} stroke="#9CA3AF" />
        <rect x={xQ1} y={height / 2 - 10} width={Math.max(xQ3 - xQ1, 1)} height={20} fill="#BFDBFE" stroke="#60A5FA" />
        <line x1={xMed} y1={height / 2 - 12} x2={xMed} y2={height / 2 + 12} stroke="#1D4ED8" />
      </svg>
    )
  }

  useEffect(() => {
    if (!serverData || !serverData.extracted_metals) return
    
    let aborted = false
    async function fetchCorr() {
      try {
        setCorrLoading(true)
        setCorrError('')
        const resp = await fetch(`${API_BASE}/api/stats/correlation?method=${encodeURIComponent(corrMethod)}`)
        if (!resp.ok) throw new Error('Failed to load correlation')
        const json = await resp.json()
        if (!aborted) setCorr(json)
      } catch (e) {
        if (!aborted) setCorrError(typeof e?.message === 'string' ? e.message : 'Failed to load correlation')
      } finally {
        if (!aborted) setCorrLoading(false)
      }
    }
    fetchCorr()
    return () => { aborted = true }
  }, [API_BASE, corrMethod, serverData])

  function Heatmap({ variables, matrix }) {
    if (!variables || !matrix || variables.length === 0) return null
    const n = variables.length
    const cell = 20
    const padLeft = 110
    const padTop = 20
    const width = padLeft + n * cell
    const height = padTop + n * cell
    const colorFor = (r) => {
      const v = Math.max(-1, Math.min(1, r ?? 0))
      const t = (v + 1) / 2 // 0..1
      const rC = Math.round(255 * t)
      const bC = Math.round(255 * (1 - t))
      return `rgb(${rC},80,${bC})`
    }
    return (
      <svg width={width} height={height} aria-label="Correlation heatmap">
        {variables.map((v, i) => (
          <text key={`yl${i}`} x={padLeft - 6} y={padTop + i * cell + 14} textAnchor="end" fontSize="10" fill={palette.govBlue}>{v}</text>
        ))}
        {variables.map((v, j) => (
          <text key={`xl${j}`} x={padLeft + j * cell + 2} y={12} transform={`rotate(-45 ${padLeft + j * cell + 2},12)`} fontSize="10" fill={palette.govBlue}>{v}</text>
        ))}
        {matrix.map((row, i) => row.map((r, j) => (
          <rect key={`${i}-${j}`} x={padLeft + j * cell} y={padTop + i * cell} width={cell - 1} height={cell - 1} fill={colorFor(r)} />
        )))}
      </svg>
    )
  }

  // Trends fetch
  useEffect(() => {
    if (!serverData || !serverData.extracted_metals) return
    
    let aborted = false
    async function fetchTrends() {
      try {
        setTrendsLoading(true)
        setTrendsError('')
        const resp = await fetch(`${API_BASE}/api/stats/trends`)
        if (!resp.ok) throw new Error('Failed to load trends')
        const json = await resp.json()
        if (!aborted) {
          setTrends(json)
          const metals = Object.keys(json?.metals || {})
          if (metals.length > 0) setTrendMetal((prev) => prev || metals[0])
        }
      } catch (e) {
        if (!aborted) setTrendsError(typeof e?.message === 'string' ? e.message : 'Failed to load trends')
      } finally {
        if (!aborted) setTrendsLoading(false)
      }
    }
    fetchTrends()
    return () => { aborted = true }
  }, [API_BASE, serverData])

  // Geo fetch
  useEffect(() => {
    if (!serverData || !serverData.extracted_metals) return
    
    let aborted = false
    async function fetchGeo() {
      try {
        setGeoLoading(true)
        setGeoError('')
        const resp = await fetch(`${API_BASE}/api/stats/geo${geoGrid ? `?grid=${encodeURIComponent(geoGrid)}` : ''}`)
        if (!resp.ok) throw new Error('Failed to load geo data')
        const json = await resp.json()
        if (!aborted) {
          setGeo(json)
          // infer default geo metal from extracted metals or assessments
          const options = new Set([
            ...Object.keys(extractedMetals || {}),
            ...Object.keys(assessments || {}),
          ])
          const first = Array.from(options)[0]
          if (first) setGeoMetal((prev) => prev || first)
        }
      } catch (e) {
        if (!aborted) setGeoError(typeof e?.message === 'string' ? e.message : 'Failed to load geo data')
      } finally {
        if (!aborted) setGeoLoading(false)
      }
    }
    fetchGeo()
    return () => { aborted = true }
  }, [API_BASE, geoGrid, serverData])

  function LineChart({ dates, values }) {
    const width = 420
    const height = 120
    const pad = 28
    if (!dates || !values || dates.length === 0) return <div className="text-xs text-gray-600">No dated samples</div>
    const xs = dates.map((_, i) => i)
    const minX = 0
    const maxX = xs[xs.length - 1]
    const vs = values.map((v) => (v == null ? null : Number(v)))
    const defined = vs.filter((v) => v != null)
    const minY = Math.min(...defined)
    const maxY = Math.max(...defined)
    const sx = (x) => pad + ((x - minX) / (maxX - minX || 1)) * (width - 2 * pad)
    const sy = (y) => height - pad - ((y - minY) / (maxY - minY || 1)) * (height - 2 * pad)
    let d = ''
    vs.forEach((v, i) => {
      if (v == null) return
      const x = sx(xs[i])
      const y = sy(v)
      d += d ? ` L ${x} ${y}` : `M ${x} ${y}`
    })
    return (
      <svg width={width} height={height} aria-label="Trend line chart">
        <rect x={0} y={0} width={width} height={height} fill="#FFFFFF" />
        <path d={d} fill="none" stroke="#2563EB" strokeWidth={2} />
        <text x={pad} y={height - 6} fontSize="10" fill={palette.govBlue}>{dates[0]}</text>
        <text x={width - pad} y={height - 6} fontSize="10" textAnchor="end" fill={palette.govBlue}>{dates[dates.length - 1]}</text>
      </svg>
    )
  }

  // PCA fetch
  useEffect(() => {
    if (!serverData || !serverData.extracted_metals) return
    
    let aborted = false
    async function fetchPca() {
      try {
        setPcaLoading(true)
        setPcaError('')
        const resp = await fetch(`${API_BASE}/api/stats/pca?include_params=true&n_components=3`)
        if (!resp.ok) throw new Error('Failed to load PCA')
        const json = await resp.json()
        if (!aborted) setPca(json)
      } catch (e) {
        if (!aborted) setPcaError(typeof e?.message === 'string' ? e.message : 'Failed to load PCA')
      } finally {
        if (!aborted) setPcaLoading(false)
      }
    }
    fetchPca()
    return () => { aborted = true }
  }, [API_BASE, serverData])

  // Cluster fetch
  useEffect(() => {
    if (!serverData || !serverData.extracted_metals) return
    
    let aborted = false
    async function fetchCluster() {
      try {
        setClusterLoading(true)
        setClusterError('')
        const resp = await fetch(`${API_BASE}/api/stats/cluster?k=${encodeURIComponent(clusterK)}&include_params=true&pca_components=2`)
        if (!resp.ok) throw new Error('Failed to load clusters')
        const json = await resp.json()
        if (!aborted) setCluster(json)
      } catch (e) {
        if (!aborted) setClusterError(typeof e?.message === 'string' ? e.message : 'Failed to load clusters')
      } finally {
        if (!aborted) setClusterLoading(false)
      }
    }
    fetchCluster()
    return () => { aborted = true }
  }, [API_BASE, clusterK, serverData])

  function ScreePlot({ evr }) {
    if (!evr || evr.length === 0) return null
    const width = 420
    const height = 140
    const pad = 28
    const barW = (width - 2 * pad) / evr.length
    const maxV = Math.max(...evr, 0.001)
    return (
      <svg width={width} height={height} aria-label="Scree plot">
        <rect x={0} y={0} width={width} height={height} fill="#FFFFFF" />
        {evr.map((v, i) => {
          const h = ((v) / maxV) * (height - 2 * pad)
          const x = pad + i * barW
          const y = height - pad - h
          return (
            <g key={i}>
              <rect x={x} y={y} width={Math.max(barW - 6, 2)} height={h} fill="#60A5FA" />
              <text x={x + (barW - 6) / 2} y={height - 8} textAnchor="middle" fontSize="10" fill={palette.govBlue}>PC{i + 1}</text>
            </g>
          )
        })}
      </svg>
    )
  }

  function ClusterScatter({ scores, labels }) {
    if (!scores || !labels || scores.length === 0) return null
    const width = 420
    const height = 220
    const pad = 20
    const xs = scores.map((s) => s[0])
    const ys = scores.map((s) => s[1])
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const sx = (x) => pad + ((x - minX) / (maxX - minX || 1)) * (width - 2 * pad)
    const sy = (y) => height - pad - ((y - minY) / (maxY - minY || 1)) * (height - 2 * pad)
    const colors = ["#EF4444", "#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#14B8A6"]
    return (
      <svg width={width} height={height} aria-label="Cluster scatter">
        <rect x={0} y={0} width={width} height={height} fill="#FFFFFF" stroke="#E5E7EB" />
        {scores.map((s, i) => (
          <circle key={i} cx={sx(s[0])} cy={sy(s[1])} r={4} fill={colors[labels[i] % colors.length]} opacity={0.85} />
        ))}
      </svg>
    )
  }

  function MiniMap({ points, metal }) {
    const width = 420
    const height = 220
    if (!points || points.length === 0) return <div className="text-xs text-gray-600">No geo-tagged samples</div>
    const lats = points.map((p) => p.lat)
    const lngs = points.map((p) => p.lng)
    const minLat = Math.min(...lats)
    const maxLat = Math.max(...lats)
    const minLng = Math.min(...lngs)
    const maxLng = Math.max(...lngs)
    const pad = 10
    const sx = (lng) => pad + ((lng - minLng) / (maxLng - minLng || 1)) * (width - 2 * pad)
    const sy = (lat) => pad + ((maxLat - lat) / (maxLat - minLat || 1)) * (height - 2 * pad)
    const vals = points.map((p) => p.metals?.[metal]).filter((v) => v != null)
    const minV = Math.min(...vals, 0)
    const maxV = Math.max(...vals, 1)
    const colorFor = (v) => {
      const t = (Number(v ?? 0) - minV) / (maxV - minV || 1)
      const rC = Math.round(255 * t)
      const gC = Math.round(120 * (1 - t))
      const bC = Math.round(255 * (1 - t))
      return `rgb(${rC},${gC},${bC})`
    }
    return (
      <svg width={width} height={height} aria-label="Geo map">
        <rect x={0} y={0} width={width} height={height} fill="#F3F4F6" stroke="#E5E7EB" />
        {points.map((p) => (
          <circle key={p.id} cx={sx(p.lng)} cy={sy(p.lat)} r={5} fill={colorFor(p.metals?.[metal])} stroke="#374151" strokeWidth={0.5} />
        ))}
      </svg>
    )
  }

  return (
    <div className="mt-6">
      {extractedMetals && Object.keys(extractedMetals).length > 0 && (
        <div className="rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
          <div className="p-3 text-sm font-semibold" style={{ color: palette.govBlue }}>Extracted Metals</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: palette.govBlue }}>
                  <th className="px-3 py-2">Metal</th>
                  <th className="px-3 py-2">Value (mg/L)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(extractedMetals)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([metal, value]) => (
                    <tr key={metal} className="border-t" style={{ borderColor: palette.border }}>
                      <td className="px-3 py-2" style={{ color: palette.govBlue }}>{metal}</td>
                      <td className="px-3 py-2">{value ?? '-'}</td>
                    </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="rounded-lg border" style={{ borderColor: palette.border, backgroundColor: bg }}>
        <div className="p-4 flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span style={{ color: fg }}><StatusIcon category={category} /></span>
            <div>
              <div className="text-xs font-semibold tracking-wide" style={{ color: fg }}>[ STATUS: {label} ]</div>
              <div className="text-sm mt-1" style={{ color: palette.govBlue }}>
                HPI: {hpi?.toFixed ? hpi.toFixed(2) : hpi} | HEI: {hei?.toFixed ? hei.toFixed(2) : hei} | PLI: {pli?.toFixed ? pli.toFixed(3) : pli}
              </div>
              <div className="text-xs mt-1" style={{ color: fg }}>
                Exceedances: {exceededCount}{exceededCount > 0 ? ` (${exceededList})` : ''}
              </div>
              {severeOverride && (
                <div className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-red-700">
                  ⚠️ Strict override: at least one metal ≥ {thresholds?.STRICT_UNSAFE_FACTOR ?? 2}× its limit
                </div>
              )}
            </div>
          </div>
          <div className="shrink-0">
            <Gauge value={hpi} />
          </div>
        </div>
      </div>

      {thresholds && (
        <div className="mt-3 text-xs" style={{ color: palette.govBlue }}>
          Thresholds (configurable): HPI safe &lt; {thresholds.HPI_SAFE_MAX}, caution {thresholds.HPI_SAFE_MAX}–{thresholds.HPI_UNSAFE_MIN}, unsafe ≥ {thresholds.HPI_UNSAFE_MIN}; HEI safe ≤ {thresholds.HEI_SAFE_MAX}, unsafe &gt; {thresholds.HEI_UNSAFE_MIN}; PLI safe &lt; {thresholds.PLI_SAFE_MAX}, unsafe ≥ {thresholds.PLI_UNSAFE_MIN}.
        </div>
      )}

      {/* Descriptive statistics */}
      <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
        <div className="p-3 text-sm font-semibold" style={{ color: palette.govBlue }}>Dataset Statistics</div>
        {statsLoading && (
          <div className="px-3 pb-3 text-xs" style={{ color: palette.govBlue }}>Loading statistics…</div>
        )}
        {statsError && (
          <div className="px-3 pb-3 text-xs text-red-600">{statsError}</div>
        )}
        {!statsLoading && !statsError && statEntries.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: palette.govBlue }}>
                  <th className="px-3 py-2">Metal</th>
                  <th className="px-3 py-2">Count</th>
                  <th className="px-3 py-2">Mean</th>
                  <th className="px-3 py-2">Median</th>
                  <th className="px-3 py-2">Std</th>
                  <th className="px-3 py-2">Min</th>
                  <th className="px-3 py-2">Max</th>
                  <th className="px-3 py-2">Exceed %</th>
                  <th className="px-3 py-2">Histogram</th>
                  <th className="px-3 py-2">Box</th>
                </tr>
              </thead>
              <tbody>
                {statEntries
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([metal, s]) => (
                    <tr key={metal} className="border-t" style={{ borderColor: palette.border }}>
                      <td className="px-3 py-2" style={{ color: palette.govBlue }}>{metal}</td>
                      <td className="px-3 py-2">{s?.count ?? '-'}</td>
                      <td className="px-3 py-2">{s?.mean?.toFixed ? s.mean.toFixed(4) : s?.mean}</td>
                      <td className="px-3 py-2">{s?.median?.toFixed ? s.median.toFixed(4) : s?.median}</td>
                      <td className="px-3 py-2">{s?.std?.toFixed ? s.std.toFixed(4) : s?.std}</td>
                      <td className="px-3 py-2">{s?.min?.toFixed ? s.min.toFixed(4) : s?.min}</td>
                      <td className="px-3 py-2">{s?.max?.toFixed ? s.max.toFixed(4) : s?.max}</td>
                      <td className="px-3 py-2">{s?.exceed_pct?.toFixed ? `${s.exceed_pct.toFixed(1)}%` : s?.exceed_pct ?? '-'}</td>
                      <td className="px-3 py-2"><Histogram counts={s?.histogram?.counts} bins={s?.histogram?.bins} /></td>
                      <td className="px-3 py-2"><BoxPlot min={s?.box?.min} q1={s?.box?.q1} median={s?.box?.median} q3={s?.box?.q3} max={s?.box?.max} /></td>
                    </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* PCA & Clustering */}
      <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
        <div className="p-3 text-sm font-semibold" style={{ color: palette.govBlue }}>PCA (Dimensionality Reduction)</div>
        {pcaLoading && <div className="px-3 pb-3 text-xs" style={{ color: palette.govBlue }}>Loading PCA…</div>}
        {pcaError && <div className="px-3 pb-3 text-xs text-red-600">{pcaError}</div>}
        {!pcaLoading && !pcaError && pca?.explained_variance_ratio?.length > 0 && (
          <div className="px-3 pb-3">
            <ScreePlot evr={pca.explained_variance_ratio} />
          </div>
        )}
      </div>

      <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
        <div className="p-3 flex items-center justify-between">
          <div className="text-sm font-semibold" style={{ color: palette.govBlue }}>Clustering (K-means)</div>
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="clusterK" className="text-gray-700">k</label>
            <input id="clusterK" type="number" min={2} max={8} step={1} className="border rounded px-2 py-1 text-xs w-20" value={clusterK} onChange={(e) => setClusterK(Math.max(2, Math.min(8, Number(e.target.value) || 2)))} />
          </div>
        </div>
        {clusterLoading && <div className="px-3 pb-3 text-xs" style={{ color: palette.govBlue }}>Loading clusters…</div>}
        {clusterError && <div className="px-3 pb-3 text-xs text-red-600">{clusterError}</div>}
        {!clusterLoading && !clusterError && cluster?.labels?.length > 0 && (
          <div className="px-3 pb-3">
            {cluster?.pca2?.scores && (
              <div className="mb-3">
                <ClusterScatter scores={cluster.pca2.scores} labels={cluster.labels} />
                <div className="text-xs mt-1" style={{ color: palette.govBlue }}>PCA 2D embedding (colored by cluster)</div>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: palette.govBlue }}>
                    <th className="px-2 py-2">Sample ID</th>
                    <th className="px-2 py-2">Cluster</th>
                  </tr>
                </thead>
                <tbody>
                  {cluster.sample_ids.map((sid, i) => (
                    <tr key={sid} className="border-t" style={{ borderColor: palette.border }}>
                      <td className="px-2 py-2">{sid}</td>
                      <td className="px-2 py-2">{cluster.labels[i]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
      {assessments && Object.keys(assessments).length > 0 && (
        <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
          <div className="p-3 text-sm font-semibold" style={{ color: palette.govBlue }}>Detailed Breakdown</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: palette.govBlue }}>
                  <th className="px-3 py-2">Metal</th>
                  <th className="px-3 py-2">Value (mg/L)</th>
                  <th className="px-3 py-2">Limit (mg/L)</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(assessments).map(([metal, a]) => {
                  const ex = a?.exceeds === 1 || a?.exceeds === '1'
                  return (
                    <tr key={metal} className="border-t" style={{ borderColor: palette.border }}>
                      <td className="px-3 py-2" style={{ color: palette.govBlue }}>{metal}</td>
                      <td className="px-3 py-2">{a?.value_mg_l ?? '-'}</td>
                      <td className="px-3 py-2">{a?.limit_mg_l ?? '-'}</td>
                      <td className="px-3 py-2">
                        <span className={`inline-flex items-center gap-1 font-medium ${ex ? 'text-red-600' : 'text-green-700'}`}>
                          {ex ? '❌ Exceeds' : '✅ Within Limit'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Correlation */}
      <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
        <div className="p-3 flex items-center justify-between">
          <div className="text-sm font-semibold" style={{ color: palette.govBlue }}>Correlation Matrix</div>
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="corrMethod" className="text-gray-700">Method</label>
            <select id="corrMethod" value={corrMethod} onChange={(e) => setCorrMethod(e.target.value)} className="border rounded px-2 py-1 text-xs">
              <option value="pearson">Pearson</option>
              <option value="spearman">Spearman</option>
            </select>
          </div>
        </div>
        {corrLoading && <div className="px-3 pb-3 text-xs" style={{ color: palette.govBlue }}>Loading correlation…</div>}
        {corrError && <div className="px-3 pb-3 text-xs text-red-600">{corrError}</div>}
        {!corrLoading && !corrError && corr?.metals?.length > 0 && (
          <div className="px-3 pb-3 overflow-x-auto">
            <div className="mb-3">
              <Heatmap variables={corr.metals} matrix={corr.matrix} />
            </div>
            <table className="min-w-full text-xs">
              <thead>
                <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: palette.govBlue }}>
                  <th className="px-2 py-2">Var</th>
                  {corr.metals.map((v) => (
                    <th key={`h-${v}`} className="px-2 py-2">{v}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {corr.metals.map((ri, i) => (
                  <tr key={`r-${ri}`} className="border-t" style={{ borderColor: palette.border }}>
                    <td className="px-2 py-2" style={{ color: palette.govBlue }}>{ri}</td>
                    {corr.metals.map((cj, j) => {
                      const val = corr.matrix[ri]?.[cj] ?? 0
                      return (
                        <td key={`c-${i}-${j}`} className="px-2 py-2">
                          {typeof val === 'number' ? val.toFixed(2) : val}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="mt-5 rounded-lg border p-3 text-sm" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF', color: palette.govBlue }}>
        <div className="font-semibold mb-1">Interpretation</div>
        <div>
          {(() => {
            if (category === 'unsafe') {
              return `HPI exceeded the 100 threshold (${hpi?.toFixed ? hpi.toFixed(2) : hpi}). ${exceeded.length > 0 ? `Exceedances: ${exceededList}.` : ''} Recommended action: mitigation and alternative water source assessment.`
            }
            if (category === 'caution') {
              return `Indices indicate moderate risk. ${exceeded.length > 0 ? `Exceedances: ${exceededList}.` : 'No exceedances.'} Recommended action: increased monitoring.`
            }
            if (category === 'safe') {
              return 'All parameters within permissible limits and indices in safe range.'
            }
            return 'Insufficient data to classify.'
          })()}
        </div>
      </div>

      {/* Trends */}
      <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
        <div className="p-3 flex items-center justify-between">
          <div className="text-sm font-semibold" style={{ color: palette.govBlue }}>Trends Over Time</div>
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="trendMetal" className="text-gray-700">Metal</label>
            <select id="trendMetal" value={trendMetal} onChange={(e) => setTrendMetal(e.target.value)} className="border rounded px-2 py-1 text-xs">
              {Object.keys(trends?.metals || {}).map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        {trendsLoading && <div className="px-3 pb-3 text-xs" style={{ color: palette.govBlue }}>Loading trends…</div>}
        {trendsError && <div className="px-3 pb-3 text-xs text-red-600">{trendsError}</div>}
        {!trendsLoading && !trendsError && trendMetal && trends?.metals?.[trendMetal] && (
          <div className="px-3 pb-3">
            <LineChart dates={trends.metals[trendMetal].dates} values={trends.metals[trendMetal].values} />
          </div>
        )}
      </div>

      {/* Geo Visualization */}
      <div className="mt-5 rounded-lg border" style={{ borderColor: palette.border, backgroundColor: '#FFFFFF' }}>
        <div className="p-3 flex items-center justify-between">
          <div className="text-sm font-semibold" style={{ color: palette.govBlue }}>Geo Visualization</div>
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-2">
              <label htmlFor="geoMetal" className="text-gray-700">Metal</label>
              <select id="geoMetal" value={geoMetal} onChange={(e) => setGeoMetal(e.target.value)} className="border rounded px-2 py-1 text-xs">
                {Array.from(new Set([...Object.keys(extractedMetals || {}), ...Object.keys(assessments || {})])).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="geoGrid" className="text-gray-700">Grid (m)</label>
              <input id="geoGrid" type="number" min={0} step={100} className="border rounded px-2 py-1 text-xs w-24" value={geoGrid} onChange={(e) => setGeoGrid(Number(e.target.value) || 0)} />
            </div>
          </div>
        </div>
        {geoLoading && <div className="px-3 pb-3 text-xs" style={{ color: palette.govBlue }}>Loading geo data…</div>}
        {geoError && <div className="px-3 pb-3 text-xs text-red-600">{geoError}</div>}
        {!geoLoading && !geoError && geo && (
          <div className="px-3 pb-3">
            <MiniMap points={geo.points} metal={geoMetal} />
          </div>
        )}
      </div>
    </div>
  )
}


