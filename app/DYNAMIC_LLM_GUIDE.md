# Dynamic LLM Initialization - Usage Guide

## Overview

The `decision.py` file now includes a factory function `create_llm_instance()` that dynamically creates LLM instances based on the selected model provider. This allows seamless switching between different LLM backends without code changes.

## Supported Providers

1. **Ollama** - Local open-source models
2. **OpenAI** - Cloud-based GPT models
3. **LocalAI** - Local OpenAI-compatible server
4. **Azure** - Azure OpenAI service

## Configuration

Set the provider via environment variable:

```bash
# Option 1: Ollama (default)
export ENV=ollama
export MODEL=llama3.2:3b
export OLLAMA_BASE_URL=http://localhost:11434

# Option 2: OpenAI
export ENV=openai
export OPENAI_API_KEY=sk-xxx...
export MODEL=gpt-3.5-turbo

# Option 3: LocalAI
export ENV=localai
export LOCALAI_BASE_URL=http://localhost:8080/v1
export LOCALAI_API_KEY=xxx

# Option 4: Azure OpenAI
export ENV=azure
export AZURE_OPENAI_API_KEY=xxx
export AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
```

## Environment Files

Create `.env.{provider}` files in the app directory:

### `.env.ollama` (Local Development)
```env
MODEL_PROVIDER=ollama
MODEL=llama3.2:3b
BASE_URL=http://localhost:11434
TEMPERATURE=0.7
TOP_P=0
EMBEDDING_MODEL=nomic-embed-text:latest
```

### `.env.openai` (Production)
```env
MODEL_PROVIDER=openai
MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-xxx...
TEMPERATURE=0.7
TOP_P=0.9
```

### `.env.localai` (Local with OpenAI API)
```env
MODEL_PROVIDER=localai
MODEL=gpt4all
LOCALAI_BASE_URL=http://localhost:8080/v1
LOCALAI_API_KEY=xxx
TEMPERATURE=0.7
TOP_P=0
```

### `.env.azure` (Azure OpenAI)
```env
MODEL_PROVIDER=azure
MODEL=gpt-4
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
TEMPERATURE=0.7
TOP_P=0
```

## Code Structure

### Factory Function

```python
def create_llm_instance(provider=None, model=None, temperature=None, top_p=None, **kwargs):
    """
    Create LLM instance dynamically based on provider.
    
    Args:
        provider: 'ollama', 'openai', 'localai', 'azure'
        model: Model name/ID
        temperature: Sampling temperature
        top_p: Nucleus sampling
        **kwargs: Provider-specific options
    
    Returns:
        LLM instance from LangChain
    """
```

### Default Initialization

```python
# Automatic initialization from config
llm = create_llm_instance()              # Uses MODEL_PROVIDER from config

# Custom initialization
llm = create_llm_instance(
    provider='openai',
    model='gpt-4',
    temperature=0.7,
    timeout=600
)

# With credentials
llm = create_llm_instance(
    provider='openai',
    api_key='sk-xxx...',
    model='gpt-4'
)
```

## Usage Examples

### Example 1: Switch from Ollama to OpenAI

**Before (static):**
```python
# Old approach - hardcoded
llm = OllamaLLM(model="llama3.2:3b", base_url="http://localhost:11434")
openai_llm = ChatOpenAI(model="gpt-3.5-turbo")  # Separate init
```

**After (dynamic):**
```python
# New approach - automatic
llm = create_llm_instance()  # Uses config

# Just change ENV and MODEL in .env file
# No code changes needed!
```

### Example 2: Runtime Provider Selection

```python
# Get provider from environment or parameter
provider = os.getenv('MODEL_PROVIDER', 'ollama')

# Create appropriate instance
llm = create_llm_instance(provider=provider)

# Use the same llm instance regardless of provider
response = llm.invoke("What devices are end-of-support?")
```

### Example 3: Multiple Instances with Different Providers

```python
# Analysis LLM - using production OpenAI
analysis_llm = create_llm_instance(
    provider='openai',
    model='gpt-4',
    temperature=0.5
)

# SQL generation LLM - using local Ollama (faster)
sql_llm = create_llm_instance(
    provider='ollama',
    model='mistral:latest'
)

# Use both in your application
analysis = analysis_llm.invoke(question)
sql_query = sql_llm.invoke(sql_prompt)
```

## Provider-Specific Features

### Ollama
- **Use Case**: Local development, privacy-focused
- **Models**: llama3.2, mistral, phi, etc.
- **Pros**: No API key, fast local inference
- **Cons**: Requires local setup, slower than cloud

**Config:**
```env
MODEL_PROVIDER=ollama
BASE_URL=http://localhost:11434
```

### OpenAI
- **Use Case**: Production, maximum accuracy
- **Models**: gpt-4, gpt-3.5-turbo
- **Pros**: State-of-the-art performance
- **Cons**: Requires API key, costs money

**Config:**
```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-xxx...
```

### LocalAI
- **Use Case**: Self-hosted OpenAI-compatible
- **Models**: Various (gpt4all, etc.)
- **Pros**: Local, OpenAI-compatible API
- **Cons**: More setup than Ollama

**Config:**
```env
MODEL_PROVIDER=localai
LOCALAI_BASE_URL=http://localhost:8080/v1
```

### Azure OpenAI
- **Use Case**: Enterprise Azure deployment
- **Models**: gpt-4, gpt-35-turbo
- **Pros**: Enterprise support, compliance
- **Cons**: Azure-specific, additional setup

**Config:**
```env
MODEL_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_API_KEY=xxx
```

## Logging & Debugging

The factory function provides detailed logging:

```
Creating LLM instance: provider='ollama', model='llama3.2:3b', temperature=0.7
✓ Ollama LLM initialized: llama3.2:3b at http://localhost:11434
All LLM instances initialized successfully. Provider: ollama, Model: llama3.2:3b
```

### Troubleshooting

**Issue**: "OPENAI_API_KEY not found"
```bash
export OPENAI_API_KEY=sk-xxx...
# or add to .env.openai file
```

**Issue**: "Connection refused" to Ollama
```bash
# Check Ollama is running
curl http://localhost:11434/api/tags
# Start Ollama
ollama serve
```

**Issue**: "Unsupported LLM provider"
```python
# Ensure provider is one of: ollama, openai, localai, azure
provider = os.getenv('MODEL_PROVIDER', 'ollama').lower()
```

## Initialization Order

The application initializes LLM instances in this order:

1. **Primary LLM** - `llm = create_llm_instance()`
   - Used for main device analysis
   - Uses MODEL_PROVIDER from config

2. **SQL LLM** - `sql_llm = create_llm_instance()`
   - Used for SQL query generation
   - Same provider as primary

3. **Chat LLM** - `llm_chat = create_llm_instance()`
   - Used for conversation
   - Same provider as primary

4. **OpenAI-Compatible LLM** - `openai_llm = create_llm_instance(provider=MODEL_PROVIDER)`
   - If provider is 'localai', 'openai', or 'azure'
   - Falls back to llm_chat for 'ollama'

## Performance Comparison

| Provider | Speed | Cost | Quality | Setup |
|----------|-------|------|---------|-------|
| Ollama | Fast (local) | Free | Good | Medium |
| OpenAI | Fast (cloud) | $$ | Excellent | Easy |
| LocalAI | Medium | Free | Good | Hard |
| Azure | Fast (cloud) | $$$ | Excellent | Hard |

## Best Practices

1. **Development**: Use Ollama (free, local)
   ```bash
   export ENV=ollama
   ```

2. **Testing**: Use smaller models
   ```bash
   export MODEL=phi:mini  # Faster testing
   ```

3. **Production**: Use OpenAI or Azure (better quality)
   ```bash
   export ENV=openai
   export MODEL=gpt-4
   ```

4. **Cost Optimization**: Use gpt-3.5-turbo for most tasks
   ```bash
   export MODEL=gpt-3.5-turbo  # More affordable
   ```

5. **Privacy**: Use Ollama or LocalAI (on-premise)
   ```bash
   export ENV=ollama  # No data leaves your server
   ```

## Advanced Usage

### Custom Temperature & Top-P

```python
# Conservative responses (deterministic)
llm = create_llm_instance(temperature=0, top_p=0)

# Creative responses (varied)
llm = create_llm_instance(temperature=0.9, top_p=0.9)

# Balanced
llm = create_llm_instance(temperature=0.7, top_p=0.9)
```

### Custom Timeout

```python
# For slow models
llm = create_llm_instance(timeout=300)  # 5 minutes

# For fast API
llm = create_llm_instance(timeout=30)   # 30 seconds
```

### Azure OpenAI with Specific Version

```python
llm = create_llm_instance(
    provider='azure',
    api_version='2024-02-15-preview'
)
```

## Migration Guide

### From Static to Dynamic

**Before:**
```python
# decision.py - hardcoded
llm = OllamaLLM(model=MODEL, base_url=BASE_URL)
```

**After:**
```python
# decision.py - dynamic
llm = create_llm_instance()

# Switch providers by changing ENV variable
```

No application code changes needed - just environment configuration!

---

**Benefits:**
✅ Single codebase for multiple providers
✅ Easy provider switching
✅ Reduced code duplication
✅ Better error handling
✅ Improved logging
✅ Support for 4 major LLM platforms

