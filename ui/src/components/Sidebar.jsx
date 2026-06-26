import React from 'react'
import { Menu, Plus, Trash2, Settings, HelpCircle, Lock } from 'lucide-react'
import '../styles/Sidebar.css'

function Sidebar({ isOpen, onToggle, onNewChat, onClearChat, onOpenAdmin, provider = 'azure', onProviderChange }) {
  return (
    <>
      <button 
        className={`menu-toggle ${!isOpen ? 'show' : ''}`}
        onClick={onToggle} 
        title="Toggle sidebar"
        aria-label="Toggle sidebar"
      >
        <Menu size={18} />
      </button>
      
      <div className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <h1 className="sidebar-title">Device Migration Chat</h1>
          <button 
            type="button"
            className="close-button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onToggle()
            }}
            title="Close sidebar"
            aria-label="Close sidebar"
          >
            ✕
          </button>
        </div>

        <div className="sidebar-actions">
          <button 
            className="action-button new-chat"
            onClick={onNewChat}
            title="Start a new conversation"
            aria-label="Start new chat"
          >
            <Plus size={18} />
            <span>New Chat</span>
          </button>
          <button 
            className="action-button clear-chat"
            onClick={onClearChat}
            title="Clear current chat"
            aria-label="Clear chat"
          >
            <Trash2 size={18} />
            <span>Clear Chat</span>
          </button>
        </div>

        <div className="sidebar-section">
          <h3 className="section-title">LLM Provider</h3>
          <div className="provider-toggle">
            <button
              className={`provider-btn${provider === 'local' ? ' active local' : ''}`}
              onClick={() => onProviderChange('local')}
              title="Local Ollama — gemma4:latest (no cloud calls)"
            >
              <span>⚡</span>
              <span>Local</span>
            </button>
            <button
              className={`provider-btn${provider === 'azure' ? ' active azure' : ''}`}
              onClick={() => onProviderChange('azure')}
              title="Azure OpenAI — gpt-4o"
            >
              <span>☁</span>
              <span>Azure</span>
            </button>
          </div>
          <div className="provider-hint">
            {provider === 'local' ? 'gemma4:latest · Ollama' : 'gpt-4o · Azure OpenAI'}
          </div>
        </div>

        <div className="sidebar-section">
          <h3 className="section-title">System Status</h3>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Model</span>
              <span className="info-value">{provider === 'local' ? 'Gemma 4 (Local)' : 'GPT-4o (Azure)'}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Backend</span>
              <span className="info-value">RAG Engine</span>
            </div>
            <div className="info-item">
              <span className="info-label">Status</span>
              <span className="info-value status-online">
                <span className="status-dot"></span>Online
              </span>
            </div>
          </div>
        </div>

        <div className="sidebar-section">
          <h3 className="section-title">Usage Tips</h3>
          <ul className="tips-list">
            <li>Ask about device migration paths</li>
            <li>Request device comparisons</li>
            <li>Get compatibility suggestions</li>
            <li>Ask for technical specifications</li>
            <li>Get replacement recommendations</li>
          </ul>
        </div>

        <div className="sidebar-section">
          <h3 className="section-title">Support</h3>
          <div className="support-buttons">
            <button className="support-btn" title="Help">
              <HelpCircle size={16} />
              <span>Help</span>
            </button>
            <button className="support-btn" title="Settings">
              <Settings size={16} />
              <span>Settings</span>
            </button>
          </div>
        </div>

        <div className="sidebar-section">
          <h3 className="section-title">Administration</h3>
          <button 
            className="admin-button"
            onClick={onOpenAdmin}
            title="Manage vector database and files"
            aria-label="Admin panel"
          >
            <Lock size={16} />
            <span>Database Admin</span>
          </button>
        </div>

        <div className="sidebar-footer">
          <p className="version">v1.0.0</p>
          <p className="copyright">© 2026 Device Migration Assistant</p>
        </div>
      </div>
    </>
  )
}

export default Sidebar