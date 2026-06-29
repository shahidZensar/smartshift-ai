# SmarAI UI - Device Migration Chat Application

A modern React-based web interface for device inventory management and migration analysis. Features real-time chat with an AI assistant, device search, and administrative controls.

## 📋 Overview

SmarAI UI is a responsive web application built with React 18, Vite, and TailwindCSS. It provides an intuitive interface for querying device inventory, receiving migration recommendations, and managing device databases through an admin panel.

## ✨ Features

### User Features
- 💬 **Conversational Chat** - Ask questions about device inventory
- 🔍 **Device Search** - Filter devices by name, location, type
- 📊 **Device Details** - View comprehensive device information
- 📋 **Risk Assessment** - See critical and high-risk devices
- 🎯 **Migration Recommendations** - Get replacement model suggestions
- 📱 **Responsive Design** - Works on desktop, tablet, mobile

### Admin Features
- 📤 **File Upload** - Import CSV/Excel device data
- 🔗 **URL Import** - Add knowledge base from URLs
- 📂 **File Management** - View and delete uploaded files
- 📊 **Database Stats** - Monitor inventory metrics
- 🗂️ **Data Import** - Batch import CSV to database

## 🚀 Quick Start

### Prerequisites

- Node.js 16+ (LTS recommended)
- npm or yarn
- Backend server running (http://localhost:8000)

### Installation

1. **Navigate to UI directory**
   ```bash
   cd smarai/ui
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env.local
   ```

   Edit `.env.local`:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

4. **Start development server**
   ```bash
   npm run dev
   ```

   App will be available at `http://localhost:5173`

## 📁 Project Structure

```
ui/
├── src/
│   ├── components/
│   │   ├── Sidebar.jsx           # Navigation sidebar
│   │   ├── AdminPanel.jsx        # Admin control panel
│   │   ├── ChatWindow.jsx        # Main chat interface
│   │   ├── MessageBubble.jsx     # Chat message display
│   │   ├── InputArea.jsx         # User input field
│   │   └── LoadingSpinner.jsx    # Loading indicator
│   │
│   ├── styles/
│   │   ├── Sidebar.css           # Sidebar styling
│   │   ├── AdminPanel.css        # Admin panel styling
│   │   ├── ChatWindow.css        # Chat window styling
│   │   └── globals.css           # Global styles
│   │
│   ├── App.jsx                   # Main app component
│   ├── main.jsx                  # Entry point
│   └── index.css                 # Base styles
│
├── public/                        # Static assets
├── index.html                     # HTML template
├── vite.config.js                # Vite configuration
├── tailwind.config.js            # TailwindCSS config
├── postcss.config.js             # PostCSS config
├── package.json                  # Dependencies
├── .env.example                  # Environment template
└── README.md                      # This file
```

## 🎨 UI Components

### ChatWindow
Main chat interface for device queries.
```jsx
<ChatWindow
  messages={messages}
  onSendMessage={handleSendMessage}
  isLoading={isLoading}
/>
```

### Sidebar
Navigation and context sidebar.
```jsx
<Sidebar
  isOpen={isSidebarOpen}
  onToggle={toggleSidebar}
/>
```

### AdminPanel
Administrative control panel for data management.
```jsx
<AdminPanel
  isSidebarOpen={isSidebarOpen}
/>
```

### MessageBubble
Individual chat message display with markdown support.
```jsx
<MessageBubble
  message={message}
  isUser={true}
/>
```

## 🎯 Usage

### Chat with AI Assistant

1. Type your question in the input field
2. Ask about device inventory, migrations, or risks
3. View the AI response with formatted recommendations
4. Follow-up questions are supported in the same session

**Example Questions:**
- "What devices are end-of-support?"
- "Show devices in New York"
- "Which devices need migration?"
- "What are critical risk devices?"

### Admin Operations

1. **Upload Device Data**
   - Click "Upload Files" tab
   - Select CSV or Excel file
   - Preview and confirm import

2. **Add Knowledge Base**
   - Click "Add URL" tab
   - Enter URL for migration guidance
   - System indexes content

3. **Manage Files**
   - Click "Manage Files" tab
   - View uploaded documents
   - Delete if needed

4. **View Statistics**
   - Click "Database Stats" tab
   - Monitor total devices, inventory metrics
   - Track data freshness

## 🔧 Configuration

### Environment Variables

```env
# Backend API
VITE_API_BASE_URL=http://localhost:8000

# Optional: Feature flags
VITE_ENABLE_ANALYTICS=true
VITE_ENABLE_SEARCH=true
```

### Styling

Customize TailwindCSS in `tailwind.config.js`:
```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: '#3B82F6',
        danger: '#EF4444',
      },
    },
  },
}
```

## 🚀 Build & Deployment

### Development Build
```bash
npm run dev
```

### Production Build
```bash
npm run build
```

Output goes to `dist/` folder.

### Preview Built App
```bash
npm run preview
```

## 📦 Dependencies

### Core
- **react** (18.2+) - UI library
- **react-dom** (18.2+) - DOM rendering
- **vite** (5.0+) - Build tool

### Styling
- **tailwindcss** (3.3+) - Utility CSS
- **postcss** (8.4+) - CSS processing

### Features
- **axios** (1.6+) - HTTP client
- **react-markdown** (9.1+) - Markdown rendering
- **remark-gfm** (4.0+) - GitHub-flavored markdown
- **lucide-react** (0.292+) - Icons

### Development
- **eslint** (8.50+) - Code linting
- **@vitejs/plugin-react** - React support for Vite

See `package.json` for full dependency list.

## 🌐 API Integration

The UI communicates with the backend via REST API:

### Chat Endpoint
```javascript
POST /api/v1/chat
{
  "question": "user question",
  "session_id": "session-id",
  "include_context": true
}
```

### Admin Endpoints
```javascript
POST /api/admin/upload       // Upload files
GET  /api/admin/stats        // Get statistics
POST /api/admin/import       // Import CSV
GET  /api/admin/files        // List files
DELETE /api/admin/files/{id} // Delete file
```

## 🎨 Responsive Design

### Breakpoints
- **Mobile**: < 640px
- **Tablet**: 640px - 1024px
- **Desktop**: > 1024px

### Sidebar Behavior
- **Desktop**: Always visible (toggle to collapse)
- **Tablet**: Collapsible overlay
- **Mobile**: Hidden by default, slide-out menu

## ⚡ Performance

### Optimizations
- ✅ Code splitting with Vite
- ✅ Lazy component loading
- ✅ Markdown rendering with react-markdown
- ✅ CSS minification with Tailwind
- ✅ Assets optimization

### Build Size
- Main bundle: ~150-200 KB (gzipped)
- Development: ~2-3 MB
- Production: ~300-400 KB

## 🐛 Troubleshooting

### Issue: "Cannot connect to backend"
```javascript
// Check backend URL in .env.local
VITE_API_BASE_URL=http://localhost:8000

// Test connectivity
curl http://localhost:8000/health
```

### Issue: Styles not loading
```bash
# Rebuild Tailwind
npm run build

# Clear cache
rm -rf node_modules/.vite
npm run dev
```

### Issue: Chat not responding
- Check backend logs
- Verify API endpoint in dev tools (Network tab)
- Check browser console for errors
- Ensure session_id is being sent

### Issue: File upload fails
- Check file size (< 10MB recommended)
- Verify file format (CSV, Excel)
- Check backend logs for parse errors

## 🧪 Testing

### Linting
```bash
npm run lint
```

### Manual Testing

1. **Chat Functionality**
   - Send test message
   - Verify response appears
   - Check markdown formatting

2. **Admin Panel**
   - Upload test CSV
   - Verify preview
   - Check database import

3. **Responsive Design**
   - Resize browser window
   - Test on mobile device
   - Check sidebar toggle

## 📱 Browser Support

- ✅ Chrome/Edge (latest)
- ✅ Firefox (latest)
- ✅ Safari (latest)
- ✅ Mobile browsers
- ⚠️ IE11 (not supported)

## 🔐 Security

### Best Practices
- ✅ No sensitive data in localStorage
- ✅ Session IDs for user tracking
- ✅ Sanitized markdown rendering
- ✅ CORS configured on backend

### Environment Variables
- Never commit `.env.local`
- Use `.env.example` template
- Add sensitive data in CI/CD secrets

## 📊 Performance Monitoring

Monitor in browser DevTools:

1. **Performance Tab**
   - Track load times
   - Identify slow operations

2. **Network Tab**
   - Monitor API calls
   - Check response times

3. **Console**
   - Check for errors/warnings
   - Review logs

## 🚀 Deployment

### Vercel
```bash
vercel
```

### Netlify
```bash
netlify deploy --prod --dir=dist
```

### Docker
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "preview"]
```

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/name`
2. Make changes and test
3. Commit: `git commit -am 'Add feature'`
4. Push: `git push origin feature/name`
5. Create pull request

## 📝 License

Proprietary - Zensar Technologies

## 📧 Support

For issues:
1. Check browser console (F12)
2. Review backend logs
3. Check `.env.local` configuration
4. Open GitHub issue with error details

## 🔄 Version History

- **v1.0.0** (Current)
  - Chat interface
  - Device search
  - Admin panel
  - File upload
  - Responsive design

---

**Last Updated**: April 23, 2026

## 🎓 Additional Resources

- [React Documentation](https://react.dev)
- [Vite Guide](https://vitejs.dev)
- [TailwindCSS Docs](https://tailwindcss.com)
- [Backend API Docs](../app/README.md)

