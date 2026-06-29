import React, { useState } from 'react'
import { Copy, Check, File, Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import FormCard from './FormCard'
import '../styles/MessageBubble.css'

function MessageBubble({ message, onFormSubmit, onFormCancel }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(message.text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const formatTime = (date) => {
    return new Date(date).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    })
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  return (
    <div className={`message-bubble message-${message.sender} ${message.isError ? 'message-error' : ''}`}>
      <div className="message-content">
        {message.form ? (
          <FormCard
            form={message.form}
            onSubmit={(values) => onFormSubmit && onFormSubmit(values)}
            onCancel={() => onFormCancel && onFormCancel()}
          />
        ) : (
        <div className="message-text markdown-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({node, ...props}) => <p {...props} style={{margin: '0.1em 0'}} />,
              code: ({node, inline, ...props}) => 
                inline ? 
                  <code {...props} style={{backgroundColor: '#f5f5f5', padding: '2px 4px', borderRadius: '2px', fontFamily: 'monospace', fontSize: '0.9em'}} /> : 
                  <code {...props} />,
              pre: ({node, ...props}) => <pre {...props} style={{backgroundColor: '#f5f5f5', padding: '8px', borderRadius: '4px', overflow: 'auto', fontSize: '0.85em', margin: '6px 0'}} />,
              blockquote: ({node, ...props}) => <blockquote {...props} style={{borderLeft: '3px solid #ddd', paddingLeft: '8px', margin: '6px 0', color: '#666', fontStyle: 'italic'}} />,
              table: ({node, ...props}) => <table {...props} style={{borderCollapse: 'collapse', width: '100%', margin: '6px 0'}} />,
              th: ({node, ...props}) => <th {...props} style={{border: '1px solid #ddd', padding: '6px', textAlign: 'left', backgroundColor: '#f5f5f5', fontWeight: 'bold'}} />,
              td: ({node, ...props}) => <td {...props} style={{border: '1px solid #ddd', padding: '6px'}} />,
              a: ({node, ...props}) => <a {...props} style={{color: '#667eea', textDecoration: 'underline'}} target="_blank" rel="noopener noreferrer" />,
              ul: ({node, ...props}) => <ul {...props} style={{marginLeft: '18px', marginTop: '2px', marginBottom: '2px', paddingLeft: '0'}} />,
              ol: ({node, ...props}) => <ol {...props} style={{marginLeft: '18px', marginTop: '2px', marginBottom: '2px', paddingLeft: '0'}} />,
              li: ({node, ...props}) => <li {...props} style={{margin: '2px 0'}} />,
              h1: ({node, ...props}) => <h1 {...props} style={{fontSize: '1.4em', fontWeight: 'bold', margin: '6px 0 4px 0'}} />,
              h2: ({node, ...props}) => <h2 {...props} style={{fontSize: '1.2em', fontWeight: 'bold', margin: '5px 0 3px 0'}} />,
              h3: ({node, ...props}) => <h3 {...props} style={{fontSize: '1.05em', fontWeight: 'bold', margin: '4px 0 2px 0'}} />,
              hr: ({node, ...props}) => <hr {...props} style={{margin: '6px 0', border: 'none', borderTop: '1px solid #ddd'}} />,
            }}
          >
            {message.text}
          </ReactMarkdown>
        </div>
        )}
        {message.files && message.files.length > 0 && (
          <div className="message-files">
            <div className="files-label">Attached files</div>
            {message.files.map((file, index) => (
              <div key={index} className="file-attachment">
                <File size={14} className="file-icon" />
                <div className="file-info">
                  <span className="file-name" title={file.name}>{file.name}</span>
                  <span className="file-size">{formatFileSize(file.size)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
        <span className="message-time">{formatTime(message.timestamp)}</span>
      </div>
      {(message.sender === 'bot' || message.sender === 'user') && !message.isError && (
        <button 
          className="copy-button"
          onClick={handleCopy}
          title="Copy message"
          aria-label="Copy message"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      )}
    </div>
  )
}

export default MessageBubble