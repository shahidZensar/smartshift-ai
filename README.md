# SmarAI - Enterprise Device Migration Assistant

A comprehensive AI-powered platform for device lifecycle management, end-of-support analysis, and migration recommendations using local Language Models and vector-based retrieval.

## 🎯 Project Overview

SmarAI is an enterprise-grade solution that:
- Analyzes device inventory for end-of-support and end-of-life devices
- Calculates risk levels based on support date expiration
- Provides specific replacement model recommendations
- Delivers insights through a conversational AI interface
- Manages device data with administrative tools

**Architecture**: Full-stack application with React frontend and FastAPI backend, powered by local Ollama LLM and Qdrant vector database.

## 📦 Project Structure

```
smarai/
├── app/                          # Backend - FastAPI service
│   ├── app.py                   # Main FastAPI application
│   ├── config.py                # Configuration management
│   ├── util.py                  # Prompt templates & utilities
│   ├── decision.py              # LLM routing logic
│   ├── rag.py                   # RAG system
│   ├── admin.py                 # Admin endpoints
│   ├── requirements.txt          # Python dependencies
│   ├── .env.ollama              # Local LLM config
│   ├── .env.openai              # OpenAI config
│   └── README.md                # Backend documentation
│
├── ui/                           # Frontend - React application
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── styles/              # CSS styling
│   │   ├── App.jsx              # Main App component
│   │   └── main.jsx             # Entry point
│   ├── package.json             # Node dependencies
│   ├── vite.config.js           # Vite configuration
│   ├── tailwind.config.js       # TailwindCSS config
│   ├── .env.example             # Environment template
│   └── README.md                # Frontend documentation
│
├── data/                         # Data storage
├── test.py                       # Test scripts
└── README.md                     # This file
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ (backend)
- Node.js 16+ (frontend)
- MySQL database
- Ollama (local LLM) or OpenAI API key
- Qdrant (vector database)

### Backend Setup (5 minutes)

```bash
# Navigate to app directory
cd smarai/app

# Create virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows
# or
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env.ollama
# Edit .env.ollama with your settings

# Start server
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Backend running at: `http://localhost:8000`

### Frontend Setup (5 minutes)

```bash
# Navigate to ui directory
cd smarai/ui

# Install dependencies
npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local if needed

# Start development server
npm run dev
```

Frontend running at: `http://localhost:5173`

### Verify Setup

```bash
# Test backend health
curl http://localhost:8000/health

# Check API docs
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc

# Test frontend
# Open browser: http://localhost:5173
```

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
│  Sidebar | Chat Window | Admin Panel | Message Display  │
└────────────────────┬────────────────────────────────────┘
                     │ REST API (axios)
                     ▼
┌─────────────────────────────────────────────────────────┐
│                Backend (FastAPI)                         │
├─────────────────┬──────────────────┬────────────────────┤
│   LLM Layer     │   Data Layer     │  Storage Layer    │
├─────────────────┼──────────────────┼────────────────────┤
│ Ollama/OpenAI   │ SQLAlchemy ORM   │ MySQL Database    │
│ LangChain       │ Query Engine     │ Qdrant Vector DB  │
│ Prompts (RAG)   │ Session Memory   │ File Storage      │
└─────────────────┴──────────────────┴────────────────────┘
```

### Data Flow

1. **User Query** → Frontend (Chat)
2. **API Request** → Backend (FastAPI)
3. **SQL Generation** → LLM converts to SQL
4. **Database Query** → Retrieves device data
5. **RAG Retrieval** → Gets migration guidance
6. **Analysis** → LLM analyzes and recommends
7. **Response** → Formatted back to frontend

## 🤖 LLM Configuration

### Option 1: Local Ollama (Recommended for Development)

```bash
# Install Ollama
# Visit https://ollama.ai

# Pull model
ollama pull llama3.2:3b

# Start Ollama
ollama serve

# In another terminal, test
curl http://localhost:11434/api/tags
```

Environment config (`.env.ollama`):
```env
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://localhost:11434
TEMPERATURE=0.7
TOP_P=0
```

### Option 2: OpenAI API (Production)

Environment config (`.env.openai`):
```env
OPENAI_API_KEY=sk-xxx...
OPENAI_MODEL=gpt-3.5-turbo
TEMPERATURE=0.7
```

## 💾 Database Setup

### MySQL Installation

```bash
# Windows (using MySQL Installer)
# macOS (using Homebrew)
brew install mysql

# Linux (Ubuntu/Debian)
sudo apt-get install mysql-server

# Start MySQL
mysql.server start  # macOS
# or
mysqld  # Windows
```

### Create Database

```sql
-- Connect to MySQL
mysql -u root -p

-- Create database
CREATE DATABASE inventory;

-- Create user (optional)
CREATE USER 'smarai'@'localhost' IDENTIFIED BY 'password';
GRANT ALL PRIVILEGES ON inventory.* TO 'smarai'@'localhost';
FLUSH PRIVILEGES;
```

### Connection String
```env
MYSQL_URI=mysql+pymysql://user:password@localhost:3306/inventory
```

## 🔍 Key Features

### Device Analysis
- ✅ **Risk Assessment** - Critical/High/Low based on support dates
- ✅ **Instance Tracking** - Same model across multiple locations
- ✅ **End-of-Life Detection** - Automatic identification
- ✅ **Replacement Recommendations** - Specific models suggested

### Chat Interface
- ✅ **Conversational** - Ask natural language questions
- ✅ **Markdown Support** - Formatted responses
- ✅ **Session Memory** - Context across messages
- ✅ **Real-time** - Live response streaming

### Admin Tools
- ✅ **File Upload** - CSV/Excel import
- ✅ **Bulk Import** - Database loading
- ✅ **File Management** - Upload history
- ✅ **Statistics** - Database metrics

## 📊 API Endpoints

### Chat API
```
POST /api/v1/chat
{
  "question": "What devices are end-of-support?",
  "session_id": "user-123",
  "include_context": true
}
```

### Admin APIs
```
POST   /api/admin/upload       - Upload files
GET    /api/admin/stats        - Database statistics
POST   /api/admin/import       - Import CSV data
GET    /api/admin/files        - List files
DELETE /api/admin/files/{id}   - Delete file
```

### Health Check
```
GET /health                    - Service health
```

## 🎨 Technology Stack

### Backend
- **Framework**: FastAPI (Python)
- **ORM**: SQLAlchemy
- **LLM**: Ollama / OpenAI
- **RAG**: LangChain + Qdrant
- **Database**: MySQL
- **Server**: Uvicorn

### Frontend
- **Framework**: React 18
- **Build Tool**: Vite
- **Styling**: TailwindCSS
- **HTTP**: Axios
- **Markdown**: react-markdown
- **Icons**: lucide-react

## ⚡ Performance Metrics

| Component | Time | Notes |
|-----------|------|-------|
| Backend startup | ~2s | Fast with Uvicorn |
| Frontend build | ~5s | With Vite |
| Chat response | ~25-30s | LLM inference bottleneck |
| Database query | ~1-2s | Indexed MySQL |
| RAG retrieval | ~2-3s | Qdrant search |

## 🔧 Configuration & Customization

### Backend Configuration
Edit `app/config.py`:
- LLM model selection
- Database connection
- Vector DB settings
- Temperature/sampling

### Frontend Configuration
Edit `.env.local`:
- Backend API URL
- Feature flags
- Analytics settings

### Prompt Customization
Edit `app/util.py`:
- `final_prompt` - Analysis template
- `sql_prompt` - Query generation
- Risk calculation rules
- Output format

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check Python version
python --version

# Verify dependencies
pip list | grep fastapi

# Check MySQL connection
mysql -u root -p

# Verify Ollama
curl http://localhost:11434/api/tags
```

### Frontend won't connect
```bash
# Check backend is running
curl http://localhost:8000/health

# Verify VITE_API_BASE_URL in .env.local
# Clear browser cache (Ctrl+Shift+Del)
```

### Slow responses
- Use smaller LLM (llama3.2:3b)
- Increase TEMPERATURE (0.8-0.9)
- Reduce data context size
- Check MySQL performance

## 📚 Documentation

### Detailed Guides
- [Backend README](./app/README.md) - API, LLM setup, configuration
- [Frontend README](./ui/README.md) - Components, styling, deployment

### API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🚀 Deployment

### Docker Compose (All Services)
```bash
docker-compose up -d
```

### Cloud Deployment
- **Backend**: Heroku, AWS EC2, Google Cloud
- **Frontend**: Vercel, Netlify, AWS S3 + CloudFront

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/name`
2. Implement changes with tests
3. Commit: `git commit -am 'Add feature'`
4. Push: `git push origin feature/name`
5. Submit pull request

## 📋 Development Checklist

- [ ] Backend running on port 8000
- [ ] Frontend running on port 5173
- [ ] MySQL database created
- [ ] Ollama/OpenAI configured
- [ ] Qdrant running
- [ ] Chat functionality working
- [ ] Admin panel accessible

## 🐛 Known Issues

- LLM inference time can be 20-30s (model dependent)
- Very large datasets (>100k devices) may require optimization
- Markdown rendering may have slight delays for large responses

## 📝 License

Proprietary - Zensar Technologies

## 📧 Support & Contact

For issues, questions, or suggestions:
1. Check README files for your component
2. Review API documentation
3. Check application logs
4. Contact development team

## 🎓 Learning Resources

- [FastAPI Tutorial](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev)
- [Ollama Models](https://ollama.ai)
- [LangChain Docs](https://langchain.readthedocs.io/)
- [TailwindCSS Guide](https://tailwindcss.com)

## 🔄 Version History

### v1.0.0 (Current)
- ✅ Full-stack application
- ✅ Device analysis engine
- ✅ Chat interface
- ✅ Admin panel
- ✅ RAG system
- ✅ Local LLM support
- ✅ Responsive UI

---

**Project Status**: Active Development
**Last Updated**: April 23, 2026
**Maintained By**: Zensar Technologies

#   t e m p  
 # smartshift-ai-migration
# smartshift-ai-migration
# smartshift-ai-migration
# smartshift-ai
