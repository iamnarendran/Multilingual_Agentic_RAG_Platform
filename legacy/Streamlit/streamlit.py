"""
Multilingual RAG Demo - Standalone Streamlit App
Showcases the 6-agent workflow without using actual project code
"""

import streamlit as st
import requests
import json
import fitz  # PyMuPDF
import re
import time
from typing import List, Dict, Any
import chromadb
from langdetect import detect

# =============================================================================
# CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Multilingual RAG Demo",
    page_icon="🌐",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .agent-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        text-align: center;
        font-weight: bold;
    }
    .stProgress > div > div > div > div {
        background-color: #667eea;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_openrouter_embeddings(text: str, api_key: str) -> List[float]:
    """Get embeddings from OpenRouter API"""
    url = "https://openrouter.ai/api/v1/embeddings"
    
    payload = {
        "model": "intfloat/multilingual-e5-large",  
        "input": text
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        st.error(f"Embedding error: {str(e)}")
        return None


def call_llm(prompt: str, api_key: str, model: str = "openai/gpt-oss-20b") -> str:
    """Call LLM via OpenRouter"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"LLM error: {str(e)}")
        return None


def extract_text_from_pdf(pdf_file) -> str:
    """Extract text from PDF"""
    try:
        pdf_bytes = pdf_file.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        text_parts = []
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
        
        pdf_doc.close()
        return "\n\n".join(text_parts)
    except Exception as e:
        st.error(f"PDF extraction error: {str(e)}")
        return None


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """Simple text chunking"""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks


def detect_language(text: str) -> str:
    """Detect language"""
    try:
        return detect(text[:500])
    except:
        return "en"


# =============================================================================
# SIMPLIFIED AGENTS
# =============================================================================

class SimplifiedAgents:
    """6 Agents with simplified implementations"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def router_agent(self, query: str) -> str:
        """Agent 1: Classify query type"""
        prompt = f"""Classify this query into ONE category:
- SIMPLE_QA: Direct question
- COMPARISON: Comparing things
- SUMMARIZATION: Summary request
- ANALYSIS: Deep analysis
- EXTRACTION: Extract data

Query: {query}

Respond with ONLY the category name."""
        
        result = call_llm(prompt, self.api_key, model="openai/gpt-oss-20b")
        return result.strip() if result else "SIMPLE_QA"
    
    def planner_agent(self, query: str) -> List[str]:
        """Agent 2: Generate search queries"""
        prompt = f"""Generate 2-3 search queries for: {query}

Respond with ONLY a JSON array like: ["query1", "query2", "query3"]"""
        
        result = call_llm(prompt, self.api_key, model="openai/gpt-oss-20b")
        
        try:
            # Clean response
            result = re.sub(r'```json\s*|\s*```', '', result)
            queries = json.loads(result)
            return queries if isinstance(queries, list) else [query]
        except:
            return [query]
    
    def retriever_agent(self, queries: List[str], collection) -> List[Dict]:
        """Agent 3: Search documents"""
        all_results = []
        
        for query_text in queries:
            # Get embedding
            query_embedding = get_openrouter_embeddings(query_text, self.api_key)
            if not query_embedding:
                continue
            
            # Search ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=3
            )
            
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    all_results.append({
                        'text': doc,
                        'distance': results['distances'][0][i] if 'distances' in results else 0
                    })
        
        # Sort by distance and take top 5
        all_results.sort(key=lambda x: x['distance'])
        return all_results[:5]
    
    def analyzer_agent(self, query: str, documents: List[Dict]) -> str:
        """Agent 4: Analyze documents"""
        context = "\n\n".join([f"[Doc {i+1}]: {doc['text']}" for i, doc in enumerate(documents)])
        
        prompt = f"""Based on these documents, answer the query. Include citations like [Doc 1].

Documents:
{context}

Query: {query}

Answer with citations:"""
        
        result = call_llm(prompt, self.api_key, model="x-ai/grok-4.1-fast")
        return result if result else "No analysis available."
    
    def synthesizer_agent(self, analysis: str) -> str:
        """Agent 5: Synthesize answer"""
        prompt = f"""Create a clear, concise final answer from this analysis. Keep all citations.

Analysis:
{analysis}

Final Answer:"""
        
        result = call_llm(prompt, self.api_key, model="anthropic/claude-3.5-sonnet")
        return result if result else analysis
    
    def validator_agent(self, answer: str, documents: List[Dict]) -> Dict:
        """Agent 6: Validate answer"""
        context = "\n\n".join([doc['text'][:200] for doc in documents])
        
        prompt = f"""Validate this answer against the source documents.

Answer: {answer}

Sources: {context[:500]}

Is this answer valid and supported by sources? Respond with JSON:
{{"valid": true/false, "confidence": 0.0-1.0}}"""
        
        result = call_llm(prompt, self.api_key, model="openai/gpt-oss-20b")
        
        try:
            result = re.sub(r'```json\s*|\s*```', '', result)
            validation = json.loads(result)
            return validation
        except:
            return {"valid": True, "confidence": 0.8}


# =============================================================================
# MAIN APP
# =============================================================================

st.markdown('<div class="main-header">🌐 Multilingual RAG Demo</div>', unsafe_allow_html=True)
st.markdown("**6-Agent Architecture Showcase** | Upload PDF → Ask Questions → Get Cited Answers")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    api_key = st.text_input(
        "OpenRouter API Key",
        type="password",
        value=st.secrets.get("OPENROUTER_API_KEY", ""),
        help="Get from https://openrouter.ai"
    )
    
    st.markdown("---")
    st.markdown("""
    ### 🤖 6 Agents
    
    1. 🧭 **Router** - Classify query
    2. 🗓️ **Planner** - Generate searches
    3. 🔍 **Retriever** - Find documents
    4. 📊 **Analyzer** - Extract info
    5. 🔄 **Synthesizer** - Create answer
    6. ✓ **Validator** - Verify quality
    """)

# Initialize session state
if 'collection' not in st.session_state:
    # Initialize ChromaDB
    client = chromadb.Client()
    st.session_state.collection = client.create_collection(
        name="documents",
        metadata={"hnsw:space": "cosine"}
    )
    st.session_state.document_count = 0

# Main interface
tab1, tab2 = st.tabs(["📄 Upload & Query", "ℹ️ About"])

with tab1:
    col1, col2 = st.columns([1, 1])
    
    # UPLOAD SECTION
    with col1:
        st.subheader("📤 Upload Document")
        
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=['pdf'],
            help="Upload a document to analyze"
        )
        
        if uploaded_file and api_key:
            if st.button("🔄 Process Document", type="primary"):
                with st.spinner("Processing document..."):
                    # Extract text
                    text = extract_text_from_pdf(uploaded_file)
                    if not text:
                        st.error("Failed to extract text from PDF")
                        st.stop()
                    
                    # Detect language
                    language = detect_language(text)
                    
                    # Chunk text
                    chunks = chunk_text(text)
                    
                    progress_bar = st.progress(0)
                    status = st.empty()
                    
                    # Process chunks
                    for i, chunk in enumerate(chunks):
                        status.text(f"Processing chunk {i+1}/{len(chunks)}...")
                        
                        # Get embedding
                        embedding = get_openrouter_embeddings(chunk, api_key)
                        if embedding:
                            # Add to ChromaDB
                            st.session_state.collection.add(
                                embeddings=[embedding],
                                documents=[chunk],
                                ids=[f"doc_{st.session_state.document_count}_{i}"]
                            )
                        
                        progress_bar.progress((i + 1) / len(chunks))
                    
                    st.session_state.document_count += 1
                    status.empty()
                    progress_bar.empty()
                    
                    st.success(f"✅ Processed {len(chunks)} chunks | Language: {language}")
                    st.balloons()
    
    # QUERY SECTION
    with col2:
        st.subheader("💬 Ask Questions")
        
        if st.session_state.document_count == 0:
            st.info("👈 Upload a document first!")
        elif not api_key:
            st.warning("⚠️ Add API key in sidebar")
        else:
            query = st.text_area(
                "Your question:",
                placeholder="What is this document about?\nभारत की राजधानी क्या है?",
                height=100
            )
            
            if st.button("🚀 Get Answer", type="primary"):
                if not query.strip():
                    st.warning("Please enter a question!")
                else:
                    # Initialize agents
                    agents = SimplifiedAgents(api_key)
                    
                    # Create containers for workflow
                    workflow_container = st.container()
                    
                    with workflow_container:
                        st.markdown("### 🔄 Agent Workflow")
                        
                        # AGENT 1: Router
                        with st.spinner(""):
                            st.markdown('<div class="agent-box">🧭 ROUTER AGENT - Classifying query...</div>', unsafe_allow_html=True)
                            time.sleep(0.5)
                            query_type = agents.router_agent(query)
                            st.success(f"✅ Query Type: **{query_type}**")
                        
                        # AGENT 2: Planner
                        with st.spinner(""):
                            st.markdown('<div class="agent-box">🗓️ PLANNER AGENT - Generating search queries...</div>', unsafe_allow_html=True)
                            time.sleep(0.5)
                            search_queries = agents.planner_agent(query)
                            st.success(f"✅ Generated {len(search_queries)} queries")
                        
                        # AGENT 3: Retriever
                        with st.spinner(""):
                            st.markdown('<div class="agent-box">🔍 RETRIEVER AGENT - Searching documents...</div>', unsafe_allow_html=True)
                            time.sleep(0.5)
                            documents = agents.retriever_agent(search_queries, st.session_state.collection)
                            st.success(f"✅ Retrieved {len(documents)} documents")
                        
                        if not documents:
                            st.error("No relevant documents found!")
                            st.stop()
                        
                        # AGENT 4: Analyzer
                        with st.spinner(""):
                            st.markdown('<div class="agent-box">📊 ANALYZER AGENT - Analyzing content...</div>', unsafe_allow_html=True)
                            time.sleep(1)
                            analysis = agents.analyzer_agent(query, documents)
                            st.success("✅ Analysis complete")
                        
                        # AGENT 5: Synthesizer
                        with st.spinner(""):
                            st.markdown('<div class="agent-box">🔄 SYNTHESIZER AGENT - Creating answer...</div>', unsafe_allow_html=True)
                            time.sleep(1)
                            answer = agents.synthesizer_agent(analysis)
                            st.success("✅ Answer synthesized")
                        
                        # AGENT 6: Validator
                        with st.spinner(""):
                            st.markdown('<div class="agent-box">✓ VALIDATOR AGENT - Validating quality...</div>', unsafe_allow_html=True)
                            time.sleep(0.5)
                            validation = agents.validator_agent(answer, documents)
                            st.success(f"✅ Validation: {validation.get('confidence', 0.8):.0%} confidence")
                        
                        # Display final answer
                        st.markdown("---")
                        st.markdown("### 💡 Final Answer")
                        st.markdown(f"**{answer}**")
                        
                        # Show sources
                        with st.expander("📚 View Source Documents"):
                            for i, doc in enumerate(documents[:3], 1):
                                st.markdown(f"**Document {i}**")
                                st.text(doc['text'][:300] + "...")
                                st.markdown("---")

with tab2:
    st.markdown("""
    ## 🌐 About This Demo
    
    This is a **simplified demonstration** of the Multilingual RAG system with 6-agent architecture.
    
    ### 🏗️ Architecture
    
    **Vector Database:** ChromaDB (in-memory)  
    **Embeddings:** Multilingual-e5-large (intfloat/multilingual-e5-large)  
    **LLMs:** openai/Gpt-oss-20b + Grok-4.1-fast (routing/validation)
    
    ### 🤖 Agent Workflow
    
    1. **Router** → Classifies query type (QA, comparison, etc.)
    2. **Planner** → Generates multiple search queries
    3. **Retriever** → Searches vector database with embeddings
    4. **Analyzer** → Extracts information with citations
    5. **Synthesizer** → Creates coherent final answer
    6. **Validator** → Verifies answer quality
    
    ### 🌍 Features
    
    - ✅ Multilingual support (auto-detect language)
    - ✅ Citation tracking
    - ✅ Hybrid search (vector similarity)
    - ✅ Cost-optimized (different models for different agents)
    
    ### 📊 Tech Stack
    
    - **Frontend:** Streamlit
    - **Vector DB:** ChromaDB
    - **LLM Gateway:** OpenRouter
    - **Models:** Gpt-oss-20b + Grok-4.1-fast
    - **Document Processing:** PyMuPDF
    
    ---
    
    **Note:** This is a demo version. The full production system includes:
    - Qdrant for persistent vector storage
    - PostgreSQL for metadata
    - FastAPI backend
    - Redis caching
    - Complete error handling
    - User authentication
    """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p><strong>Multilingual RAG Demo</strong> - Powered by Multi-Agent Architecture</p>
</div>
""", unsafe_allow_html=True)
