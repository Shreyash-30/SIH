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
  const [reportTimerMs, setReportTimerMs] = useState(0)
  const metals = useMemo(() => {
    if (data?.extracted_metals) return data.extracted_metals
    if (data?.metals) return data.metals
    return {}
  }, [data])
  const timeseries = useMemo(() => data?.timeseries || null, [data])
  const limits = useMemo(() => data?.limits_mg_l || {}, [data])
  const reportLoading = loading || (!!timeseries && (statsLoading || indicesLoading || formulasLoading))
  const API_BASE = import.meta?.env?.VITE_API_URL || 'http://localhost:8000'

  // Correlation matrix state
  const [corrData, setCorrData] = useState(null) // Pearson
  const [corrLoading, setCorrLoading] = useState(false)
  const [corrDataSpearman, setCorrDataSpearman] = useState(null)
  const [corrLoadingSpearman, setCorrLoadingSpearman] = useState(false)

  // ML Forecast + Hotspot state
  const [forecastTarget, setForecastTarget] = useState('HPI')
  const [forecastModel, setForecastModel] = useState('auto') // auto|linear|poly2|gbr
  const [forecastHorizon, setForecastHorizon] = useState(6)
  const [forecastData, setForecastData] = useState(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const [hotspotInfo, setHotspotInfo] = useState(null)
  const [hotspotLoading, setHotspotLoading] = useState(false)
  const [centerLat, setCenterLat] = useState('')
  const [centerLon, setCenterLon] = useState('')
  const [radiusKm, setRadiusKm] = useState('')
  const [useForecastHotspot, setUseForecastHotspot] = useState(false)
  const [heatmapOn, setHeatmapOn] = useState(true)

  // Server-rendered visualization images
  const [vizHpiUrl, setVizHpiUrl] = useState(null)
  const [vizHpiOverallUrl, setVizHpiOverallUrl] = useState(null)
  const [vizHeiPliUrl, setVizHeiPliUrl] = useState(null)
  const [vizHqUrl, setVizHqUrl] = useState(null)

  // Client-side correlation (fallback) computed from available data
  const clientCorr = useMemo(() => {
    // Helper: Pearson correlation for two numeric arrays with NaN filtering
    const pearson = (a, b) => {
      const x = []
      const y = []
      for (let i = 0; i < a.length; i++) {
        const av = a[i]
        const bv = b[i]
        if (Number.isFinite(av) && Number.isFinite(bv)) {
          x.push(av)
          y.push(bv)
        }
      }
      const n = x.length
      if (n < 2) return NaN
      const mean = arr => arr.reduce((s, v) => s + v, 0) / arr.length
      const mx = mean(x)
      const my = mean(y)
      let num = 0, dx = 0, dy = 0
      for (let i = 0; i < n; i++) {
        const ux = x[i] - mx
        const uy = y[i] - my
        num += ux * uy
        dx += ux * ux
        dy += uy * uy
      }
      const den = Math.sqrt(dx) * Math.sqrt(dy)
      if (!Number.isFinite(den) || den === 0) return NaN
      return num / den
    }

    // Preferred: use timeseries (metals x months)
    if (timeseries) {
      const metalsList = Object.keys(timeseries)
      if (metalsList.length >= 2) {
        // union of months
        const monthsSet = new Set()
        metalsList.forEach(m => Object.keys(timeseries[m] || {}).forEach(mm => monthsSet.add(mm)))
        const months = Array.from(monthsSet)
        const seriesByMetal = {}
        metalsList.forEach(m => {
          seriesByMetal[m] = months.map(mm => {
            const v = timeseries[m]?.[mm]
            const val = typeof v === 'number' ? v : parseFloat(v)
            return Number.isFinite(val) ? val : NaN
          })
        })
        const matrix = {}
        metalsList.forEach(r => {
          matrix[r] = {}
          metalsList.forEach(c => {
            const corr = pearson(seriesByMetal[r], seriesByMetal[c])
            matrix[r][c] = Number.isFinite(corr) ? corr : 0
          })
        })
        return { method: 'pearson-local-timeseries', matrix, metals: metalsList }
      }
    }

    // Fallback: build feature vectors per metal from indices/formulas/limits/extracted values
    // Vector features per metal (as available):
    // mean_mgL, limit_mgL, ratio, percent_limit, Q, W, WQ, extracted_value
    const metalsSet = new Set()
    if (metalFormulas?.metal_headers) metalFormulas.metal_headers.forEach(m => metalsSet.add(m))
    if (metalIndices?.metal_headers) metalIndices.metal_headers.forEach(m => metalsSet.add(m))
    if (data?.metals) Object.keys(data.metals).forEach(m => metalsSet.add(m))
    if (data?.limits_mg_l) Object.keys(data.limits_mg_l).forEach(m => metalsSet.add(m))
    const metalsList = Array.from(metalsSet)
    if (metalsList.length < 2) return null

    const tableF = metalFormulas?.table_data || {}
    const tableI = metalIndices?.table_data || {}
    const featureNames = ['mean_mgL','limit_mgL','ratio','percent_limit','Q','W','WQ','extracted']
    const getFeatureVector = (metal) => {
      const vec = []
      // indices
      const mean = parseFloat(tableI?.['mean_mgL']?.[metal])
      const limitI = parseFloat(tableI?.['limit_mgL']?.[metal])
      const ratio = parseFloat(tableI?.['ratio']?.[metal])
      const percent = parseFloat(tableI?.['percent_limit']?.[metal])
      // formulas
      const Q = parseFloat(tableF?.['Q']?.[metal])
      const W = parseFloat(tableF?.['W']?.[metal])
      let WQ = parseFloat(tableF?.['WQ']?.[metal])
      if (!Number.isFinite(WQ) && Number.isFinite(Q) && Number.isFinite(W)) WQ = W * Q
      // limits and extracted current metals
      const extr = parseFloat(data?.metals?.[metal])
      const limitDirect = parseFloat(data?.limits_mg_l?.[metal])
      const feats = [mean, (Number.isFinite(limitI) ? limitI : limitDirect), ratio, percent, Q, W, WQ, extr]
      feats.forEach(v => vec.push(Number.isFinite(v) ? v : NaN))
      return vec
    }
    const vectors = {}
    metalsList.forEach(m => { vectors[m] = getFeatureVector(m) })
    // Require at least 3 overlapping finite features to correlate
    const matrix = {}
    metalsList.forEach(r => {
      matrix[r] = {}
      metalsList.forEach(c => {
        const a = vectors[r]
        const b = vectors[c]
        const filteredA = []
        const filteredB = []
        for (let i = 0; i < Math.min(a.length, b.length); i++) {
          if (Number.isFinite(a[i]) && Number.isFinite(b[i])) {
            filteredA.push(a[i])
            filteredB.push(b[i])
          }
        }
        const corr = filteredA.length >= 3 ? pearson(filteredA, filteredB) : NaN
        matrix[r][c] = Number.isFinite(corr) ? corr : 0
      })
    })
    return { method: 'pearson-local-features', matrix, metals: metalsList }
  }, [timeseries, metalFormulas, metalIndices, data])

  // Always resolve to a fresh sample detail (prefer ID from navigation; fallback to latest)
  useEffect(() => {
    // Optimistic render: show whatever we have from navigation immediately
    if (initialData && !data) setData(initialData)
  }, [initialData])

  // Always resolve to a fresh sample detail (prefer ID from navigation; fallback to latest)
  useEffect(() => {
    let aborted = false
    async function fetchDetail() {
      try {
        setLoading(true)
        setError('')
        let sampleId = initialData?.id
        if (!sampleId) {
          const listResp = await fetch(`${API_BASE}/api/samples`)
          if (!listResp.ok) throw new Error('Failed to load samples list')
          const list = await listResp.json()
          if (!list || list.length === 0) {
            if (!aborted) setError('No samples available')
            return
          }
          sampleId = list[list.length - 1]?.id
        }
        if (!sampleId) {
          if (!aborted) setError('No sample selected')
          return
        }
        const detResp = await fetch(`${API_BASE}/api/samples/${sampleId}`)
        if (!detResp.ok) throw new Error('Failed to load sample details')
        const detail = await detResp.json()
        if (!aborted) setData(detail)
      } catch (e) {
        if (!aborted) setError(typeof e?.message === 'string' ? e.message : 'Failed to load data')
      } finally {
        if (!aborted) setLoading(false)
      }
    }
    fetchDetail()
    return () => { aborted = true }
  }, [API_BASE, initialData?.id])

  

  // Helper: fetch with simple retry/backoff
  const fetchWithRetry = async (url, { tries = 5, delayMs = 600, validate } = {}) => {
    let lastError = null
    for (let i = 0; i < tries; i++) {
      try {
        const resp = await fetch(url)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const json = await resp.json()
        if (typeof validate === 'function' && !validate(json)) {
          throw new Error('Invalid payload or not ready')
        }
        return json
      } catch (e) {
        lastError = e
        if (i < tries - 1) await new Promise(r => setTimeout(r, delayMs))
      }
    }
    throw lastError || new Error('Request failed')
  }

  // Fetch monthly statistics when we have timeseries data
  useEffect(() => {
    let aborted = false
    async function fetchMonthlyStats() {
      if (!data?.id) return
      
      try {
        setStatsLoading(true)
        const stats = await fetchWithRetry(
          `${API_BASE}/api/stats/monthly?sample_id=${data.id}`,
          { tries: 5, delayMs: 700, validate: (j) => j && !j.error }
        )
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
  }, [data?.id, API_BASE])

  // Fetch server-rendered visualization images (PNG) when sample id is available
  useEffect(() => {
    let aborted = false
    async function fetchViz() {
      if (!data?.id) return
      try {
        // Step 2: HPI monthly
        // Step 2: HPI monthly
        const hpiResp = await fetch(`${API_BASE}/api/visualization/hpi?sample_id=${data.id}`)
        if (hpiResp.ok) {
          const hpiJson = await hpiResp.json()
          if (!aborted && hpiJson?.image_url) setVizHpiUrl(`${API_BASE}${hpiJson.image_url}?t=${Date.now()}`)
        }
      } catch {}
      try {
        // Step 2b: Overall HPI gauge (Safe/Caution/Unsafe)
        const hpiOverallResp = await fetch(`${API_BASE}/api/visualization/hpi-overall?sample_id=${data.id}`)
        if (hpiOverallResp.ok) {
          const hpiOverallJson = await hpiOverallResp.json()
          if (!aborted && hpiOverallJson?.image_url) setVizHpiOverallUrl(`${API_BASE}${hpiOverallJson.image_url}?t=${Date.now()}`)
        }
      } catch {}
      try {
        // Step 3: HEI & PLI grouped
        const heiResp = await fetch(`${API_BASE}/api/visualization/hei-pli?sample_id=${data.id}`)
        if (heiResp.ok) {
          const heiJson = await heiResp.json()
          if (!aborted && heiJson?.image_url) setVizHeiPliUrl(`${API_BASE}${heiJson.image_url}?t=${Date.now()}`)
        }
      } catch {}
      try {
        // Step 4: HQ by metal (needs current metals of sample)
        const hqResp = await fetch(`${API_BASE}/api/visualization/hq?sample_id=${data.id}`)
        if (hqResp.ok) {
          const hqJson = await hqResp.json()
          if (!aborted && hqJson?.image_url) setVizHqUrl(`${API_BASE}${hqJson.image_url}?t=${Date.now()}`)
        }
      } catch {}
    }
    fetchViz()
    return () => { aborted = true }
  }, [data?.id, API_BASE])

  // Fetch Pearson correlation matrix across samples
  useEffect(() => {
    let aborted = false
    async function fetchCorrelation() {
      try {
        setCorrLoading(true)
        const resp = await fetch(`${API_BASE}/api/stats/correlation?method=pearson`)
        if (!resp.ok) throw new Error('Failed to load correlation matrix')
        const json = await resp.json()
        if (!aborted) setCorrData(json)
      } catch (e) {
        if (!aborted) setCorrData(null)
      } finally {
        if (!aborted) setCorrLoading(false)
      }
    }
    fetchCorrelation()
    return () => { aborted = true }
  }, [API_BASE])

  // Fetch Spearman correlation matrix across samples
  useEffect(() => {
    let aborted = false
    async function fetchCorrelationSpearman() {
      try {
        setCorrLoadingSpearman(true)
        const resp = await fetch(`${API_BASE}/api/stats/correlation?method=spearman`)
        if (!resp.ok) throw new Error('Failed to load spearman correlation matrix')
        const json = await resp.json()
        if (!aborted) setCorrDataSpearman(json)
      } catch (e) {
        if (!aborted) setCorrDataSpearman(null)
      } finally {
        if (!aborted) setCorrLoadingSpearman(false)
      }
    }
    fetchCorrelationSpearman()
    return () => { aborted = true }
  }, [API_BASE])

  // Prepare combined HPI contribution (W×Q) data for a single bar chart
  const hpiCombined = useMemo(() => {
    if (!metalFormulas || !metalFormulas.table_data || !metalFormulas.metal_headers) return null
    const WQraw = metalFormulas.table_data['WQ'] || {}
    const Qraw = metalFormulas.table_data['Q'] || {}
    const Wraw = metalFormulas.table_data['W'] || {}
    const metalsList = metalFormulas.metal_headers
    const series = metalsList.map(m => {
      let v = parseFloat(WQraw[m])
      if (!Number.isFinite(v)) {
        const q = parseFloat(Qraw[m])
        const w = parseFloat(Wraw[m])
        v = (Number.isFinite(q) && Number.isFinite(w)) ? (w * q) : 0
      }
      return { metal: m, value: Number.isFinite(v) ? v : 0 }
    })
    const maxVal = Math.max(1, ...series.map(d => (Number.isFinite(d.value) ? d.value : 0)))
    return { series, maxVal }
  }, [metalFormulas])

  // Final laboratory-style summary report derived from indices and formulas
  const finalReport = useMemo(() => {
    if (!metalIndices || metalIndices.error || !metalIndices.table_data || !metalIndices.metal_headers) return null
    const headers = metalIndices.metal_headers
    const means = metalIndices.table_data['mean_mgL'] || {}
    const lims = metalIndices.table_data['limit_mgL'] || {}

    const perMetal = headers.map(m => {
      const mean = parseFloat(means[m])
      const lim = parseFloat(lims[m] ?? limits?.[m])
      const exceed = Number.isFinite(mean) && Number.isFinite(lim) && lim > 0 && mean > lim
      return { metal: m, mean: Number.isFinite(mean) ? mean : null, limit: Number.isFinite(lim) ? lim : null, exceed }
    })

    // Optional: compute overall HPI and HEI if formula terms are available
    let hpi = null, hpiStatus = null, hei = null, heiStatus = null, topContributor = null
    if (metalFormulas && metalFormulas.table_data && metalFormulas.metal_headers) {
      const W = metalFormulas.table_data['W'] || {}
      const WQ = metalFormulas.table_data['WQ'] || {}
      const HEI_term = metalFormulas.table_data['HEI_term'] || {}
      let sumW = 0, sumWQ = 0, maxWQ = -Infinity, maxMetal = null, sumHEI = 0
      metalFormulas.metal_headers.forEach(m => {
        const w = parseFloat(W[m])
        const wq = parseFloat(WQ[m])
        const heiTerm = parseFloat(HEI_term[m])
        if (Number.isFinite(w)) sumW += w
        if (Number.isFinite(wq)) {
          sumWQ += wq
          if (wq > maxWQ) { maxWQ = wq; maxMetal = m }
        }
        if (Number.isFinite(heiTerm)) sumHEI += heiTerm
      })
      if (sumW > 0) {
        hpi = sumWQ / sumW
        hpiStatus = hpi < 100 ? 'Safe' : (hpi < 150 ? 'Caution' : 'Unsafe')
      }
      if (Number.isFinite(sumHEI)) {
        hei = sumHEI
        heiStatus = hei < 5 ? 'Within Limit' : 'Exceeds Threshold'
      }
      if (Number.isFinite(maxWQ) && maxMetal) {
        topContributor = { metal: maxMetal, wq: maxWQ }
      }
    }

    return { perMetal, hpi, hpiStatus, hei, heiStatus, topContributor }
  }, [metalIndices, metalFormulas, limits])

  // Fetch metal indices table (avg vs limits) when we have timeseries
  useEffect(() => {
    let aborted = false
    async function fetchMetalIndices() {
      if (!data?.id) return
      try {
        setIndicesLoading(true)
        const json = await fetchWithRetry(
          `${API_BASE}/api/stats/metal-indices?sample_id=${data.id}`,
          { tries: 5, delayMs: 700, validate: (j) => j && !j.error }
        )
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
  }, [data?.id, API_BASE])

  // Report generation timer: runs while any report requests are in-flight
  useEffect(() => {
    let intervalId = null
    let startTs = Date.now()
    if (reportLoading) {
      startTs = Date.now()
      setReportTimerMs(0)
      intervalId = setInterval(() => {
        setReportTimerMs(Date.now() - startTs)
      }, 250)
    } else {
      setReportTimerMs(0)
    }
    return () => {
      if (intervalId) clearInterval(intervalId)
    }
  }, [reportLoading])

  // Fetch per-metal formula values table
  useEffect(() => {
    let aborted = false
    async function fetchMetalFormulas() {
      if (!data?.id) return
      try {
        setFormulasLoading(true)
        const json = await fetchWithRetry(
          `${API_BASE}/api/stats/metal-formulas?sample_id=${data.id}`,
          { tries: 5, delayMs: 700, validate: (j) => j && !j.error }
        )
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
  }, [data?.id, API_BASE])

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
        {/* Report generation banner with timer */}
        {reportLoading && (
          <div className="mb-4 rounded-md border px-3 py-2 text-sm flex items-center gap-2" style={{ borderColor: '#BFDBFE', backgroundColor: '#EFF6FF', color: '#1E40AF' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="animate-spin" style={{ animationDuration: '1s' }}>
              <path d="M12 2a10 10 0 1 0 10 10" stroke="#1E40AF" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span>
              Generating report… {new Date(reportTimerMs).toISOString().substring(14, 19)}
            </span>
          </div>
        )}

        {/* Final Laboratory-Style Summary Report */}
        {finalReport && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>Final Laboratory Report (Summary)</div>
              <div className="p-4 space-y-4">
                {/* Overall indices summary */}
                <div className="text-sm">
                  {typeof finalReport.hpi === 'number' && (
                    <div className="mb-1"><span className="font-medium" style={{ color: '#004E92' }}>HPI (overall):</span> {finalReport.hpi.toFixed(2)} — <span>{finalReport.hpiStatus}</span> <span className="text-gray-500">(Safe&lt;100, 100–150 Caution, ≥150 Unsafe)</span></div>
                  )}
                  {typeof finalReport.hei === 'number' && (
                    <div><span className="font-medium" style={{ color: '#004E92' }}>HEI (overall):</span> {finalReport.hei.toFixed(2)} — <span>{finalReport.heiStatus}</span> <span className="text-gray-500">(Threshold ≈ 5.0)</span></div>
                  )}
                </div>
                {/* Per-metal exceedance table */}
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left" style={{ backgroundColor: '#F9FAFB', color: '#004E92' }}>
                        <th className="px-3 py-2">Metal</th>
                        <th className="px-3 py-2">Mean (mg/L)</th>
                        <th className="px-3 py-2">Permissible (mg/L)</th>
                        <th className="px-3 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {finalReport.perMetal
                        .slice()
                        .sort((a,b) => a.metal.localeCompare(b.metal))
                        .map(row => (
                          <tr key={row.metal} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                            <td className="px-3 py-2" style={{ color: '#004E92' }}>{row.metal}</td>
                            <td className="px-3 py-2" style={{ color: row.exceed ? '#B91C1C' : undefined }}>{Number.isFinite(row.mean) ? row.mean.toFixed(3) : '-'}</td>
                            <td className="px-3 py-2">{Number.isFinite(row.limit) ? row.limit.toFixed(3) : '-'}</td>
                            <td className="px-3 py-2" style={{ color: row.exceed ? '#B91C1C' : '#065F46' }}>{row.exceed ? 'Exceeds Limit' : 'Within Limit'}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                {/* Conclusion */}
                {(finalReport.topContributor || typeof finalReport.hpi === 'number' || typeof finalReport.hei === 'number') && (
                  <div className="text-sm">
                    {finalReport.topContributor && (
                      <div className="mb-1"><span className="font-medium" style={{ color: '#004E92' }}>Highest contributor to HPI:</span> {finalReport.topContributor.metal} <span className="text-gray-600">(W×Q ≈ {finalReport.topContributor.wq.toFixed(2)})</span></div>
                    )}
                    {typeof finalReport.hpi === 'number' && (
                      <div className="mb-1">Overall HPI indicates: <span className="font-medium">{finalReport.hpiStatus}</span>.</div>
                    )}
                    {typeof finalReport.hei === 'number' && (
                      <div>Overall HEI indicates: <span className="font-medium">{finalReport.heiStatus}</span>.</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
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

        

        {/* Correlation matrices removed as requested */}
        {/* Server-rendered visualizations (images) */}
        {(vizHpiUrl || vizHpiOverallUrl || vizHeiPliUrl || vizHqUrl) && (
          <div className="mt-8 grid grid-cols-1 gap-6">
            {vizHpiUrl && (
              <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>Monthly HPI (Color-coded)</div>
                <div className="p-4 overflow-x-auto"><img src={vizHpiUrl} alt="HPI Monthly" className="max-w-full h-auto" /></div>
              </div>
            )}
            {vizHpiOverallUrl && (
              <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>Overall HPI Risk</div>
                <div className="p-4 overflow-x-auto">
                  <div className="text-xs text-gray-600 mb-2">Thresholds: HPI &lt; 100 → Safe, 100 ≤ HPI &lt; 150 → Caution, HPI ≥ 150 → Unsafe</div>
                  <img src={vizHpiOverallUrl} alt="HPI Overall Gauge" className="max-w-full h-auto" />
                </div>
              </div>
            )}
            {vizHeiPliUrl && (
              <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>HEI & PLI Monthly Trends</div>
                <div className="p-4 overflow-x-auto"><img src={vizHeiPliUrl} alt="HEI PLI" className="max-w-full h-auto" /></div>
              </div>
            )}
            {vizHqUrl && (
              <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>HQ by Metal</div>
                <div className="p-4 overflow-x-auto"><img src={vizHqUrl} alt="HQ by Metal" className="max-w-full h-auto" /></div>
              </div>
            )}
          </div>
        )}
                

        {/* HPI Combined Plot: metals on X-axis, W×Q on Y-axis */}
        {timeseries && hpiCombined && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                HPI (W×Q) per Metal
              </div>
              <div className="p-4 overflow-x-auto">
                {(() => {
                  const width = Math.max(600, hpiCombined.series.length * 60)
                  const height = 260
                  const padding = { top: 20, right: 20, bottom: 60, left: 50 }
                  const chartW = width - padding.left - padding.right
                  const chartH = height - padding.top - padding.bottom
                  const barWidth = Math.max(24, chartW / (hpiCombined.series.length * 1.6))
                  const scaleY = v => chartH * (v / hpiCombined.maxVal)
                  return (
                    <svg width={width} height={height} role="img" aria-label="HPI contribution by metal">
                      <g transform={`translate(${padding.left},${padding.top})`}>
                        {/* Axes */}
                        <line x1={0} y1={chartH} x2={chartW} y2={chartH} stroke="#e5e7eb" />
                        <line x1={0} y1={0} x2={0} y2={chartH} stroke="#e5e7eb" />
                        {/* Bars */}
                        {hpiCombined.series.map((d, i) => {
                          const x = i * (barWidth * 1.4) + barWidth * 0.2
                          const h = scaleY(Math.max(0, d.value))
                          const y = chartH - h
                          return (
                            <g key={d.metal}>
                              <rect x={x} y={y} width={barWidth} height={h} fill="#0ea5e9" rx={3} />
                              <text x={x + barWidth / 2} y={y - 6} textAnchor="middle" fontSize="10" fill="#374151">
                                {Number.isFinite(d.value) ? d.value.toFixed(2) : '-'}
                              </text>
                              <text transform={`translate(${x + barWidth / 2}, ${chartH + 36}) rotate(45)`} textAnchor="start" fontSize="10" fill="#374151">
                                {d.metal}
                              </text>
                            </g>
                          )
                        })}
                        {/* Y-axis labels */}
                        <text x={-8} y={chartH} textAnchor="end" fontSize="10" fill="#6b7280">0</text>
                        <text x={-8} y={0} textAnchor="end" fontSize="10" fill="#6b7280">{hpiCombined.maxVal.toFixed(2)}</text>
                      </g>
                    </svg>
                  )
                })()}
              </div>
            </div>
          </div>
        )}

        {/* Monthly Statistics Combined Charts */}
        {timeseries && monthlyStats && !monthlyStats.error && monthlyStats.table_data && (
          <div className="mt-8 space-y-8">
            {(() => {
              // Helper to find matching key in table_data
              const findKey = (candidates) => candidates.find(k => monthlyStats.table_data[k])
              const metalsList = monthlyStats.metals || []
              // Mean chart
              const meanKey = findKey(['mean','average','avg'])
              // Std chart
              const stdKey = findKey(['std','standard_deviation','stdev'])
              // Min/Max chart
              const minKey = findKey(['min'])
              const maxKey = findKey(['max'])

              const renderSingleBarChart = (title, dataMap, color = '#10b981') => {
                const series = metalsList.map(m => ({ metal: m, value: parseFloat(dataMap?.[m]) || 0 }))
                const maxVal = Math.max(1, ...series.map(d => (Number.isFinite(d.value) ? d.value : 0)))
                const width = Math.max(600, series.length * 60)
                const height = 260
                const padding = { top: 20, right: 20, bottom: 60, left: 50 }
                const chartW = width - padding.left - padding.right
                const chartH = height - padding.top - padding.bottom
                const barWidth = Math.max(24, chartW / (series.length * 1.6))
                const scaleY = v => chartH * (v / maxVal)
                return (
                  <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                    <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>{title}</div>
                    <div className="p-4 overflow-x-auto">
                      <svg width={width} height={height} role="img" aria-label={title}>
                        <g transform={`translate(${padding.left},${padding.top})`}>
                          <line x1={0} y1={chartH} x2={chartW} y2={chartH} stroke="#e5e7eb" />
                          <line x1={0} y1={0} x2={0} y2={chartH} stroke="#e5e7eb" />
                          {series.map((d, i) => {
                            const x = i * (barWidth * 1.4) + barWidth * 0.2
                            const h = scaleY(Math.max(0, d.value))
                            const y = chartH - h
                            return (
                              <g key={d.metal}>
                                <rect x={x} y={y} width={barWidth} height={h} fill={color} rx={3} />
                                <text x={x + barWidth / 2} y={y - 6} textAnchor="middle" fontSize="10" fill="#374151">{Number.isFinite(d.value) ? d.value.toFixed(2) : '-'}</text>
                                <text transform={`translate(${x + barWidth / 2}, ${chartH + 36}) rotate(45)`} textAnchor="start" fontSize="10" fill="#374151">{d.metal}</text>
                              </g>
                            )
                          })}
                          <text x={-8} y={chartH} textAnchor="end" fontSize="10" fill="#6b7280">0</text>
                          <text x={-8} y={0} textAnchor="end" fontSize="10" fill="#6b7280">{maxVal.toFixed(2)}</text>
                        </g>
                      </svg>
                    </div>
                  </div>
                )
              }

              const renderGroupedMinMaxChart = (title, minMap, maxMap) => {
                const series = metalsList.map(m => ({ metal: m, min: parseFloat(minMap?.[m]) || 0, max: parseFloat(maxMap?.[m]) || 0 }))
                const maxVal = Math.max(1, ...series.flatMap(d => [d.min, d.max]))
                const width = Math.max(600, series.length * 70)
                const height = 280
                const padding = { top: 20, right: 20, bottom: 60, left: 50 }
                const chartW = width - padding.left - padding.right
                const chartH = height - padding.top - padding.bottom
                const groupWidth = Math.max(30, chartW / (series.length * 1.3))
                const barWidth = Math.max(12, groupWidth / 2.6)
                const scaleY = v => chartH * (v / maxVal)
                const colors = { min: '#22c55e', max: '#ef4444' }
                return (
                  <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                    <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>{title}</div>
                    <div className="p-4 overflow-x-auto">
                      <svg width={width} height={height} role="img" aria-label={title}>
                        <g transform={`translate(${padding.left},${padding.top})`}>
                          <line x1={0} y1={chartH} x2={chartW} y2={chartH} stroke="#e5e7eb" />
                          <line x1={0} y1={0} x2={0} y2={chartH} stroke="#e5e7eb" />
                          {series.map((d, i) => {
                            const x0 = i * (groupWidth * 1.2)
                            const minH = scaleY(Math.max(0, d.min))
                            const maxH = scaleY(Math.max(0, d.max))
                            const minY = chartH - minH
                            const maxY = chartH - maxH
                            return (
                              <g key={d.metal}>
                                <rect x={x0 + 4} y={minY} width={barWidth} height={minH} fill={colors.min} rx={3} />
                                <rect x={x0 + 8 + barWidth} y={maxY} width={barWidth} height={maxH} fill={colors.max} rx={3} />
                                <text x={x0 + 4 + barWidth / 2} y={minY - 6} textAnchor="middle" fontSize="10" fill="#374151">{Number.isFinite(d.min) ? d.min.toFixed(2) : '-'}</text>
                                <text x={x0 + 8 + barWidth + barWidth / 2} y={maxY - 6} textAnchor="middle" fontSize="10" fill="#374151">{Number.isFinite(d.max) ? d.max.toFixed(2) : '-'}</text>
                                <text transform={`translate(${x0 + groupWidth / 2}, ${chartH + 36}) rotate(45)`} textAnchor="start" fontSize="10" fill="#374151">{d.metal}</text>
                              </g>
                            )
                          })}
                          <text x={-8} y={chartH} textAnchor="end" fontSize="10" fill="#6b7280">0</text>
                          <text x={-8} y={0} textAnchor="end" fontSize="10" fill="#6b7280">{maxVal.toFixed(2)}</text>
                        </g>
                        {/* Legend */}
                        <g transform={`translate(${padding.left}, ${height - 24})`}>
                          <rect x={0} y={-10} width={12} height={12} fill={colors.min} rx={2} />
                          <text x={18} y={0} fontSize="12" fill="#374151">Min</text>
                          <rect x={60} y={-10} width={12} height={12} fill={colors.max} rx={2} />
                          <text x={78} y={0} fontSize="12" fill="#374151">Max</text>
                        </g>
                      </svg>
                    </div>
                  </div>
                )
              }

              return (
                <>
                  {meanKey && renderSingleBarChart('Monthly Mean per Metal', monthlyStats.table_data[meanKey], '#3b82f6')}
                  {stdKey && renderSingleBarChart('Monthly Standard Deviation per Metal', monthlyStats.table_data[stdKey], '#f59e0b')}
                  {(minKey && maxKey) && renderGroupedMinMaxChart('Monthly Min/Max per Metal', monthlyStats.table_data[minKey], monthlyStats.table_data[maxKey])}
                </>
              )
            })()}
          </div>
        )}

        {/* Pearson Correlation Heatmap (uses backend if available; else client-side) */}
        {(() => {
          const corrToShow = (corrData && corrData.matrix && corrData.metals) ? corrData : (clientCorr && clientCorr.matrix && clientCorr.metals ? clientCorr : null)
          if (!corrToShow) return null
          return (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                Pearson Correlation Matrix {corrToShow.method ? `(${corrToShow.method})` : ''}
              </div>
              {corrLoading && (
                <div className="p-4 text-sm text-gray-700">Loading correlation matrix...</div>
              )}
              {!corrLoading && (
                <div className="overflow-x-auto p-4">
                  {(() => {
                    const features = corrToShow.metals
                    const getColor = (v) => {
                      // map -1..1 to blue(negative) -> white(0) -> red(positive)
                      const val = Math.max(-1, Math.min(1, typeof v === 'number' ? v : 0))
                      if (val >= 0) {
                        const r = 255
                        const g = Math.round(255 * (1 - val))
                        const b = Math.round(255 * (1 - val))
                        return `rgb(${r},${g},${b})`
                      } else {
                        const pos = Math.abs(val)
                        const r = Math.round(255 * (1 - pos))
                        const g = Math.round(255 * (1 - pos))
                        const b = 255
                        return `rgb(${r},${g},${b})`
                      }
                    }
                    return (
                      <table className="text-xs">
                        <thead>
                          <tr>
                            <th className="px-2 py-1"></th>
                            {features.map(f => (
                              <th key={`h-${f}`} className="px-2 py-1 text-right" style={{ color: '#004E92' }}>{f}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {features.map(rowF => (
                            <tr key={`r-${rowF}`}>
                              <td className="px-2 py-1 font-medium" style={{ color: '#004E92' }}>{rowF}</td>
                              {features.map(colF => {
                                const v = (corrToShow.matrix?.[rowF]?.[colF]) ?? 0
                                const color = getColor(v)
                                return (
                                  <td key={`c-${rowF}-${colF}`} className="px-0 py-0">
                                    <div title={`${rowF} vs ${colF}: ${Number.isFinite(v) ? v.toFixed(2) : v}`}
                                         style={{ width: 36, height: 24, backgroundColor: color, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#111827', fontSize: 10 }}>
                                      {Number.isFinite(v) ? v.toFixed(2) : '-'}
                                    </div>
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )
                  })()}
                </div>
              )}
            </div>
          </div>
          )
        })()}
        {!corrLoading && (!corrData || !corrData.matrix || !corrData.metals) && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                Pearson Correlation Matrix
              </div>
              <div className="p-4 text-sm text-gray-700">
                {corrData?.error ? (
                  <span>Correlation unavailable: {corrData.error}</span>
                ) : (
                  <span>Correlation matrix is not available yet. Ensure there are multiple samples with overlapping metals and try again.</span>
                )}
              </div>
            </div>
          </div>
        )}
        {/* Forecast & Hotspot (ML) - moved to end */}
        {data?.id && (
          <div className="mt-8">
            <div className="rounded-lg border" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
              <div className="p-3 text-sm font-semibold" style={{ color: '#004E92' }}>
                Forecast and Hotspot
              </div>
              <div className="p-4 space-y-4">
                <div className="flex flex-wrap items-end gap-3 text-sm">
                  <div>
                    <label className="block mb-1" style={{ color: '#004E92' }}>Target</label>
                    <select className="border rounded px-2 py-1" value={forecastTarget} onChange={e => setForecastTarget(e.target.value)}>
                      {['HPI','HEI','HI','Cd','CDI','MI', ...(timeseries ? Object.keys(timeseries) : [])].map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block mb-1" style={{ color: '#004E92' }}>Model</label>
                    <select className="border rounded px-2 py-1" value={forecastModel} onChange={e => setForecastModel(e.target.value)}>
                      {['auto','linear','poly2','gbr'].map(m => (<option key={m} value={m}>{m}</option>))}
                    </select>
                  </div>
                  <div>
                    <label className="block mb-1" style={{ color: '#004E92' }}>Horizon (months)</label>
                    <input type="number" min={1} max={24} className="border rounded px-2 py-1 w-24" value={forecastHorizon} onChange={e => setForecastHorizon(parseInt(e.target.value || '1', 10))} />
                  </div>
                  <div>
                    <label className="block mb-1" style={{ color: '#004E92' }}>Center Lat</label>
                    <input type="number" step="0.0001" className="border rounded px-2 py-1 w-36" placeholder={data?.latitude ? String(data.latitude) : 'e.g., 17.9886'} value={centerLat} onChange={e => setCenterLat(e.target.value)} />
                  </div>
                  <div>
                    <label className="block mb-1" style={{ color: '#004E92' }}>Center Lon</label>
                    <input type="number" step="0.0001" className="border rounded px-2 py-1 w-36" placeholder={data?.longitude ? String(data.longitude) : 'e.g., 73.6381'} value={centerLon} onChange={e => setCenterLon(e.target.value)} />
                  </div>
                  <div>
                    <label className="block mb-1" style={{ color: '#004E92' }}>Radius (km)</label>
                    <input type="number" min={1} max={200} className="border rounded px-2 py-1 w-28" placeholder="25" value={radiusKm} onChange={e => setRadiusKm(e.target.value)} />
                  </div>
                  <label className="inline-flex items-center gap-2 mb-1" style={{ color: '#004E92' }}>
                    <input type="checkbox" checked={useForecastHotspot} onChange={e => setUseForecastHotspot(e.target.checked)} />
                    <span>Use Forecast for Hotspot</span>
                  </label>
                  <label className="inline-flex items-center gap-2 mb-1" style={{ color: '#004E92' }}>
                    <input type="checkbox" checked={heatmapOn} onChange={e => setHeatmapOn(e.target.checked)} />
                    <span>Heatmap Overlay</span>
                  </label>
                  <button
                    className="px-3 py-1.5 rounded text-white"
                    style={{ backgroundColor: '#2563eb' }}
                    onClick={async () => {
                      if (!data?.id) return
                      try {
                        setForecastLoading(true)
                        setForecastData(null)
                        const url = `${API_BASE}/api/ml/forecast?sample_id=${data.id}&target=${encodeURIComponent(forecastTarget)}&horizon=${forecastHorizon}&model=${forecastModel}`
                        const resp = await fetch(url)
                        const json = await resp.json()
                        setForecastData(json)
                      } catch (e) {
                        setForecastData({ error: 'Unable to run forecast' })
                      } finally {
                        setForecastLoading(false)
                      }
                    }}
                  >
                    Run Forecast
                  </button>
                  <button
                    className="px-3 py-1.5 rounded text-white"
                    style={{ backgroundColor: '#059669' }}
                    onClick={async () => {
                      try {
                        setHotspotLoading(true)
                        setHotspotInfo(null)
                        const params = new URLSearchParams({
                          target: forecastTarget,
                          use_forecast: useForecastHotspot ? 'true' : 'false',
                          horizon: String(forecastHorizon),
                          country: 'india',
                          heatmap: heatmapOn ? 'true' : 'false',
                        })
                        const latVal = centerLat || (data?.latitude ? String(data.latitude) : '')
                        const lonVal = centerLon || (data?.longitude ? String(data.longitude) : '')
                        const radVal = radiusKm || ''
                        if (latVal && lonVal && radVal) {
                          params.set('center_lat', latVal)
                          params.set('center_lon', lonVal)
                          params.set('radius_km', radVal)
                        }
                        const url = `${API_BASE}/api/ml/hotspot?${params.toString()}`
                        const resp = await fetch(url)
                        const json = await resp.json()
                        setHotspotInfo(json)
                      } catch (e) {
                        setHotspotInfo({ error: 'Unable to generate hotspot map' })
                      } finally {
                        setHotspotLoading(false)
                      }
                    }}
                  >
                    Generate Hotspot ({useForecastHotspot ? 'Forecast' : 'Current'})
                  </button>
                </div>

                {/* Forecast visualization */}
                {forecastLoading && (
                  <div className="text-sm text-gray-700">Running forecast…</div>
                )}
                {!forecastLoading && forecastData && !forecastData.error && (
                  <div className="rounded border p-3" style={{ borderColor: '#E5E7EB' }}>
                    <div className="text-sm font-semibold mb-2" style={{ color: '#004E92' }}>
                      {`Forecast ${forecastData.target} (model: ${forecastData.model})`}
                    </div>
                    {(() => {
                      const hist = forecastData.history || { periods: [], values: [] }
                      const fc = forecastData.forecast || { periods: [], values: [] }
                      const ciL = forecastData.ci_low || []
                      const ciH = forecastData.ci_high || []
                      const xAll = [...hist.periods, ...fc.periods]
                      const yAll = [...hist.values, ...fc.values]
                      const maxY = Math.max(1, ...yAll.filter(v => Number.isFinite(v)))
                      const width = Math.max(600, xAll.length * 48)
                      const height = 260
                      const padding = { top: 20, right: 20, bottom: 60, left: 50 }
                      const chartW = width - padding.left - padding.right
                      const chartH = height - padding.top - padding.bottom
                      const scaleX = (i) => chartW * (i / Math.max(1, xAll.length - 1))
                      const scaleY = (v) => chartH * (1 - (v / maxY))
                      const xsHist = hist.values.map((_, i) => scaleX(i))
                      const xsFc = fc.values.map((_, i) => scaleX(hist.values.length + i))
                      const pathLine = (xs, ys) => ys.reduce((acc, v, i) => {
                        const y = Number.isFinite(v) ? scaleY(v) : scaleY(0)
                        const x = xs[i]
                        return acc + `${i===0?'M':' L'}${x.toFixed(2)},${y.toFixed(2)}`
                      }, '')
                      const histPath = pathLine(xsHist, hist.values)
                      const fcPath = pathLine(xsFc, fc.values)
                      // CI area as polygon
                      const ciXs = xsFc
                      const ciTop = ciH.map((v, i) => `${ciXs[i].toFixed(2)},${scaleY(Number.isFinite(v)?v:0).toFixed(2)}`)
                      const ciBot = ciL.map((v, i) => `${ciXs[ciXs.length-1-i].toFixed(2)},${scaleY(Number.isFinite(v)?v:0).toFixed(2)}`)
                      return (
                        <div className="overflow-x-auto">
                          <svg width={width} height={height} role="img" aria-label={`Forecast ${forecastData.target}`}>
                            <g transform={`translate(${padding.left},${padding.top})`}>
                              <line x1={0} y1={chartH} x2={chartW} y2={chartH} stroke="#e5e7eb" />
                              <line x1={0} y1={0} x2={0} y2={chartH} stroke="#e5e7eb" />
                              {/* CI area */}
                              {ciTop.length && ciBot.length ? (
                                <path d={`M${ciTop[0]} L${ciTop.slice(1).join(' L')} L${ciBot.join(' L')} Z`} fill="#fecaca" opacity="0.5" />
                              ) : null}
                              {/* History */}
                              <path d={histPath} fill="none" stroke="#0ea5e9" strokeWidth="2" />
                              {/* Forecast */}
                              <path d={fcPath} fill="none" stroke="#ef4444" strokeWidth="2" strokeDasharray="4,4" />
                              {/* X labels */}
                              {xAll.map((lbl, i) => (
                                <text key={`x-${i}`} x={scaleX(i)} y={chartH + 36} transform={`rotate(45, ${scaleX(i)}, ${chartH + 36})`} textAnchor="start" fontSize="10" fill="#374151">{lbl}</text>
                              ))}
                              {/* Y labels */}
                              <text x={-8} y={chartH} textAnchor="end" fontSize="10" fill="#6b7280">0</text>
                              <text x={-8} y={0} textAnchor="end" fontSize="10" fill="#6b7280">{maxY.toFixed(2)}</text>
                            </g>
                          </svg>
                        </div>
                      )
                    })()}
                  </div>
                )}
                {!forecastLoading && forecastData && forecastData.error && (
                  <div className="text-sm text-red-600">{forecastData.error}</div>
                )}

                {/* Hotspot result */}
                {hotspotLoading && (
                  <div className="text-sm text-gray-700">Generating hotspot map…</div>
                )}
                {!hotspotLoading && hotspotInfo && (
                  <div className="text-sm">
                    {hotspotInfo.error ? (
                      <div className="text-red-600">{hotspotInfo.error}</div>
                    ) : (
                      <div className="space-y-1">
                        <div className="text-gray-700">Hotspot generated for {hotspotInfo.target} ({hotspotInfo.mode}). Points: {hotspotInfo.points?.length || 0}</div>
                        {hotspotInfo.map_path && (
                          <div>
                            <span className="text-gray-700">Saved map path (server): </span>
                            <code className="text-gray-800">{hotspotInfo.map_path}</code>
                          </div>
                        )}
                        {hotspotInfo.image_url && (
                          <div className="mt-2">
                            <div className="text-gray-700 mb-1">Preview:</div>
                            <div className="border rounded p-2 inline-block" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF' }}>
                              <img src={`${API_BASE}${hotspotInfo.image_url}`} alt="Local hotspot" style={{ maxWidth: '640px', height: 'auto' }} />
                            </div>
                            {hotspotInfo.map_url && (
                              <div className="mt-2">
                                <a className="text-blue-600 underline" href={`${API_BASE}${hotspotInfo.map_url}`} target="_blank" rel="noreferrer">Open interactive map</a>
                              </div>
                            )}
                          </div>
                        )}
                        {!hotspotInfo.image_url && hotspotInfo.map_url && (
                          <div className="mt-2">
                            <div className="text-gray-700 mb-1">Interactive Map (iframe):</div>
                            <div className="border rounded overflow-hidden" style={{ borderColor: '#E5E7EB', backgroundColor: '#FFFFFF', width: '100%', maxWidth: 700, height: 420 }}>
                              <iframe title="Hotspot Map" src={`${API_BASE}${hotspotInfo.map_url}`} style={{ width: '100%', height: '100%', border: '0' }} />
                            </div>
                            <div className="mt-2">
                              <a className="text-blue-600 underline" href={`${API_BASE}${hotspotInfo.map_url}`} target="_blank" rel="noreferrer">Open map in new tab</a>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


