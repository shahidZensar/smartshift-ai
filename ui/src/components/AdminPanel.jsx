import React, { useState, useEffect } from 'react'
import { Upload, Link as LinkIcon, RefreshCw, Trash2, Eye, EyeOff, Download, Database } from 'lucide-react'
import '../styles/AdminPanel.css'

function AdminPanel({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('upload')
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [stats, setStats] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  
  // Form states
  const [selectedFile, setSelectedFile] = useState(null)
  const [urlInput, setUrlInput] = useState('')
  const [autoIndex, setAutoIndex] = useState(true)
  
  // CSV Import states
  const [csvFile, setCsvFile] = useState(null)
  const [tableName, setTableName] = useState('')
  const [mysqlTables, setMysqlTables] = useState([])
  const [selectedTable, setSelectedTable] = useState('')

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  // Load files and stats on mount and when tab changes
  useEffect(() => {
    if (isOpen) {
      loadFiles()
      loadStats()
    }
  }, [isOpen, activeTab])

  // Handle escape key to close panel
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    
    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen, onClose])

  const loadFiles = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/uploaded-files`)
      if (!response.ok) throw new Error('Failed to load files')
      
      const data = await response.json()
      setFiles(data.files || [])
      setError(null)
    } catch (err) {
      setError(`Error loading files: ${err.message}`)
      console.error(err)
    }
  }

  const loadStats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/vector-db-stats`)
      if (!response.ok) throw new Error('Failed to load stats')
      
      const data = await response.json()
      setStats(data.vector_database)
      setError(null)
    } catch (err) {
      setError(`Error loading stats: ${err.message}`)
      console.error(err)
    }
  }

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      const maxSize = 50 * 1024 * 1024 // 50 MB
      if (file.size > maxSize) {
        setError(`File too large. Maximum size: 50 MB`)
        return
      }
      setSelectedFile(file)
      setError(null)
    }
  }

  const uploadFile = async () => {
    if (!selectedFile) {
      setError('Please select a file')
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('auto_index', autoIndex)

      const response = await fetch(`${API_URL}/api/admin/upload-file`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Upload failed')
      }

      const data = await response.json()
      setSuccess(`File uploaded successfully! ${autoIndex ? `Added ${data.file.chunks_added} chunks to vector database.` : ''}`)
      setSelectedFile(null)
      setUploadProgress(0)
      
      // Reload files
      setTimeout(() => {
        loadFiles()
        loadStats()
      }, 500)
    } catch (err) {
      setError(`Upload error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const uploadUrl = async () => {
    if (!urlInput.trim()) {
      setError('Please enter a URL')
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('url', urlInput)
      formData.append('auto_index', autoIndex)

      const response = await fetch(`${API_URL}/api/admin/upload-url`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'URL processing failed')
      }

      const data = await response.json()
      setSuccess(`URL processed successfully! Added ${data.chunks_added} chunks to vector database.`)
      setUrlInput('')
      
      // Reload files
      setTimeout(() => {
        loadFiles()
        loadStats()
      }, 500)
    } catch (err) {
      setError(`URL error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const deleteFile = async (filename) => {
    if (!window.confirm(`Delete file: ${filename}?`)) return

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_URL}/api/admin/uploaded-files/${filename}`, {
        method: 'DELETE'
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Delete failed')
      }

      setSuccess(`File deleted: ${filename}`)
      loadFiles()
    } catch (err) {
      setError(`Delete error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const refreshIndex = async (reindexAll = false) => {
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('reindex_all', reindexAll)

      const response = await fetch(`${API_URL}/api/admin/refresh-index`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Refresh failed')
      }

      const data = await response.json()
      setSuccess(`Index refreshed! Added ${data.total_chunks} chunks from ${data.files_indexed} files.`)
      loadStats()
    } catch (err) {
      setError(`Refresh error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const loadMysqlTables = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/mysql-tables`)
      if (!response.ok) throw new Error('Failed to load tables')
      
      const data = await response.json()
      setMysqlTables(data.tables || [])
      setError(null)
    } catch (err) {
      setError(`Error loading tables: ${err.message}`)
      console.error(err)
    }
  }

  const handleCsvFileSelect = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      const maxSize = 50 * 1024 * 1024 // 50 MB
      if (file.size > maxSize) {
        setError(`File too large. Maximum size: 50 MB`)
        return
      }
      if (!['.csv', '.xlsx', '.xls'].some(ext => file.name.endsWith(ext))) {
        setError('Only CSV and Excel files are supported')
        return
      }
      setCsvFile(file)
      setError(null)
    }
  }

  const importCsvToMysql = async () => {
    if (!csvFile) {
      setError('Please select a CSV/Excel file')
      return
    }
    
    const table = tableName.trim() || selectedTable
    if (!table) {
      setError('Please enter a table name or select an existing table')
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('file', csvFile)
      formData.append('table_name', table)

      const response = await fetch(`${API_URL}/api/admin/import-csv-to-mysql`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Import failed')
      }

      const data = await response.json()
      setSuccess(`Successfully imported ${data.import.rows_imported} rows to table '${table}'`)
      setCsvFile(null)
      setTableName('')
      setSelectedTable('')
      loadMysqlTables()
    } catch (err) {
      setError(`Import error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (!isOpen) return null

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  return (
    <div className="admin-panel-overlay" onClick={handleOverlayClick}>
      <div className="admin-panel">
        <div className="admin-header">
          <h2>Admin Panel - Vector Database Management</h2>
          <button 
            type="button" 
            className="close-btn" 
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onClose()
            }}
          >
            ✕
          </button>
        </div>

        {/* Alert Messages */}
        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        {/* Tabs */}
        <div className="admin-tabs">
          <button 
            className={`tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            <Upload size={18} />
            Upload Files
          </button>
          <button 
            className={`tab-btn ${activeTab === 'url' ? 'active' : ''}`}
            onClick={() => setActiveTab('url')}
          >
            <LinkIcon size={18} />
            Add URL
          </button>
          <button 
            className={`tab-btn ${activeTab === 'files' ? 'active' : ''}`}
            onClick={() => setActiveTab('files')}
          >
            <Eye size={18} />
            Manage Files
          </button>
          <button 
            className={`tab-btn ${activeTab === 'stats' ? 'active' : ''}`}
            onClick={() => setActiveTab('stats')}
          >
            <RefreshCw size={18} />
            Database
          </button>
          <button 
            className={`tab-btn ${activeTab === 'csv-import' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('csv-import')
              loadMysqlTables()
            }}
          >
            <Database size={18} />
            Import Data
          </button>
        </div>

        {/* Tab Content */}
        <div className="admin-content">
          {/* Upload Files Tab */}
          {activeTab === 'upload' && (
            <div className="tab-content">
              <h3>Upload Files to Vector Database</h3>
              <p className="info-text">Supported formats: PDF, TXT, DOCX, MD, CSV (Max 50 MB)</p>
              
              <div className="file-upload-section">
                <label className="file-input-label">
                  <input
                    type="file"
                    onChange={handleFileSelect}
                    accept=".pdf,.txt,.docx,.md,.csv"
                    disabled={loading}
                  />
                  <span className="file-input-btn">
                    <Upload size={20} />
                    Choose File
                  </span>
                </label>
                
                {selectedFile && (
                  <div className="file-preview">
                    <span>Selected: {selectedFile.name}</span>
                    <span className="file-size">({formatFileSize(selectedFile.size)})</span>
                  </div>
                )}
              </div>

              <div className="option-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={autoIndex}
                    onChange={(e) => setAutoIndex(e.target.checked)}
                    disabled={loading}
                  />
                  <span>Auto-index to vector database</span>
                </label>
              </div>

              {uploadProgress > 0 && uploadProgress < 100 && (
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${uploadProgress}%` }}>
                    {uploadProgress}%
                  </div>
                </div>
              )}

              <button 
                className="btn btn-primary"
                onClick={uploadFile}
                disabled={!selectedFile || loading}
              >
                {loading ? 'Uploading...' : 'Upload File'}
              </button>
            </div>
          )}

          {/* Add URL Tab */}
          {activeTab === 'url' && (
            <div className="tab-content">
              <h3>Add Content from URL</h3>
              <p className="info-text">Enter a URL to fetch and index web content</p>
              
              <div className="url-input-section">
                <input
                  type="url"
                  placeholder="https://example.com/page"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  disabled={loading}
                  className="url-input"
                />
              </div>

              <div className="option-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={autoIndex}
                    onChange={(e) => setAutoIndex(e.target.checked)}
                    disabled={loading}
                  />
                  <span>Auto-index to vector database</span>
                </label>
              </div>

              <button 
                className="btn btn-primary"
                onClick={uploadUrl}
                disabled={!urlInput.trim() || loading}
              >
                {loading ? 'Processing...' : 'Fetch & Index'}
              </button>
            </div>
          )}

          {/* Manage Files Tab */}
          {activeTab === 'files' && (
            <div className="tab-content">
              <h3>Uploaded Files ({files.length})</h3>
              
              {files.length === 0 ? (
                <p className="no-files">No files uploaded yet</p>
              ) : (
                <div className="files-list">
                  {files.map((file, idx) => (
                    <div key={idx} className="file-item">
                      <div className="file-info">
                        <div className="file-name">{file.filename}</div>
                        <div className="file-meta">
                          <span>{formatFileSize(file.size)}</span>
                          <span>•</span>
                          <span>{formatDate(file.uploaded_at)}</span>
                        </div>
                      </div>
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() => deleteFile(file.filename)}
                        disabled={loading}
                        title="Delete file"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="action-group">
                <button 
                  className="btn btn-secondary"
                  onClick={() => refreshIndex(false)}
                  disabled={loading || files.length === 0}
                  title="Reindex only new files"
                >
                  <RefreshCw size={18} />
                  Refresh Index
                </button>
                <button 
                  className="btn btn-secondary btn-danger"
                  onClick={() => refreshIndex(true)}
                  disabled={loading || files.length === 0}
                  title="Clear and rebuild entire index"
                >
                  <RefreshCw size={18} />
                  Reindex All
                </button>
              </div>
            </div>
          )}

          {/* Database Stats Tab */}
          {activeTab === 'stats' && (
            <div className="tab-content">
              <h3>Vector Database Statistics</h3>
              
              {stats ? (
                <div className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-label">Uploaded Files</div>
                    <div className="stat-value">{stats.uploaded_files}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Total Size</div>
                    <div className="stat-value">{stats.total_size_formatted}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Storage Path</div>
                    <div className="stat-path">{stats.upload_directory}</div>
                  </div>
                </div>
              ) : (
                <p>Loading statistics...</p>
              )}

              <div className="action-group">
                <button 
                  className="btn btn-primary"
                  onClick={() => {
                    loadStats()
                    loadFiles()
                  }}
                  disabled={loading}
                >
                  <RefreshCw size={18} />
                  Refresh Stats
                </button>
              </div>
            </div>
          )}

          {/* CSV Import Tab */}
          {activeTab === 'csv-import' && (
            <div className="tab-content">
              <h3>Import Structured Data to MySQL</h3>
              <p className="info-text">Upload CSV or Excel files to import data into MySQL database</p>
              
              <div className="csv-import-section">
                <div className="form-group">
                  <label>Select CSV/Excel File</label>
                  <label className="file-input-label">
                    <input
                      type="file"
                      onChange={handleCsvFileSelect}
                      accept=".csv,.xlsx,.xls"
                      disabled={loading}
                    />
                    <span className="file-input-btn">
                      <Upload size={20} />
                      Choose File
                    </span>
                  </label>
                  
                  {csvFile && (
                    <div className="file-preview">
                      <span>Selected: {csvFile.name}</span>
                      <span className="file-size">({formatFileSize(csvFile.size)})</span>
                    </div>
                  )}
                </div>

                <div className="form-group">
                  <label>Target Table Name</label>
                  <p className="info-text small">Create new table or select existing one</p>
                  
                  <div className="table-options">
                    <input
                      type="text"
                      placeholder="Enter new table name (or use selection below)"
                      value={tableName}
                      onChange={(e) => {
                        setTableName(e.target.value)
                        setSelectedTable('')
                      }}
                      disabled={loading}
                      className="table-input"
                    />
                    
                    <select
                      value={selectedTable}
                      onChange={(e) => {
                        setSelectedTable(e.target.value)
                        setTableName('')
                      }}
                      disabled={loading}
                      className="table-select"
                    >
                      <option value="">-- Or select existing table --</option>
                      {mysqlTables.map(table => (
                        <option key={table} value={table}>{table}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <button 
                  className="btn btn-primary"
                  onClick={importCsvToMysql}
                  disabled={loading || !csvFile}
                >
                  <Database size={18} />
                  {loading ? 'Importing...' : 'Import to MySQL'}
                </button>
              </div>

              <div className="info-box">
                <h4>Import Information</h4>
                <ul>
                  <li>✓ Supported formats: CSV, XLSX, XLS</li>
                  <li>✓ Maximum file size: 50 MB</li>
                  <li>✓ Column names will be normalized (lowercase, spaces to underscores)</li>
                  <li>✓ Data will be appended to existing tables or create new one</li>
                  <li>✓ Null values will be properly handled</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="admin-footer">
          <p>Vector Database Management | Files are automatically chunked and indexed</p>
        </div>
      </div>
    </div>
  )
}

export default AdminPanel
