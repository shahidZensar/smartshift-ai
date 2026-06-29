import React, { useState, useRef, useEffect } from 'react'
import { Send, Upload, X, File } from 'lucide-react'
import '../styles/InputArea.css'

function InputArea({ onSendMessage, isLoading, onFileUpload }) {
  const [input, setInput] = useState('')
  const [uploadedFiles, setUploadedFiles] = useState([])
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [input])

  const handleSubmit = (e) => {
    e.preventDefault()
    if ((input.trim() || uploadedFiles.length > 0) && !isLoading) {
      onSendMessage(input, uploadedFiles)
      setInput('')
      setUploadedFiles([])
    }
  }

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || [])
    const newFiles = files.map(file => ({
      name: file.name,
      size: file.size,
      type: file.type,
      file: file
    }))
    setUploadedFiles(prev => [...prev, ...newFiles])
  }

  const removeFile = (index) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="input-area">
      {uploadedFiles.length > 0 && (
        <div className="uploaded-files">
          <div className="files-header">
            <span className="files-title">Attached files ({uploadedFiles.length})</span>
          </div>
          <div className="files-list">
            {uploadedFiles.map((file, index) => (
              <div key={index} className="file-item">
                <div className="file-info">
                  <File size={16} className="file-icon" />
                  <div className="file-details">
                    <span className="file-name" title={file.name}>{file.name}</span>
                    <span className="file-size">{formatFileSize(file.size)}</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="remove-file-btn"
                  onClick={() => removeFile(index)}
                  title="Remove file"
                  aria-label={`Remove ${file.name}`}
                >
                  <X size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      <form onSubmit={handleSubmit} className="input-form">
        <div className="input-controls">
          <textarea
            ref={textareaRef}
            className="message-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about device migration, compatibility, or suggestions... (Shift+Enter for new line)"
            disabled={isLoading}
            rows={1}
            aria-label="Message input"
          />
          <div className="button-group">
            <button
              type="button"
              className="file-upload-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
              title="Attach file"
              aria-label="Attach file"
            >
              <Upload size={20} />
            </button>
            <button 
              type="submit" 
              className="send-button"
              disabled={isLoading || (input.trim().length === 0 && uploadedFiles.length === 0)}
              title="Send message (Enter)"
              aria-label="Send message"
            >
              <Send size={20} />
            </button>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          className="file-input-hidden"
          aria-label="File upload"
        />
      </form>
      <p className="input-hint">Powered by RAG Engine with Llama 3.2</p>
    </div>
  )
}

export default InputArea