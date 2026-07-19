import os
from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

def build_bolt_brain():
    # 1. Set your OpenAI API Key
    # Ensure this is set in your environment or defined here
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "your-openai-api-key-here"

    # 2. Load all markdown files from the memory/ folder
    loader = DirectoryLoader("./memory", glob="**/*.md")
    docs = loader.load()

    # 3. Split the documents into chunks
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(docs)

    # 4. Initialize embeddings and save to a persistent Chroma DB
    embeddings = OpenAIEmbeddings()
    persist_directory = "./chroma_db"
    
    db = Chroma.from_documents(
        documents=chunks, 
        embedding=embeddings, 
        persist_directory=persist_directory
    )
    
    return db

if __name__ == "__main__":
    # Build or load the database
    db = build_bolt_brain()
    print("Bolt Brain updated with your profile vibe!")
    
    # 5. Convert the database to a retriever to query it
    retriever = db.as_retriever()
    
    # Querying the system about your persona/voice
    query = "What is Billy's conversational voice?"
    results = retriever.invoke(query)
    
    # Print the relevant document chunks found
    for i, doc in enumerate(results):
        print(f"\n--- Result {i+1} ---")
        print(doc.page_content)
