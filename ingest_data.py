import os
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

# 1. Definir rutas
DATA_PATH = "data/"
CHROMA_PATH = "chroma_db/" # base de datos vectorial

def main():
    print("Iniciando procesamiento de documentos normativos...")
    
    # 2. Cargar los PDFs de la carpeta data/
    # PyPDFDirectoryLoader para leer todos los PDFs del directorio
    loader = PyPDFDirectoryLoader(DATA_PATH)
    documents = loader.load()
    
    if not documents:
         print(f"⚠️ No se encontraron documentos en la carpeta '{DATA_PATH}'. Por favor, agrega los manuales en formato PDF.")
         return
    
    print(f"✅ Se cargaron {len(documents)} páginas de contexto normativo.")

    # 3. Chunking
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200, 
        length_function=len
    )
    chunks = text_splitter.split_documents(documents)
    print(f"✅ Se generaron {len(chunks)} fragmentos de texto.")

    # 4. Embeddings / Save in ChromaDB

    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    
    print("⏳ Creando base de datos vectorial (esto puede tardar unos minutos la primera vez)...")
    db = Chroma.from_documents(
        chunks, 
        embeddings, 
        persist_directory=CHROMA_PATH
    )
    
    print(f"✅ Base de datos creada exitosamente en la carpeta '{CHROMA_PATH}'.")

if __name__ == "__main__":
    main()