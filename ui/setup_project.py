import os
import json

# Define base path
BASE_PATH = "."

# Create directory structure
directories = [
    "src",
    "src/components",
    "src/styles",
    "public"
]

for directory in directories:
    os.makedirs(directory, exist_ok=True)
    print(f"✓ Created directory: {directory}")

# File contents
files_content = {
    # Root files
    "index.html": '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Device Migration AI Assistant Chat">
  <title>Device Migration Chat Assistant</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>''',

    "vite.config.js": '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    strictPort: false,
    cors: true
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'terser'
  }
})''',

    "tailwind.config.js": '''export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#3b82f6',
        secondary: '#1e293b',
      },
      animation: {
        fadeIn: 'fadeIn 0.3s ease-in',
        bounce: 'bounce 1.4s infinite ease-in-out',
      }
    },
  },
  plugins: [],
}''',

    "postcss.config.js": '''export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}''',

    ".env.example": '''VITE_API_URL=http://localhost:8000
VITE_API_ENDPOINT=/api/chat''',

    ".gitignore": '''# Dependencies
node_modules/
npm-debug.log
yarn-error.log
.pnpm-debug.log

# Production
dist/
build/

# Environment variables
.env
.env.local
.env.*.local

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# OS
Thumbs.db''',

    # src files
    "src/main.jsx": '''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)''',

    "src/App.jsx": '''import React, { useState, useRef, useEffect } from 'react'
import ChatWindow from './components/ChatWindow'
import InputArea from './components/InputArea'
import Sidebar from './components/Sidebar'
import './App.css'

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Hello! I'm your Device Migration Assistant. Ask me anything about device migration, suggestions, or compatibility.",
      sender: 'bot',
      timestamp: new Date()
    }
  ])
  const [isLoading, setIsLoading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (text) => {
    if (!text.trim()) return

    const userMessage = {
      id: Date.now(),
      text: text,
      sender: 'user',
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: text,
          history: messages.map(m => ({
            role: m.sender === 'user' ? 'user' : 'assistant',
            content: m.text
          }))
        })
      })

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }

      const data = await response.json()
      
      const botMessage = {
        id: Date.now() + 1,
        text: data.response || data.message || "I couldn't process that request. Please try again.",
        sender: 'bot',
        timestamp: new Date()
      }

      setMessages(prev => [...prev, botMessage])
    } catch (error) {
      console.error('Error:', error)
      
      const errorMessage = {
        id: Date.now() + 1,
        text: `Error: ${error.message}. Make sure the backend server is running at ${import.meta.env.VITE_API_URL || 'http://localhost:8000'}`,
        sender: 'bot',
        timestamp: new Date(),
        isError: true
      }

      setMessages(prev => [...prev, errorMessage])
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  const handleNewChat = () => {
    setMessages([
      {
        id: 1,
        text: "Hello! I'm your Device Migration Assistant. Ask me anything about device migration, suggestions, or compatibility.",
        sender: 'bot',
        timestamp: new Date()
      }
    ])
    setError(null)
  }

  const handleClearChat = () => {
    handleNewChat()
  }

  return (
    <div className="app-container">
      <Sidebar 
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        onNewChat={handleNewChat}
        onClearChat={handleClearChat}
      />
      <div className="chat-container">
        <ChatWindow 
          messages={messages}
          isLoading={isLoading}
          messagesEndRef={messagesEndRef}
          error={error}
        />
        <InputArea 
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}

export default App''',

    "src/index.css": '''* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --primary-color: #3b82f6;
  --secondary-color: #1e293b;
  --background-color: #f8fafc;
  --surface-color: #ffffff;
  --border-color: #e2e8f0;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --user-message-bg: #3b82f6;
  --bot-message-bg: #f1f5f9;
  --error-color: #ef4444;
  --success-color: #10b981;
}

html,
body,
#root {
  height: 100%;
  width: 100%;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: var(--background-color);
  color: var(--text-primary);
  line-height: 1.5;
}

button {
  cursor: pointer;
  border: none;
  background: none;
  font-family: inherit;
  transition: all 0.2s ease;
}

textarea,
input {
  font-family: inherit;
}

/* Scrollbar Styling */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--background-color);
}

::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}

/* Firefox Scrollbar */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) var(--background-color);
}''',

    "src/App.css": '''.app-container {
  display: flex;
  height: 100vh;
  width: 100%;
  background-color: var(--background-color);
  overflow: hidden;
}

.chat-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  background-color: var(--surface-color);
  overflow: hidden;
  min-width: 0;
}

@media (max-width: 768px) {
  .app-container {
    flex-direction: column;
  }

  .chat-container {
    width: 100%;
  }
}''',

    # Component files
    "src/components/ChatWindow.jsx": '''import React from 'react'
import MessageBubble from './MessageBubble'
import LoadingIndicator from './LoadingIndicator'
import '../styles/ChatWindow.css'

function ChatWindow({ messages, isLoading, messagesEndRef, error }) {
  return (
    <div className="chat-window">
      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-state">
            <p>No messages yet. Start a conversation!</p>
          </div>
        ) : (
          messages.map((message) => (
            <MessageBubble 
              key={message.id}
              message={message}
            />
          ))
        )}
        {isLoading && <LoadingIndicator />}
        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}

export default ChatWindow''',

    "src/components/MessageBubble.jsx": '''import React, { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import '../styles/MessageBubble.css'

function MessageBubble({ message }) {
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

  return (
    <div className={`message-bubble message-${message.sender} ${message.isError ? 'message-error' : ''}`}>
      <div className="message-content">
        <p className="message-text">{message.text}</p>
        <span className="message-time">{formatTime(message.timestamp)}</span>
      </div>
      {message.sender === 'bot' && !message.isError && (
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

export default MessageBubble''',

    "src/components/InputArea.jsx": '''import React, { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import '../styles/InputArea.css'

function InputArea({ onSendMessage, isLoading }) {
  const [input, setInput] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [input])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (input.trim() && !isLoading) {
      onSendMessage(input)
      setInput('')
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="input-area">
      <form onSubmit={handleSubmit} className="input-form">
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
        <button 
          type="submit" 
          className="send-button"
          disabled={isLoading || !input.trim()}
          title="Send message (Enter)"
          aria-label="Send message"
        >
          <Send size={20} />
        </button>
      </form>
      <p className="input-hint">Powered by RAG Engine with Llama 3.2</p>
    </div>
  )
}

export default InputArea''',

    "src/components/Sidebar.jsx": '''import React from 'react'
import { Menu, Plus, Trash2, Settings, HelpCircle } from 'lucide-react'
import '../styles/Sidebar.css'

function Sidebar({ isOpen, onToggle, onNewChat, onClearChat }) {
  return (
    <>
      <button 
        className="menu-toggle" 
        onClick={onToggle} 
        title="Toggle sidebar"
        aria-label="Toggle sidebar"
      >
        <Menu size={24} />
      </button>
      
      <div className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <h1 className="sidebar-title">Device Migration Chat</h1>
          <button 
            className="close-button"
            onClick={onToggle}
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
          <h3 className="section-title">System Status</h3>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Model</span>
              <span className="info-value">Llama 3.2</span>
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

        <div className="sidebar-footer">
          <p className="version">v1.0.0</p>
          <p className="copyright">© 2026 Device Migration Assistant</p>
        </div>
      </div>
    </>
  )
}

export default Sidebar''',

    "src/components/LoadingIndicator.jsx": '''import React from 'react'
import '../styles/LoadingIndicator.css'

function LoadingIndicator() {
  return (
    <div className="loading-message">
      <div className="loading-spinner">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <p>Device Assistant is thinking...</p>
    </div>
  )
}

export default LoadingIndicator''',

    # Style files
    "src/styles/ChatWindow.css": '''.chat-window {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, var(--background-color) 0%, #ffffff 100%);
}

.messages-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-size: 16px;
}

@media (max-width: 768px) {
  .chat-window {
    padding: 16px;
  }

  .messages-container {
    gap: 12px;
  }
}

@media (max-width: 480px) {
  .chat-window {
    padding: 12px;
  }
}''',

    "src/styles/MessageBubble.css": '''.message-bubble {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  max-width: 85%;
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-user {
  align-self: flex-end;
  margin-left: auto;
  flex-direction: row-reverse;
}

.message-bot {
  align-self: flex-start;
}

.message-error {
  border: 1px solid var(--error-color);
  background-color: #fee2e2;
}

.message-content {
  padding: 12px 16px;
  border-radius: 12px;
  word-wrap: break-word;
  white-space: pre-wrap;
  line-height: 1.5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.message-user .message-content {
  background-color: var(--user-message-bg);
  color: white;
  border-bottom-right-radius: 4px;
}

.message-bot .message-content {
  background-color: var(--bot-message-bg);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  border: 1px solid var(--border-color);
}

.message-error .message-content {
  background-color: #fecaca;
  color: #991b1b;
  border-color: var(--error-color);
}

.message-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}

.message-time {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 4px;
  display: block;
}

.message-user .message-time {
  color: rgba(255, 255, 255, 0.7);
}

.message-bot .message-time {
  color: var(--text-secondary);
}

.copy-button {
  padding: 6px;
  border-radius: 6px;
  background-color: transparent;
  color: var(--text-secondary);
  transition: all 0.2s;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.copy-button:hover {
  background-color: var(--border-color);
  color: var(--primary-color);
}

.copy-button svg {
  color: currentColor;
}

@media (max-width: 768px) {
  .message-bubble {
    max-width: 95%;
  }

  .message-content {
    padding: 10px 12px;
    font-size: 13px;
  }

  .copy-button {
    padding: 4px;
  }
}''',

    "src/styles/InputArea.css": '''.input-area {
  padding: 16px;
  border-top: 1px solid var(--border-color);
  background-color: var(--surface-color);
  flex-shrink: 0;
}

.input-form {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-bottom: 8px;
}

.message-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-primary);
  resize: none;
  max-height: 120px;
  min-height: 44px;
  transition: border-color 0.2s, box-shadow 0.2s;
  background-color: var(--background-color);
  font-family: inherit;
}

.message-input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.message-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background-color: #f5f5f5;
}

.message-input::placeholder {
  color: var(--text-secondary);
}

.send-button {
  padding: 10px 16px;
  background-color: var(--primary-color);
  color: white;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  height: 44px;
  min-width: 44px;
  font-weight: 500;
}

.send-button:hover:not(:disabled) {
  background-color: #2563eb;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
  transform: translateY(-2px);
}

.send-button:active:not(:disabled) {
  transform: translateY(0);
}

.send-button:disabled {
  background-color: var(--border-color);
  color: var(--text-secondary);
  cursor: not-allowed;
}

.input-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  text-align: center;
}

@media (max-width: 768px) {
  .input-area {
    padding: 12px;
  }

  .message-input {
    padding: 10px 12px;
    font-size: 13px;
  }

  .send-button {
    padding: 8px 12px;
    min-width: 40px;
    height: 40px;
  }

  .input-hint {
    font-size: 11px;
  }
}''',

    "src/styles/Sidebar.css": '''.menu-toggle {
  display: none;
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 1000;
  padding: 8px;
  background-color: var(--primary-color);
  color: white;
  border-radius: 8px;
  transition: all 0.2s;
}

.menu-toggle:hover {
  background-color: #2563eb;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.sidebar {
  width: 280px;
  background: linear-gradient(135deg, var(--secondary-color) 0%, #0f172a 100%);
  color: white;
  display: flex;
  flex-direction: column;
  padding: 20px;
  overflow-y: auto;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  transition: transform 0.3s ease;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.5px;
}

.close-button {
  display: none;
  color: white;
  font-size: 24px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.close-button:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 30px;
}

.action-button {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.action-button:hover {
  background-color: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.2);
}

.action-button.new-chat:hover {
  background-color: rgba(16, 185, 129, 0.2);
  border-color: rgba(16, 185, 129, 0.3);
}

.action-button.clear-chat:hover {
  background-color: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.3);
}

.sidebar-section {
  margin-bottom: 25px;
}

.section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 12px;
  letter-spacing: 0.5px;
}

.info-grid {
  display: grid;
  gap: 10px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background-color: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.info-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
}

.status-online {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  background-color: var(--success-color);
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.tips-list {
  list-style: none;
  font-size: 13px;
  line-height: 1.8;
}

.tips-list li {
  margin-bottom: 8px;
  padding-left: 16px;
  position: relative;
  color: rgba(255, 255, 255, 0.8);
}

.tips-list li:before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--primary-color);
  font-weight: bold;
}

.support-buttons {
  display: flex;
  gap: 8px;
}

.support-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
  border-radius: 6px;
  font-size: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: all 0.2s;
}

.support-btn:hover {
  background-color: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.2);
}

.sidebar-footer {
  margin-top: auto;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  text-align: center;
}

.version {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  margin: 0 0 4px 0;
}

.copyright {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  margin: 0;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .menu-toggle {
    display: flex;
  }

  .sidebar {
    position: fixed;
    left: 0;
    top: 0;
    height: 100vh;
    z-index: 999;
    transform: translateX(-100%);
    width: 250px;
    border-radius: 0;
    border-right: none;
  }

  .sidebar.open {
    transform: translateX(0);
    box-shadow: 4px 0 12px rgba(0, 0, 0, 0.3);
  }

  .close-button {
    display: flex;
  }
}

@media (max-width: 480px) {
  .sidebar {
    width: 100%;
  }

  .action-button {
    font-size: 13px;
  }
}''',

    "src/styles/LoadingIndicator.css": '''.loading-message {
  display: flex;
  align-items: center;
  gap: 12px;
  align-self: flex-start;
  padding: 12px 16px;
  background-color: var(--bot-message-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  border-bottom-left-radius: 4px;
  max-width: 85%;
}

.loading-spinner {
  display: flex;
  gap: 4px;
}

.loading-spinner span {
  width: 8px;
  height: 8px;
  background-color: var(--primary-color);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.loading-spinner span:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-spinner span:nth-child(2) {
  animation-delay: -0.16s;
}

.loading-spinner span:nth-child(3) {
  animation-delay: 0s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.loading-message p {
  color: var(--text-secondary);
  font-size: 13px;
  margin: 0;
  font-weight: 500;
}

@media (max-width: 768px) {
  .loading-message {
    max-width: 95%;
    padding: 10px 12px;
  }

  .loading-message p {
    font-size: 12px;
  }
}'''
}

# Create all files with proper directory handling
for file_path, content in files_content.items():
    # Get directory path
    dir_path = os.path.dirname(file_path)
    
    # Create directory if it doesn't exist and has a path
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    # Create file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✓ Created file: {file_path}")

# Update package.json with correct content
package_json = {
    "name": "device-migration-chat",
    "description": "Device Migration AI Assistance Chat Application",
    "version": "1.0.0",
    "private": True,
    "type": "module",
    "main": "index.js",
    "scripts": {
        "dev": "vite",
        "build": "vite build",
        "preview": "vite preview",
        "lint": "eslint src --ext js,jsx"
    },
    "dependencies": {
        "react": "^18.2.0",
        "react-dom": "^18.2.0",
        "axios": "^1.6.0",
        "lucide-react": "^0.292.0"
    },
    "devDependencies": {
        "@vitejs/plugin-react": "^4.2.0",
        "vite": "^5.0.0",
        "tailwindcss": "^3.3.0",
        "postcss": "^8.4.31",
        "autoprefixer": "^10.4.16",
        "eslint": "^8.50.0",
        "eslint-plugin-react": "^7.33.0"
    }
}

with open('package.json', 'w', encoding='utf-8') as f:
    json.dump(package_json, f, indent=2)
print("✓ Updated file: package.json")

print("\n" + "="*60)
print("✅ Project setup completed successfully!")
print("="*60)
print("\nNext steps:")
print("1. npm install")
print("2. npm run dev")
print("\nProject structure created:")
print("""
UI/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── .env.example
├── .gitignore
├── package.json
├── public/
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── index.css
    ├── App.css
    ├── components/
    │   ├── ChatWindow.jsx
    │   ├── MessageBubble.jsx
    │   ├── InputArea.jsx
    │   ├── Sidebar.jsx
    │   └── LoadingIndicator.jsx
    └── styles/
        ├── ChatWindow.css
        ├── MessageBubble.css
        ├── InputArea.css
        ├── Sidebar.css
        └── LoadingIndicator.css
""")