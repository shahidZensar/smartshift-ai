"""
Admin endpoints for managing vector database, files, URLs, and MySQL data import
"""
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from pathlib import Path
import os
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
import aiofiles
import requests
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from .rag import vectorstore_manager
from . import logger
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from .config import MYSQL_URI

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

# Configuration
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.md', '.csv', '.xlsx', '.xls'}

# ==================== Utility Functions ====================

def format_file_size(bytes_size: int) -> str:
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

async def save_uploaded_file(file: UploadFile, directory: Path) -> Dict[str, Any]:
    """Save uploaded file to disk"""
    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {format_file_size(MAX_FILE_SIZE)}"
        )
    
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Save file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
    safe_filename = timestamp + file.filename.replace(" ", "_")
    file_path = directory / safe_filename
    
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(contents)
    
    logger.info(f"File uploaded: {file.filename} -> {safe_filename}")
    
    return {
        "filename": file.filename,
        "saved_as": safe_filename,
        "size": len(contents),
        "size_formatted": format_file_size(len(contents)),
        "path": str(file_path),
        "type": file.content_type,
        "timestamp": datetime.now().isoformat()
    }

def load_documents_from_file(file_path: Path) -> List[Any]:
    """Load and parse documents from file"""
    file_ext = file_path.suffix.lower()
    
    try:
        if file_ext == '.pdf':
            loader = PyPDFLoader(str(file_path))
            documents = loader.load()
        elif file_ext in ['.docx', '.doc']:
            # .docx is a binary (zip) container — it must NOT be read as text.
            loader = Docx2txtLoader(str(file_path))
            documents = loader.load()
        elif file_ext in ['.txt', '.md']:
            # autodetect_encoding so non-UTF-8 text files don't crash the loader.
            loader = TextLoader(str(file_path), autodetect_encoding=True)
            documents = loader.load()
        else:
            # Fallback: read as text (ignore undecodable bytes rather than crash).
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            from langchain_core.documents import Document
            documents = [Document(page_content=text, metadata={"source": str(file_path)})]
        
        # Split documents into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        
        chunks = splitter.split_documents(documents)
        logger.info(f"Loaded {len(chunks)} chunks from {file_path.name}")
        return chunks
    
    except Exception as e:
        logger.error(f"Error loading documents from {file_path}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )

def load_documents_from_url(url: str) -> List[Any]:
    """Load documents from URL"""
    try:
        logger.info(f"Fetching content from URL: {url}")
        loader = WebBaseLoader(url)
        documents = loader.load()
        
        # Split documents into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        
        chunks = splitter.split_documents(documents)
        logger.info(f"Loaded {len(chunks)} chunks from {url}")
        return chunks
    
    except Exception as e:
        logger.error(f"Error loading documents from {url}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching URL: {str(e)}"
        )

def load_csv_to_dataframe(file_path: Path) -> pd.DataFrame:
    """Load CSV or Excel file to pandas DataFrame"""
    try:
        file_ext = file_path.suffix.lower()
        
        if file_ext == '.csv':
            df = pd.read_csv(file_path)
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        logger.info(f"Loaded {len(df)} rows from {file_path.name}")
        return df
    
    except Exception as e:
        logger.error(f"Error loading CSV/Excel: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing file: {str(e)}"
        )

def import_to_mysql(df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
    """Import DataFrame to MySQL database"""
    try:
        # Validate table name
        if not table_name or not table_name.replace('_', '').isalnum():
            raise ValueError("Invalid table name. Only alphanumeric and underscore allowed.")
        
        engine = create_engine(MYSQL_URI)
        
        # Convert DataFrame columns to appropriate types
        # Replace NaN with None for proper NULL handling
        df = df.where(pd.notna(df), None)
        
        # Clean column names (lowercase, replace spaces with underscores)
        df.columns = [col.lower().replace(' ', '_').replace('-', '_') for col in df.columns]
        
        # Import to database
        # if_exists options: 'fail', 'replace', 'append'
        df.to_sql(
            table_name,
            con=engine,
            if_exists='append',  # Append to existing table or create new
            index=False,
            method='multi',
            chunksize=1000
        )
        
        logger.info(f"Imported {len(df)} rows to MySQL table '{table_name}'")
        
        return {
            "rows_imported": len(df),
            "columns": len(df.columns),
            "table_name": table_name,
            "column_names": list(df.columns)
        }
    
    except Exception as e:
        logger.error(f"Error importing to MySQL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing data: {str(e)}"
        )

def get_mysql_tables() -> List[str]:
    """Get list of tables in MySQL database"""
    try:
        engine = create_engine(MYSQL_URI)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return tables
    except Exception as e:
        logger.error(f"Error retrieving tables: {str(e)}")
        return []

def get_table_schema(table_name: str) -> Dict[str, Any]:
    """Get schema information for a MySQL table"""
    try:
        engine = create_engine(MYSQL_URI)
        inspector = inspect(engine)
        
        columns = inspector.get_columns(table_name)
        column_info = [
            {
                "name": col['name'],
                "type": str(col['type']),
                "nullable": col['nullable']
            }
            for col in columns
        ]
        
        return {
            "table_name": table_name,
            "columns": column_info,
            "column_count": len(column_info)
        }
    except Exception as e:
        logger.error(f"Error getting table schema: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error getting table schema: {str(e)}"
        )

# ==================== API Endpoints ====================

@admin_router.post("/upload-file")
async def upload_file_to_db(
    file: UploadFile = File(...),
    auto_index: bool = Form(True)
) -> Dict[str, Any]:
    """
    Upload a file and optionally index it to the vector database
    
    Supported formats: PDF, TXT, DOCX, MD, CSV
    """
    try:
        # Save file
        file_info = await save_uploaded_file(file, UPLOAD_DIR)
        
        # Index to vector store if requested
        if auto_index:
            file_path = Path(file_info['path'])
            documents = load_documents_from_file(file_path)
            
            if documents:
                vectorstore_manager.add_documents(documents)
                file_info['indexed'] = True
                file_info['chunks_added'] = len(documents)
                logger.info(f"Added {len(documents)} chunks to vector store")
            else:
                file_info['indexed'] = False
                file_info['chunks_added'] = 0
        else:
            file_info['indexed'] = False
            file_info['chunks_added'] = 0
        
        return {
            "status": "success",
            "message": "File uploaded successfully",
            "file": file_info
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading file: {str(e)}"
        )

@admin_router.post("/upload-url")
async def upload_url_to_db(
    url: str = Form(...),
    auto_index: bool = Form(True)
) -> Dict[str, Any]:
    """
    Fetch content from URL and optionally index it to the vector database
    """
    try:
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(
                status_code=400,
                detail="Invalid URL. Must start with http:// or https://"
            )
        
        # Load and process content
        documents = load_documents_from_url(url)
        
        # Index to vector store if requested
        if auto_index and documents:
            vectorstore_manager.add_documents(documents)
            logger.info(f"Added {len(documents)} chunks to vector store from URL")
        
        return {
            "status": "success",
            "message": "URL content loaded and indexed successfully",
            "url": url,
            "chunks_added": len(documents) if auto_index else 0,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing URL: {str(e)}"
        )

@admin_router.get("/uploaded-files")
async def list_uploaded_files() -> Dict[str, Any]:
    """List all uploaded files"""
    try:
        files = []
        if UPLOAD_DIR.exists():
            for file_path in UPLOAD_DIR.glob("*"):
                if file_path.is_file():
                    stat = file_path.stat()
                    files.append({
                        "filename": file_path.name,
                        "size": stat.st_size,
                        "size_formatted": format_file_size(stat.st_size),
                        "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "path": str(file_path)
                    })
        
        return {
            "status": "success",
            "count": len(files),
            "files": sorted(files, key=lambda x: x['uploaded_at'], reverse=True)
        }
    
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing files: {str(e)}"
        )

@admin_router.delete("/uploaded-files/{filename}")
async def delete_uploaded_file(filename: str) -> Dict[str, Any]:
    """Delete an uploaded file"""
    try:
        # Prevent directory traversal
        if "/" in filename or "\\" in filename or filename.startswith(".."):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename"
            )
        
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )
        
        file_path.unlink()
        logger.info(f"Deleted file: {filename}")
        
        return {
            "status": "success",
            "message": f"File deleted: {filename}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting file: {str(e)}"
        )

@admin_router.post("/refresh-index")
async def refresh_index(
    reindex_all: bool = Form(False)
) -> Dict[str, Any]:
    """
    Rebuild the vector index from uploaded files
    
    If reindex_all is True, clears existing index and rebuilds from all files
    """
    try:
        logger.info("Starting index refresh...")
        
        if reindex_all:
            # Clear existing index (by creating new instance)
            from .rag import vectorstore, OllamaEmbeddings, FAISS
            import faiss
            embeddings = OllamaEmbeddings(model="my_model:latest")
            embedding_size = 1536
            index = faiss.IndexFlatL2(embedding_size)
            from langchain_community.docstore import InMemoryDocstore
            vectorstore_manager.vectorstore = FAISS(
                embedding_function=embeddings,
                index=index,
                docstore=InMemoryDocstore({}),
                index_to_docstore_id={}
            )
            logger.info("Cleared existing vector index")
        
        # Index all files
        total_chunks = 0
        indexed_files = []
        
        if UPLOAD_DIR.exists():
            for file_path in UPLOAD_DIR.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in ALLOWED_EXTENSIONS:
                    try:
                        documents = load_documents_from_file(file_path)
                        if documents:
                            vectorstore_manager.add_documents(documents)
                            total_chunks += len(documents)
                            indexed_files.append({
                                "file": file_path.name,
                                "chunks": len(documents)
                            })
                    except Exception as e:
                        logger.warning(f"Skipped file {file_path.name}: {str(e)}")
        
        logger.info(f"Index refresh complete: {total_chunks} chunks from {len(indexed_files)} files")
        
        return {
            "status": "success",
            "message": "Vector index refreshed successfully",
            "total_chunks": total_chunks,
            "files_indexed": len(indexed_files),
            "files": indexed_files,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error refreshing index: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error refreshing index: {str(e)}"
        )

@admin_router.get("/vector-db-stats")
async def get_vector_db_stats() -> Dict[str, Any]:
    """Get statistics about the vector database"""
    try:
        # Get index size info
        file_count = 0
        total_size = 0
        
        if UPLOAD_DIR.exists():
            for file_path in UPLOAD_DIR.glob("*"):
                if file_path.is_file():
                    file_count += 1
                    total_size += file_path.stat().st_size
        
        return {
            "status": "success",
            "vector_database": {
                "uploaded_files": file_count,
                "total_size": total_size,
                "total_size_formatted": format_file_size(total_size),
                "upload_directory": str(UPLOAD_DIR)
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting stats: {str(e)}"
        )

@admin_router.post("/import-csv-to-mysql")
async def import_csv_to_mysql(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    replace_table: bool = Form(False)
) -> Dict[str, Any]:
    """
    Upload CSV/Excel file and import to MySQL database
    
    Supported formats: CSV, XLSX, XLS
    """
    try:
        # Save file temporarily
        file_info = await save_uploaded_file(file, UPLOAD_DIR)
        file_path = Path(file_info['path'])
        
        # Load to DataFrame
        df = load_csv_to_dataframe(file_path)
        
        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="CSV file is empty"
            )
        
        # Import to MySQL
        import_info = import_to_mysql(df, table_name)
        
        return {
            "status": "success",
            "message": f"Successfully imported {len(df)} rows to MySQL table '{table_name}'",
            "file": {
                "original_name": file_info['filename'],
                "saved_as": file_info['saved_as'],
                "size": file_info['size'],
                "rows": len(df)
            },
            "import": import_info,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing CSV to MySQL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing CSV: {str(e)}"
        )

@admin_router.get("/mysql-tables")
async def get_mysql_tables_list() -> Dict[str, Any]:
    """Get list of all tables in MySQL database"""
    try:
        tables = get_mysql_tables()
        return {
            "status": "success",
            "tables": tables,
            "count": len(tables),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting tables: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving tables: {str(e)}"
        )

@admin_router.get("/mysql-table-schema/{table_name}")
async def get_table_schema_endpoint(table_name: str) -> Dict[str, Any]:
    """Get schema information for a specific MySQL table"""
    try:
        schema = get_table_schema(table_name)
        return {
            "status": "success",
            "schema": schema,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting table schema: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving schema: {str(e)}"
        )

@admin_router.get("/health")
async def admin_health() -> Dict[str, str]:
    """Health check for admin endpoints"""
    return {
        "status": "healthy",
        "service": "admin",
        "timestamp": datetime.now().isoformat()
    }

