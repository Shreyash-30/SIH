import { useLocation } from 'react-router-dom'
import { useEffect, useState, useMemo } from 'react'

export default function ResultsPanel() {
  const location = useLocation()
  const initialData = location?.state?.data || null
  const [data, setData] = useState(initialData)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [monthlyStats, setMonthlyStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [metalIndices, setMetalIndices] = useState(null)
  const [indicesLoading, setIndicesLoading] = useState(false)
  const [metalFormulas, setMetalFormulas] = useState(null)
  const [formulasLoading, setFormulasLoading] = useState(false)
  const API_BASE = import.meta?.env?.VITE_API_URL || 'http://localhost:8000'

  // If we don't have data from navigation, fetch most recent sample detail from backend
  useEffect(() => {
    let aborted = false
    async function fetchLatest() {
      if (data && (data.extracted_metals || data.metals)) return
      try {
        setLoading(true)
        setError('')
        // If we have an id in navigation data but no metals, fetch that sample
        const navId = initialData?.id
        if (navId) {
          const resp = await fetch(`${API_BASE}/api/samples/${navId}`)
          if (!resp.ok) throw new Error('Failed to load sample')
        const json = await resp.json()
          if (!aborted) setData(json)
          return
        }
        // Else, fetch list and take the latest
        const listResp = await fetch(`${API_BASE}/api/samples`)
        if (!listResp.ok) throw new Error('Failed to load samples list')
        const list = await listResp.json()
        if (!list || list.length === 0) {
          if (!aborted) setError('No samples available')
          return
        }
        const latest = list[list.length - 1]
        const detResp = await fetch(`${API_BASE}/api/samples/${latest.id}`)
        if (!detResp.ok) throw new Error('Failed to load sample details')
        const detail = await detResp.json()
        if (!aborted) setData(detail)
      } catch (e) {
        if (!aborted) setError(typeof e?.message === 'string' ? e.message : 'Failed to load data')
      } finally {
        if (!aborted) setLoading(false)
      }
    }
    fetchLatest()
    return () => { aborted = true }
  }, [API_BASE, initialData, data])

  const metals = useMemo(() => {
    if (data?.extracted_metals) return data.extracted_metals
    if (data?.metals) return data.metals
    return {}
  }, [data])

  const timeseries = useMemo(() => data?.timeseries || null, [data])
  const limits = useMemo(() => data?.limits_mg_l || {}, [data])

  // Fetch monthly statistics when we have timeseries data
  useEffect(() => {
    let aborted = false
    async function fetchMonthlyStats() {
      if (!timeseries || !data?.id) return
      
      try {
        setStatsLoading(true)
        const resp = await fetch(`${API_BASE}/api/stats/monthly?sample_id=${data.id}`)
        if (!resp.ok) throw new Error('Failed to load monthly statistics')
        const stats = await resp.json()
        if (!aborted) setMonthlyStats(stats)
      } catch (e) {
        console.error('Error fetching monthly stats:', e)
        if (!aborted) setMonthlyStats(null)
      } finally {
        if (!aborted) setStatsLoading(false)
      }
    }
    fetchMonthlyStats()
    return () => { aborted = true }
  }, [timeseries, data?.id, API_BASE])

  // Fetch metal indices table (avg vs limits) when we have timeseries
  useEffect(() => {
    let aborted = false
    async function fetchMetalIndices() {
      if (!timeseries || !data?.id) return
      try {
        setIndicesLoading(true)
        const resp = await fetch(`${API_BASE}/api/stats/metal-indices?sample_id=${data.id}`)
        if (!resp.ok) throw new Error('Failed to load metal indices')
        const json = await resp.json()
        if (!aborted) setMetalIndices(json)
      } catch (e) {
        console.error('Error fetching metal indices:', e)
        if (!aborted) setMetalIndices(null)
      } finally {
        if (!aborted) setIndicesLoading(false)
      }
    }
    fetchMetalIndices()
    return () => { aborted = true }
  }, [timeseries, data?.id, API_BASE])

  // Fetch per-metal formula values table
  useEffect(() => {
    let aborted = false
    async function fetchMetalFormulas() {
      if (!timeseries || !data?.id) return
      try {
        setFormulasLoading(true)
        const resp = await fetch(`${API_BASE}/api/stats/metal-formulas?sample_id=${data.id}`)
        if (!resp.ok) throw new Error('Failed to load metal formulas')
        const json = await resp.json()
        if (!aborted) setMetalFormulas(json)
      } catch (e) {
        console.error('Error fetching metal formulas:', e)
        if (!aborted) setMetalFormulas(null)
      } finally {
        if (!aborted) setFormulasLoading(false)
      }
    }
    fetchMetalFormulas()
    return () => { aborted = true }
  }, [timeseries, data?.id, API_BASE])

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#FFFFFF' }}>
      <div className="max-w-[1100px] mx-auto px-4 py-6">
        <h1 className="text-xl font-semibold mb-4" style={{ color: '#004E92' }}>Results</h1>
        {loading && (
          <div className="text-sm text-gray-700 mb-3">Loading…</div>
        )}
        {error && (
          <div className="text-sm text-red-600 mb-3">{error}</div>
        )}
        {/* If timeseries present, show month-wise table; else show simple list */}
        {timeseries ? (
          <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
            <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>Month-wise Concentrations (mg/L)</div>
          <div className="overflow-x-auto">
              {(() => {
                const metalsList = Object.keys(timeseries)
                const monthsSet = new Set()
                metalsList.forEach(m => Object.keys(timeseries[m] || {}).forEach(mm => monthsSet.add(mm)))
                const months = Array.from(monthsSet)
                // Order common month names if applicable
                const order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                const allInOrder = months.every(m => order.includes(m))
                const cols = allInOrder ? order.filter(m => months.includes(m)) : months.sort()
                return (
            <table className="min-w-full text-sm">
              <thead>
                      <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: '#004E92' }}>
                  <th className="px-3 py-2">Metal</th>
                        {cols.map(c => (
                          <th key={c} className="px-3 py-2">{c}</th>
                        ))}
                        <th className="px-3 py-2">Permissible (mg/L)</th>
                </tr>
              </thead>
              <tbody>
                      {metalsList.sort((a,b)=>a.localeCompare(b)).map(metal => (
                        <tr key={metal} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                          <td className="px-3 py-2" style={{ color: '#004E92' }}>{metal}</td>
                          {cols.map(c => {
                            const v = timeseries[metal]?.[c]
                            const lim = limits[metal]
                            const exceed = typeof v === 'number' && typeof lim === 'number' && v > lim
                            return (
                              <td key={`${metal}-${c}`} className="px-3 py-2" style={{ color: exceed ? '#B91C1C' : undefined }}>
                                {v ?? '-'}
                              </td>
                            )
                          })}
                          <td className="px-3 py-2">{limits[metal] ?? '-'}</td>
                    </tr>
                ))}
              </tbody>
            </table>
                )
              })()}
          </div>
        </div>
        ) : (
          <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
            <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>Extracted Metals (mg/L)</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                  <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: '#004E92' }}>
                  <th className="px-3 py-2">Metal</th>
                    <th className="px-3 py-2">Concentration</th>
                    <th className="px-3 py-2">Permissible (mg/L)</th>
                </tr>
              </thead>
              <tbody>
                  {Object.keys(metals).length === 0 && (
                    <tr>
                      <td colSpan={2} className="px-3 py-4 text-gray-600">No metal concentrations found.</td>
                    </tr>
                  )}
                  {Object.entries(metals)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([metal, value]) => (
                      <tr key={metal} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                        <td className="px-3 py-2" style={{ color: '#004E92' }}>{metal}</td>
                        <td className="px-3 py-2" style={{ color: (typeof value === 'number' && typeof limits[metal] === 'number' && value > limits[metal]) ? '#B91C1C' : undefined }}>{value ?? '-'}</td>
                        <td className="px-3 py-2">{limits[metal] ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        
        {/* Monthly Statistical Analysis Table */}
        {timeseries && monthlyStats && !monthlyStats.error && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                {monthlyStats.title || 'Monthly Statistical Analysis'}
              </div>
              {statsLoading && (
                <div className="p-4 text-sm text-gray-700">Loading statistical analysis...</div>
              )}
              {!statsLoading && monthlyStats.table_data && (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: '#004E92' }}>
                        <th className="px-3 py-2">Statistical Variables</th>
                        {monthlyStats.metals?.map(metal => (
                          <th key={metal} className="px-3 py-2">{metal}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {monthlyStats.statistical_variables?.map(statVar => (
                        <tr key={statVar} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                          <td className="px-3 py-2 font-medium" style={{ color: '#004E92' }}>
                            {statVar.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </td>
                          {monthlyStats.metals?.map(metal => (
                            <td key={`${statVar}-${metal}`} className="px-3 py-2">
                              {monthlyStats.table_data[statVar]?.[metal] ?? '-'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Metal Indices Table (below previous table) */}
        {timeseries && metalIndices && !metalIndices.error && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                {metalIndices.title || 'Metal Indices'}
              </div>
              {indicesLoading && (
                <div className="p-4 text-sm text-gray-700">Loading metal indices...</div>
              )}
              {!indicesLoading && metalIndices.table_data && (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: '#004E92' }}>
                        <th className="px-3 py-2">Metal</th>
                        {metalIndices.metal_headers?.map(h => (
                          <th key={h} className="px-3 py-2">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {metalIndices.row_labels?.map(label => (
                        <tr key={label} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                          <td className="px-3 py-2 font-medium" style={{ color: '#004E92' }}>
                            {label === 'mean_mgL' ? 'Mean (mg/L)'
                              : label === 'limit_mgL' ? 'Permissible (mg/L)'
                              : label === 'ratio' ? 'Mean / Limit'
                              : label === 'percent_limit' ? '% of Limit'
                              : label}
                          </td>
                          {metalIndices.metal_headers?.map(h => (
                            <td key={`${label}-${h}`} className="px-3 py-2">
                              {metalIndices.table_data?.[label]?.[h] ?? '-'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Metal Formula Values Table */}
        {timeseries && metalFormulas && !metalFormulas.error && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                {metalFormulas.title || 'Metal Formula Values'}
              </div>
              {formulasLoading && (
                <div className="p-4 text-sm text-gray-700">Loading formula values...</div>
              )}
              {!formulasLoading && metalFormulas.table_data && (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: '#004E92' }}>
                        <th className="px-3 py-2">Metal</th>
                        {metalFormulas.metal_headers?.map(h => (
                          <th key={h} className="px-3 py-2">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {metalFormulas.row_labels?.map(label => (
                        <tr key={label} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                          <td className="px-3 py-2 font-medium" style={{ color: '#004E92' }}>
                            {label === 'Q' ? 'Q (HPI)'
                              : label === 'W' ? 'W (HPI)'
                              : label === 'WQ' ? 'W×Q (HPI contribution)'
                              : label === 'Cf' ? 'Cf (Cd)'
                              : label === 'HEI_term' ? 'Term (HEI)'
                              : label === 'CDI' ? 'CDI'
                              : label === 'HQ' ? 'HQ'
                              : label}
                          </td>
                          {metalFormulas.metal_headers?.map(h => (
                            <td key={`${label}-${h}`} className="px-3 py-2">
                              {metalFormulas.table_data?.[label]?.[h] ?? '-'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


