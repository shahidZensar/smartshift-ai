import React from 'react'
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

export default ChatWindow