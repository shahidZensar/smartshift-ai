import React, { useState, useRef, useEffect } from 'react'
import ChatWindow from './components/ChatWindow'
import InputArea from './components/InputArea'
import Sidebar from './components/Sidebar'
import AdminPanel from './components/AdminPanel'
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
  const [sessionId, setSessionId] = useState(null)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isAdminOpen, setIsAdminOpen] = useState(false)
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (text, files = []) => {
    if (!text.trim() && files.length === 0) return

    const userMessage = {
      id: Date.now(),
      text: text,
      sender: 'user',
      timestamp: new Date(),
      files: files.map(f => ({
        name: f.name,
        size: f.size,
        type: f.type
      }))
    }

    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      
      // Prepare form data for file upload
      const formData = new FormData()
      formData.append('question', text)
      formData.append('session_id', sessionId || '')
      formData.append('include_context', true)
      
      // Add files to form data
      files.forEach((file, index) => {
        formData.append(`files`, file.file)
      })
      
      // Add conversation history
      const history = messages.map(m => ({
        role: m.sender === 'user' ? 'user' : 'assistant',
        content: m.text
      }))
      formData.append('history', JSON.stringify(history))

      const response = files.length > 0 ? await fetch(`${apiUrl}/api/chat/upload`, {
        method: 'POST',
        body: formData
      }) : await fetch(`${apiUrl}/api/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          question: text,
          session_id: sessionId,
          include_context: true,
          history: history
        })
      })

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }

      const data = await response.json()

      // Persist the session id the backend returns so multi-turn flows
      // (e.g. the CONFIG refinement loop) chain across turns.
      if (data.session_id) {
        setSessionId(data.session_id)
      }

      const botMessage = {
        id: Date.now() + 1,
        text: data.response || data.message || data.answer || "I couldn't process that request. Please try again.",
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
    setSessionId(null)
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
        onOpenAdmin={() => setIsAdminOpen(true)}
      />
      <AdminPanel
        isOpen={isAdminOpen}
        onClose={() => setIsAdminOpen(false)}
      />
      <div className={`chat-container ${!isSidebarOpen ? 'sidebar-closed' : ''}`}>
        <ChatWindow 
          messages={messages}
          isLoading={isLoading}
          messagesEndRef={messagesEndRef}
          error={error}
        />
        <InputArea 
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          onFileUpload={(files) => console.log('Files uploaded:', files)}
        />
      </div>
    </div>
  )
}

export default App