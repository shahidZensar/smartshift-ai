# Installing LLAMA CPP
## follow the below steps.
- Clone llama Repo
```bash
git clone https://github.com/ggml-org/llama.cpp
```
- After Clone Execute below commands
```bash
 #For https support
 sudo apt install libcurl4-openssl-dev
 # Dependences
 sudo apt install build-essential
 #CPU 
 cmake -B build
 #https support build
 cmake -B build -DLLAMA_CURL=ON
 #OpenSSL Support
 cmake -B build -DLLAMA_BUILD_BORINGSSL=ON
 cmake -B build -DLLAMA_BUILD_LIBRESSL=ON
 cmake -B build -DLLAMA_OPENSSL=ON
 cmake --build build --config Release
 #GPU 
 cmake -B build -DGGML_CUDA=ON
 cmake --build build --config Release
```
- Download gguf models using hf(huggingface_hub cli)
```bash
  #Meta-Llama-3-8B-Instruct-GGUF
  hf download bartowski/Meta-Llama-3-8B-Instruct-GGUF \
  --include "Meta-Llama-3-8B-Instruct-Q4_K_M.gguf"  --local-dir ./models/
  #Gamma
  hf download ggml-org/gemma-3-1b-it-GGUF --include "*Q4_K_M.gguf" --local-dir ./models/
  #Embedding model
  hf download nomic-ai/nomic-embed-text-v1.5-GGUF \
  --include "nomic-embed-text-v1.5.Q4_K_M.gguf" \
  --local-dir .
```  
Ref [Link Hugging Face](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF#:~:text=text%2Dv1.5-,Usage,Compute%20multiple%20embeddings:)
