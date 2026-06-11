import os
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .config import *

embeddings = OllamaEmbeddings(model=MODEL)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

def get_path(session_id):
    return f"{MEMORY_BASE_PATH}/{session_id}"

def load_or_create(session_id):
    path = get_path(session_id)
    if os.path.exists(path):
        return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)
    return None

def store_document(session_id, content):
    chunks = splitter.split_text(content)

    store = load_or_create(session_id)
    if store:
        store.add_texts(chunks)
    else:
        store = FAISS.from_texts(chunks, embeddings)

    os.makedirs(get_path(session_id), exist_ok=True)
    store.save_local(get_path(session_id))

def retrieve_memory(session_id, query):
    store = load_or_create(session_id)
    if not store:
        return ""

    docs = store.similarity_search(query, k=MEMORY_TOP_K)
    return "\n\n".join([d.page_content for d in docs])
