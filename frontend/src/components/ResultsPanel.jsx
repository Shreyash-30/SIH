import React from 'react'

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

  const exceeded = Object.entries(assessments).filter(([, a]) => (a?.exceeds === 1 || a?.exceeds === '1'))
  const exceededList = exceeded.map(([m]) => m).join(', ')

  return (
    <div className="mt-6">
      <div className="rounded-lg border" style={{ borderColor: palette.border, backgroundColor: bg }}>
        <div className="p-4 flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span style={{ color: fg }}><StatusIcon category={category} /></span>
            <div>
              <div className="text-xs font-semibold tracking-wide" style={{ color: fg }}>[ STATUS: {label} ]</div>
              <div className="text-sm mt-1" style={{ color: palette.govBlue }}>
                HPI: {hpi?.toFixed ? hpi.toFixed(2) : hpi} | HEI: {hei?.toFixed ? hei.toFixed(2) : hei} | PLI: {pli?.toFixed ? pli.toFixed(3) : pli}
              </div>
              {exceeded.length > 0 && (
                <div className="text-xs mt-1" style={{ color: fg }}>Reason: {exceeded.length} parameter{exceeded.length > 1 ? 's' : ''} exceed limit ({exceededList})</div>
              )}
            </div>
          </div>
          <div className="shrink-0">
            <Gauge value={hpi} />
          </div>
        </div>
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
    </div>
  )
}


