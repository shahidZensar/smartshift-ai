import React from 'react'
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

export default LoadingIndicator