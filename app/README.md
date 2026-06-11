# SmarAI Backend - Device Migration Analysis API

A FastAPI-based backend for enterprise device lifecycle management and migration recommendations using Local Language Models (Ollama) and Retrieval-Augmented Generation (RAG).

## 📋 Overview

The SmarAI backend provides intelligent analysis of device inventory data, calculates risk assessments based on end-of-support dates, and generates migration recommendations with replacement models. It uses a local Ollama instance for LLM inference and Qdrant for vector database operations.

## 🏗️ Architecture

```
Backend Service
├── FastAPI Application (app.py)
├── LLM Integration (decision.py) - Ollama/OpenAI
├── Database Layer (SQLAlchemy ORM)
├── RAG System (rag.py) - Vector DB + Retrieval
├── Prompt Templates (util.py)
└── Admin Panel (admin.py)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- MySQL database
- Ollama (local LLM) or OpenAI API key
- Qdrant vector database

### Installation

1. **Clone and navigate to app directory**
   ```bash
   cd smarai/app
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # Windows
   # or
   source venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   # Copy and edit environment file based on your setup
   cp .env.example .env.ollama  # For local Ollama
   # or
   cp .env.example .env.openai  # For OpenAI
   ```

   Edit the configuration:
   ```env
   OLLAMA_MODEL=llama3.2:3b
   OLLAMA_BASE_URL=http://localhost:11434
   QDRANT_HOST=localhost
   QDRANT_PORT=6333
   MYSQL_URI=mysql+pymysql://user:password@localhost:3306/inventory
   TEMPERATURE=0.7
   TOP_P=0
   ```

5. **Start backend server**
   ```bash
   python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

Server will be available at `http://localhost:8000`

## 📁 Project Structure

```
app/
├── app.py              # Main FastAPI application and endpoints
├── config.py           # Configuration management
├── models.py           # Pydantic data models
├── util.py             # Prompt templates and utility functions
├── decision.py         # LLM routing and decision making
├── rag.py              # RAG system and vector store management
├── admin.py            # Admin panel endpoints
├── router.py           # API route definitions
├── memory.py           # Conversation memory management
├── file_analyzer.py    # File upload and parsing
├── web_search.py       # Web search integration
├── prompts.py          # Additional prompt definitions
├── requirements.txt    # Python dependencies
├── .env.ollama         # Ollama configuration
├── .env.openai         # OpenAI configuration
└── README.md           # This file
```

## 🔌 API Endpoints

### Health Check
```
GET /health
```
Returns service health status.

### Chat/Query Endpoint
```
POST /api/v1/chat
Content-Type: application/json

{
  "question": "What devices are end-of-support?",
  "session_id": "user-session-123",
  "include_context": true
}
```

**Response:**
```json
{
  "answer": "Analysis of device inventory...",
  "session_id": "user-session-123",
  "timestamp": "2026-04-23T10:30:00",
  "sources": ["doc1", "doc2"],
  "follow_up_questions": []
}
```

### Admin Endpoints
```
POST /api/admin/upload        - Upload CSV/Excel device data
GET  /api/admin/stats         - Get database statistics
POST /api/admin/import        - Import CSV to MySQL
GET  /api/admin/files         - List uploaded files
DELETE /api/admin/files/{id}  - Delete file
```

## 🤖 LLM Integration

### Supported Models

**Local (Ollama)**
- `llama3.2:3b` (default, fast)
- `llama3.2:latest` (slower, more capable)
- `mistral:latest` (alternative)
- `phi3:mini` (lightweight)

**Cloud (OpenAI)**
- `gpt-4`
- `gpt-3.5-turbo`

### Model Selection

Set environment variable:
```bash
ENV=ollama    # For local Ollama
ENV=openai    # For OpenAI API
```

## 💾 Database Configuration

### MySQL Setup

```sql
-- Create database
CREATE DATABASE inventory;

-- Create inventory table (auto-created by ORM)
USE inventory;

-- The app will create tables automatically via SQLAlchemy
```

### Connection String Format
```
mysql+pymysql://username:password@host:port/database
```

## 🧠 Prompt Templates

Located in `util.py`:

1. **final_prompt** - Device analysis and recommendation generation
   - Parses JSON device data
   - Calculates risk levels based on support dates
   - Generates migration recommendations

2. **sql_prompt** - Natural language to SQL query conversion
   - Converts user questions to MySQL queries
   - Enforces parameterized queries
   - Includes LIKE search wildcards

### Customizing Prompts

Edit the prompt templates in `util.py`:

```python
final_prompt = ChatPromptTemplate.from_template("""
ROLE: Enterprise Device Migration Analyst
...
""")

sql_prompt = PromptTemplate(...)
```

## 🔍 Features

### Device Analysis
- ✅ Risk level calculation (Critical/High/Low/Unknown)
- ✅ Support date tracking
- ✅ End-of-life device identification
- ✅ Replacement model recommendations
- ✅ Instance-level tracking (same model, different locations)

### Query Processing
- ✅ Natural language understanding
- ✅ Dynamic SQL generation
- ✅ Parallel SQL and RAG execution
- ✅ Timeout protection (10s SQL, 5s RAG, 30s LLM)
- ✅ Graceful error handling

### Data Management
- ✅ CSV/Excel upload
- ✅ Batch import to MySQL
- ✅ Vector indexing for RAG
- ✅ Session-based memory

## ⚙️ Configuration Options

### Environment Variables

```env
# LLM Configuration
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://localhost:11434
TEMPERATURE=0.7
TOP_P=0

# Database Configuration
MYSQL_URI=mysql+pymysql://user:pass@localhost/inventory

# Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333
COLLECTION_NAME=device_kb

# Memory Settings
MEMORY_TOP_K=5
RAG_TOP_K=5
```

## 🔐 Authentication

Currently the API has no authentication. For production, add:

```python
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/api/v1/chat", security=Depends(security))
async def ask_question(request: QueryRequest):
    ...
```

## 📊 Performance Optimization

### Response Time

| Operation | Time | Notes |
|-----------|------|-------|
| SQL Generation | ~3-5s | Local LLM |
| Database Query | ~1-2s | Depends on data size |
| RAG Retrieval | ~2-3s | Parallel with SQL |
| LLM Analysis | ~20-30s | Main bottleneck |
| **Total** | ~25-30s | Optimized with parallel execution |

### Optimization Strategies

1. **Parallel Execution** - SQL and RAG run concurrently
2. **Timeout Protection** - Prevents hanging requests
3. **Context Size Optimization** - Reduced token count
4. **Fallback Mechanisms** - Graceful degradation on timeout

## 🐛 Troubleshooting

### Issue: "Connection refused" to Ollama
```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

### Issue: MySQL connection error
```bash
# Check MySQL is running
mysql -u root -p

# Verify connection string format
MYSQL_URI=mysql+pymysql://root:password@127.0.0.1:3306/inventory
```

### Issue: Vector DB not found
```bash
# Check Qdrant service
curl http://localhost:6333/health

# Start Qdrant
docker run -p 6333:6333 qdrant/qdrant
```

### Issue: Slow responses
- Reduce `TEMPERATURE` (closer to 0 = faster, more deterministic)
- Use smaller model (llama3.2:3b instead of 7b)
- Reduce data context size
- Check database query performance

## 📚 API Documentation

Once running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 🧪 Testing

Run tests:
```bash
pytest tests/
```

Test a query:
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show devices with end of support in 2026",
    "session_id": "test-session"
  }'
```

## 📦 Dependencies

Key packages:
- **FastAPI** - Web framework
- **SQLAlchemy** - ORM
- **LangChain** - LLM orchestration
- **Qdrant** - Vector database
- **Ollama** - Local LLM
- **Pydantic** - Data validation
- **pandas** - Data manipulation

See `requirements.txt` for full list.

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/name`
2. Commit changes: `git commit -am 'Add feature'`
3. Push to branch: `git push origin feature/name`
4. Submit pull request

## 📝 License

Proprietary - Zensar Technologies

## 📧 Support

For issues or questions:
1. Check logs: `tail -f app.log`
2. Review configuration in `config.py`
3. Check API docs: `http://localhost:8000/docs`

## 🔄 Version History

- **v1.0.0** (Current)
  - Device inventory analysis
  - Risk assessment
  - Migration recommendations
  - Admin panel
  - RAG integration

---

**Last Updated**: April 23, 2026
