import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'


const MAX_SIZE_BYTES = 50 * 1024 * 1024
const API_BASE = import.meta?.env?.VITE_API_URL || 'http://localhost:8000'
const ACCEPTED_TYPES = [
  'text/csv',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/pdf',
]

function FileUploadBox({ onComplete }) {
  const navigate = useNavigate()
  const [fileInfo, setFileInfo] = useState(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')
  const [serverData, setServerData] = useState(null)
  const [isExtracting, setIsExtracting] = useState(false)
  const [uploadedSampleId, setUploadedSampleId] = useState(null)
  const inputRef = useRef(null)

  const onSelectClick = useCallback(() => {
    inputRef.current?.click()
  }, [])

  const validateFile = (file) => {
    if (!file) return 'No file selected.'
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return 'Unsupported format. Use CSV, Excel, or PDF.'
    }
    if (file.size > MAX_SIZE_BYTES) {
      return 'File too large. Max 50MB.'
    }
    return ''
  }

  const handleFiles = useCallback((files) => {
    const file = files?.[0]
    const err = validateFile(file)
    if (err) {
      setError(err)
      setFileInfo(null)
      return
    }
    setError('')
    setServerData(null)
    setIsExtracting(false)
    setUploadedSampleId(null)
    setFileInfo({
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      status: 'Ready',
    })
  }, [])

  const onInputChange = useCallback((e) => handleFiles(e.target.files), [handleFiles])

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      e.stopPropagation()
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles]
  )

  const onDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  const removeFile = () => {
    setFileInfo(null)
    setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleUpload = async () => {
    if (!fileInfo || isUploading) return
    setError('')
    setIsUploading(true)
    setFileInfo((prev) => (prev ? { ...prev, status: 'Uploading…' } : prev))
    try {
      const form = new FormData()
      form.append('file', fileInfo.file, fileInfo.name)
      const resp = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: form,
      })
      if (!resp.ok) {
        const txt = await resp.text()
        throw new Error(txt || 'Upload failed')
      }
      const data = await resp.json()
      setUploadedSampleId(data?.id || null)
      setServerData(data)
      if (typeof onComplete === 'function') onComplete(data)
      setFileInfo((prev) => (prev ? { ...prev, status: 'Uploaded' } : prev))
      setIsExtracting(false)
      // Navigate to results route with data
      navigate('/results', { state: { data } })
    } catch (e) {
      setError(typeof e?.message === 'string' ? e.message : 'Upload failed')
      setFileInfo((prev) => (prev ? { ...prev, status: 'Error' } : prev))
    } finally {
      setIsUploading(false)
    }
  }

  // Instant display: no polling
  useEffect(() => { /* no-op */ }, [])

  return (
    <section className="bg-gray-50">
      <div className="max-w-[1200px] mx-auto px-4 pb-10">
        <div className="mb-3">
          <h3 className="text-lg md:text-xl font-semibold" style={{ color: '#004E92' }}>
            Upload Your Lab Results
          </h3>
          <p className="text-xs md:text-sm text-gray-700">
            Supported formats: CSV, Excel, PDF | Max size: 50MB
          </p>
        </div>

        <div
          onDrop={onDrop}
          onDragOver={onDragOver}
          className="bg-white border-2 border-blue-400 border-dashed hover:border-blue-600 transition-colors rounded-lg shadow-md flex flex-col items-center justify-center text-center px-6 py-10 md:py-12"
          role="region"
          aria-label="Drag and drop file upload area"
        >
          <div className="mb-3" aria-hidden="true">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#004E92" className="w-10 h-10 md:w-12 md:h-12">
              <path d="M7 20a5 5 0 1 1 0-10 6 6 0 1 1 11.31 3.33A4.5 4.5 0 1 1 18.5 20H7zm4-7.5V17a1 1 0 1 0 2 0v-4.5l1.293 1.293a1 1 0 0 0 1.414-1.414l-3-3a1 1 0 0 0-1.414 0l-3 3a1 1 0 0 0 1.414 1.414L11 12.5z" />
            </svg>
          </div>

          <p className="text-sm md:text-base text-gray-800">Drag & drop files here</p>
          <p className="text-xs text-gray-600 mb-4">or</p>

          <div className="flex items-center gap-3">
            <button
              onClick={onSelectClick}
              type="button"
              className="px-4 py-2 rounded-md text-white font-medium"
              style={{ backgroundColor: '#004E92' }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#00AEEF')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#004E92')}
            >
              Select File
            </button>
            <button
              onClick={handleUpload}
              type="button"
              disabled={!fileInfo || isUploading}
              className={`px-4 py-2 rounded-md text-white font-medium ${!fileInfo || isUploading ? 'opacity-60 cursor-not-allowed' : ''}`}
              style={{ backgroundColor: '#004E92' }}
              onMouseEnter={(e) => {
                if (!fileInfo || isUploading) return
                e.currentTarget.style.backgroundColor = '#00AEEF'
              }}
              onMouseLeave={(e) => {
                if (!fileInfo || isUploading) return
                e.currentTarget.style.backgroundColor = '#004E92'
              }}
            >
              {isUploading ? 'Uploading…' : 'Upload'}
            </button>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept=".csv, application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/pdf"
            onChange={onInputChange}
            className="sr-only"
            aria-hidden="true"
          />

          {fileInfo && (
            <div className="mt-5 w-full max-w-md mx-auto text-left">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm md:text-base font-medium text-gray-900">{fileInfo.name}</p>
                  <p className="text-xs text-gray-600">{(fileInfo.size / (1024 * 1024)).toFixed(2)} MB • {fileInfo.type}</p>
                </div>
                <span className="text-xs font-semibold" style={{ color: '#004E92' }}>{fileInfo.status}</span>
              </div>
              <div className="mt-2">
                <button
                  type="button"
                  onClick={removeFile}
                  className="text-xs md:text-sm text-red-600 hover:underline"
                >
                  Remove and re-upload
                </button>
              </div>
              {isExtracting && (
                <div className="mt-3 text-sm text-gray-700">
                  Extracting values… this may take a few seconds.
                </div>
              )}
              {/* Results now open on separate route */}
            </div>
          )}

          {error && (
            <div className="mt-4 text-sm text-red-600" role="alert">
              {error}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

export default FileUploadBox
 