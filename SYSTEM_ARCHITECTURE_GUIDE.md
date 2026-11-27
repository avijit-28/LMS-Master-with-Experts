# 🏛️ EduPlatform LMS — Complete System Architecture & Production Deployment Blueprint

> **Live Production URL:** [https://master-with-experts.runasp.net](https://master-with-experts.runasp.net)  
> **Live AI Assistant API:** [https://lms-ai-assistant.onrender.com](https://lms-ai-assistant.onrender.com)  
> **Live Observability (Grafana):** [https://wiseonion1173.grafana.net](https://wiseonion1173.grafana.net)  
> **Source Repository:** [https://github.com/avijit-28/LMS-Master-with-Experts.git](https://github.com/avijit-28/LMS-Master-with-Experts.git)  
> **Total Monthly Hosting Cost:** **$0.00 / month (100% Free Tiers)**

---

## 📌 Table of Contents
1. [High-Level Architecture (Graph View)](#1-high-level-architecture-graph-view)
2. [Component Inventory (Konsa, Kya Hai, Aur Kyun Hai)](#2-component-inventory-konsa-kya-hai-aur-kyun-hai)
3. [End-to-End Working Workflows](#3-end-to-end-working-workflows)
   - [Workflow A: Student AI Tutor & Real-time Semantic Caching](#workflow-a-student-ai-tutor--real-time-semantic-caching)
   - [Workflow B: Automatic PDF Upload & RAG Retained Learning](#workflow-b-automatic-pdf-upload--rag-retained-learning)
   - [Workflow C: Asynchronous Messaging & Dead-Letter Queue (DLQ)](#workflow-c-asynchronous-messaging--dead-letter-queue-dlq)
4. [Live Cloud Endpoints & Credentials Matrix](#4-live-cloud-endpoints--credentials-matrix)
5. [Environment Variables Reference (.env)](#5-environment-variables-reference-env)
6. [Troubleshooting & Maintenance Playbook](#6-troubleshooting--maintenance-playbook)

---

## 1. High-Level Architecture (Graph View)

```mermaid
flowchart TD
    subgraph CLIENTS ["🌐 Client Tier (Users & Devices)"]
        Student["👨‍🎓 Student Browser<br/>(/ChatBot, /Courses, /Learning)"]
        Instructor["👨‍🏫 Instructor Portal<br/>(/Instructor/Documents, /Studio)"]
        Admin["🛠️ Administrator<br/>(/Admin/Dashboard)"]
    end

    subgraph MONSTERASP ["☁️ Primary Web Tier (MonsterASP.NET IIS - Windows Server)"]
        IIS["🚀 ASP.NET MVC 5 Web App (.NET 4.8)<br/>URL: master-with-experts.runasp.net<br/>Let's Encrypt Free SSL (HTTPS)"]
        Controllers["Controllers: ChatBot, Instructor, Courses, Account"]
        AiClient["AiServiceClient (C# HTTP Client + Resilient Retry)"]
    end

    subgraph CLOUD_DB ["🗄️ Relational Database Tier (MonsterASP MSSQL)"]
        MSSQL[("💾 Microsoft SQL Server<br/>db81994.databaseasp.net<br/>35 Tables | Seed Users | Stored Procs")]
        ChunksTable["AiDocumentChunks & KnowledgeChunks"]
    end

    subgraph RENDER_AI ["🧠 AI Microservice Tier (Render Linux Container)"]
        FastAPI["⚡ FastAPI Python 3.11 Microservice<br/>URL: lms-ai-assistant.onrender.com"]
        PyMuPDF["📄 Document Extractor<br/>(PyMuPDF, Docx, Pptx)"]
        Qdrant[("🎯 Qdrant Vector DB<br/>Cosine Space (3072-dim)<br/>Collection: lms_course_knowledge")]
        SelfRAG["🛡️ Self-RAG & Prompt Guardrails<br/>(RBAC Boundary + Jailbreak Protection)"]
    end

    subgraph LLM_PROVIDERS ["🤖 Foundation Model Tier (Generative AI)"]
        Gemini["🟢 Primary: Google Gemini 3.1 Flash Lite<br/>(Context & Reasoning Tutor)"]
        GeminiEmbed["📐 Embedder: Gemini text-embedding-001<br/>(3072-Dimensional Dense Vectors)"]
        Groq["🟠 Failover: Groq Llama 3 / GPT-OSS 120B<br/>(< 800ms Sub-Second Failover)"]
    end

    subgraph UPSTASH ["⚡ Distributed In-Memory Cache (Upstash Cloud)"]
        Redis[("⚡ Upstash Serverless Redis<br/>Endpoint: noted-killdeer-140904.upstash.io:6379<br/>TLS rediss:// Enabled<br/>0-Token Semantic Cache Hits (<50ms)")]
    end

    subgraph CLOUDAMQP ["🐰 Distributed Message Broker (CloudAMQP)"]
        RabbitMQ["🐰 RabbitMQ 3.12 (Little Lemur Free Tier)<br/>Cluster: cow.rmq2.cloudamqp.com<br/>Queue: lms_document_ingestion_queue<br/>DLQ: lms_document_ingestion_dlq"]
    end

    subgraph GRAFANA ["📊 Observability Tier (Grafana Cloud)"]
        GrafanaDash["📈 Grafana Cloud Synthetic Probes<br/>URL: wiseonion1173.grafana.net<br/>Pings Web Portal & AI Service every 60s<br/>Global Uptime, Latency & SSL Countdown"]
    end

    %% Client Interactions
    Student -->|HTTPS Requests| IIS
    Instructor -->|Uploads PDF / Manages Courses| IIS
    Admin -->|Platform Operations| IIS

    %% Web App to DB & AI Microservice
    IIS --> Controllers
    Controllers <-->|Entity Framework 6| MSSQL
    Controllers --> AiClient
    AiClient <-->|REST API + X-Internal-API-Key| FastAPI

    %% AI Microservice Inner Workings
    FastAPI <-->|Check / Invalidate Cache| Redis
    FastAPI <-->|Vector Upsert & Search| Qdrant
    FastAPI -->|Extract Content| PyMuPDF
    FastAPI <-->|Dense Embeddings| GeminiEmbed
    FastAPI <-->|Primary Inference| Gemini
    FastAPI -.->|Automatic Failover on 429/503| Groq
    FastAPI -->|Publish Ingestion Jobs| RabbitMQ

    %% Database Chunks sync
    Controllers -.->|Native Fallback Parsing| ChunksTable

    %% Monitoring Connections
    GrafanaDash -.->|Global Health Pings| IIS
    GrafanaDash -.->|/api/v1/health Pings| FastAPI
```

---

## 2. Component Inventory (Konsa, Kya Hai, Aur Kyun Hai)

| Component | Platform / Host | Technology / Version | Role & Description (Kya Karta Hai) | Free Tier Limit |
|---|---|---|---|---|
| **LMS Web Application** | **MonsterASP.NET** | ASP.NET MVC 5 (.NET 4.8, C#) | Core user-facing portal: course catalog, student learning player, quiz engine, instructor studio, certificates PDF generator, and chatbot UI. | Free tier Windows IIS, Free SSL Let's Encrypt |
| **Relational Database** | **MonsterASP.NET** | Microsoft SQL Server 2022 | Stores users (ASP.NET Identity), 7 seeded courses, modules, lessons, enrollments, quizzes, payments, and document chunks. | 1 GB Free MSSQL DB |
| **AI Assistant Microservice** | **Render.com** | FastAPI / Python 3.11 (Docker) | High-performance RAG backend: handles query embedding, vector search, multi-turn chat, prompt security guardrails, and model cascading. | 750 free instance hours / month |
| **Primary LLM** | **Google AI Studio** | Gemini 3.1 Flash Lite (`gemini-3.1-flash-lite`) | Main intelligence engine: answers student inquiries, writes code snippets, analyzes curriculum, and provides step-by-step tutoring. | 15 RPM / 1M TPM free |
| **Dense Vector Embedder** | **Google AI Studio** | `gemini-embedding-001` | Converts text chunks and search queries into 3,072-dimensional vector representations for cosine similarity matching. | Included in Gemini Free Tier |
| **Failover LLM** | **Groq Cloud** | OpenAI GPT-OSS 120B / Llama 3 | Instant automated failover: if Gemini hits a rate limit (HTTP 429) or transient error, requests seamlessly route to Groq in <800ms. | Free developer tier |
| **Vector Database** | **Embedded on Render** | Qdrant Vector DB 1.8 | Stores 3072-dimensional dense vectors and metadata payloads on persistent disk for high-speed cosine similarity retrieval. | Runs inside container at $0 |
| **Distributed Cache** | **Upstash.com** | Serverless Cloud Redis | High-speed semantic cache. If a question with $\ge 95\%$ semantic similarity was asked previously, returns cached answer in **<50ms with 0 tokens** consumed. | 10,000 requests / day free |
| **Message Broker** | **CloudAMQP.com** | Managed RabbitMQ 3.12 | Handles asynchronous document ingestion queues and Dead-Letter Queues (DLQ) so heavy PDFs don't freeze the web server. | "Little Lemur" Free Plan (1M msgs/mo) |
| **Telemetry & Observability** | **Grafana Cloud** | Grafana Synthetic Monitoring | Pings both the Web App and the AI Service `/health` endpoint from global synthetic probe locations to track uptime, TTFB, and SSL expiry. | 10k metrics, 50GB logs free forever |

---

## 3. End-to-End Working Workflows

### Workflow A: Student AI Tutor & Real-time Semantic Caching

```mermaid
sequenceDiagram
    autonumber
    actor Student as 👨‍🎓 Student
    participant Web as 🌐 MonsterASP (C# MVC)
    participant AI as ⚡ Render (FastAPI)
    participant Redis as ⚡ Upstash Redis
    participant Qdrant as 🎯 Qdrant Vectorstore
    participant Gemini as 🟢 Gemini 3.1 Flash Lite
    participant Groq as 🟠 Groq (Failover)

    Student->>Web: Submits question in Chatbot widget
    Web->>AI: POST /api/v1/chat/ask (with X-Internal-API-Key)
    AI->>Redis: Check Semantic Cache for Course & Query Vector
    
    alt Semantic Cache Hit (Similarity >= 0.95)
        Redis-->>AI: Return cached answer & sources
        AI-->>Web: Return response (was_cache_hit=true, 0 tokens, <50ms)
        Web-->>Student: Display instant answer!
    else Semantic Cache Miss
        AI->>Qdrant: Hybrid Search (Dense Cosine + Sparse BM25 + RRF)
        Qdrant-->>AI: Return top relevant curriculum chunks
        AI->>AI: Self-RAG verification & guardrail checks
        
        alt Primary LLM Available
            AI->>Gemini: Generate pedagogical response with citations
            Gemini-->>AI: Structured response
        else Gemini Busy / Rate Limited (429)
            AI->>Groq: Failover request to Groq 120B
            Groq-->>AI: Fast failover response
        end

        AI->>Redis: Store (query_vector, answer) with 7-day TTL
        AI-->>Web: Return JSON (answer, citations, tokens, latency)
        Web-->>Student: Stream markdown response with course recommendations
    end
```

---

### Workflow B: Automatic PDF Upload & RAG Retained Learning

When an instructor uploads course lecture notes or a textbook PDF:

```mermaid
sequenceDiagram
    autonumber
    actor Instructor as 👨‍🏫 Instructor
    participant Web as 🌐 MonsterASP (C# MVC)
    participant SQL as 💾 MonsterASP MSSQL
    participant AI as ⚡ Render (FastAPI)
    participant PyMuPDF as 📄 PyMuPDF Extractor
    participant Embed as 📐 Gemini Embedder
    participant Qdrant as 🎯 Qdrant Vector DB
    participant Redis as ⚡ Upstash Redis

    Instructor->>Web: Uploads PDF via /Instructor/Documents
    Web->>Web: Saves local backup & converts bytes to Base64
    Web->>SQL: Insert AiDocument record (Status = "Processing")
    Web->>AI: POST /api/v1/documents/queue-index (Base64 file payload)
    
    AI->>PyMuPDF: Extract text, tables & page numbers
    PyMuPDF-->>AI: Structured pages & sections
    AI->>AI: Semantic Chunker splits text into ~600 char blocks
    AI->>Embed: Embed chunks via gemini-embedding-001 (3072-dim)
    Embed-->>AI: Dense float vectors
    AI->>Qdrant: Upsert vectors + metadata (course_id, doc_id, page_no)
    AI->>Redis: Invalidate cached answers for this Course ID
    AI-->>Web: HTTP 200 OK (status="Indexed", chunks_created=X)

    Web->>SQL: Update AiDocument (Status="Indexed", TotalChunks=X)
    Web->>SQL: Insert into AiDocumentChunks & KnowledgeChunks
    Web-->>Instructor: "Document uploaded and indexed successfully!"
    
    Note over Instructor,Redis: From this moment on, ANY student asking questions<br/>about this course gets answers directly from the newly uploaded PDF!
```

---

### Workflow C: Asynchronous Messaging & Dead-Letter Queue (DLQ)

For large 100+ page textbooks:
1. The ingestion job is published to CloudAMQP RabbitMQ queue `lms_document_ingestion_queue`.
2. The `document_worker.py` background consumer pulls the job, extracts pages, chunks, and embeds them without blocking user web requests.
3. If an encrypted or corrupted PDF fails extraction after 3 retries, RabbitMQ automatically routes the poisoned message to the Dead-Letter Exchange (`lms_dlx`) and Dead-Letter Queue (`lms_document_ingestion_dlq`), preventing worker crashes.

---

## 4. Live Cloud Endpoints & Credentials Matrix

| Service | Cloud Host | Endpoint / Connection String | Authentication Key / Credential |
|---|---|---|---|
| **LMS Web App** | MonsterASP | `https://master-with-experts.runasp.net` | Site: `site110204` |
| **MSSQL Database** | MonsterASP | `db81994.databaseasp.net` (internal)<br/>`db81994.public.databaseasp.net,1433` (external) | User: `db81994`<br/>Password: `F?e4yM6!X-b7` |
| **AI Microservice** | Render | `https://lms-ai-assistant.onrender.com` | Protected by `X-Internal-API-Key` |
| **Internal Shared Secret** | Render & LMS | Header: `X-Internal-API-Key` | `lms_rag_secret_auth_token_2026_xyz987` |
| **Upstash Redis (TCP)** | Upstash AWS Frankfurt | `noted-killdeer-140904.upstash.io:6379` | `rediss://default:gQAAAAAAAiZoAAIgcDFjYjljZTQwMWMzOTk0Zjk4ODExM2FjMzQ2ZTEwMGIyNw@noted-killdeer-140904.upstash.io:6379` |
| **Upstash Redis (REST)** | Upstash | `https://noted-killdeer-140904.upstash.io` | Bearer Token: `gQAAAAAAAiZoAAIgcDFjYjljZTQwMWMzOTk0Zjk4ODExM2FjMzQ2ZTEwMGIyNw` |
| **CloudAMQP RabbitMQ** | CloudAMQP AWS | `amqps://cow.rmq2.cloudamqp.com/gcmvslbz` | User: `gcmvslbz`<br/>Password: `v_0sesfMgraR6oo1m_WnFOle584aLRNd` |
| **Grafana Cloud** | Grafana Labs | `https://wiseonion1173.grafana.net` | Probes: `LMS-Live-Portal` & `LMS-AI-Microservice` |

---

## 5. Environment Variables Reference (.env)

These are configured in `AIService/.env`, root `.env`, and Render Dashboard:

```ini
# Security & RBAC Protection
AISERVICE_INTERNAL_KEY=lms_rag_secret_auth_token_2026_xyz987
ENABLE_PROMPT_GUARDRAILS=true

# Primary Generative Model (Google Gemini)
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
DEFAULT_LLM_PROVIDER=gemini

# Failover Generative Model (Groq)
GROQ_API_KEY=YOUR_GROQ_API_KEY
GROQ_MODEL=openai/gpt-oss-120b
FAILOVER_LLM_PROVIDER=groq

# Distributed Cloud Redis (Upstash)
REDIS_URL=rediss://default:gQAAAAAAAiZoAAIgcDFjYjljZTQwMWMzOTk0Zjk4ODExM2FjMzQ2ZTEwMGIyNw@noted-killdeer-140904.upstash.io:6379
UPSTASH_REDIS_REST_URL=https://noted-killdeer-140904.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAiZoAAIgcDFjYjljZTQwMWMzOTk0Zjk4ODExM2FjMzQ2ZTEwMGIyNw
ENABLE_SEMANTIC_CACHE=true
SEMANTIC_CACHE_SIMILARITY_THRESHOLD=0.95

# Distributed Message Broker (CloudAMQP RabbitMQ)
RABBITMQ_URL=amqps://gcmvslbz:v_0sesfMgraR6oo1m_WnFOle584aLRNd@cow.rmq2.cloudamqp.com/gcmvslbz

# Hybrid Search Parameters
HYBRID_SEARCH_TOP_K=8
RRF_K=60
DENSE_WEIGHT=0.65
SPARSE_WEIGHT=0.35
```

---

## 6. Troubleshooting & Maintenance Playbook

### Q1: How do I test if the AI Assistant is online?
Run this curl command in your terminal:
```powershell
curl.exe -s https://lms-ai-assistant.onrender.com/api/v1/health
```
Expected output:
```json
{
  "status": "healthy",
  "distributed_backend": "connected",
  "redis_active": true,
  "message_broker": {
    "rabbitmq_status": "configured",
    "provider": "CloudAMQP"
  }
}
```

### Q2: How do I re-publish the C# Web App after code changes?
Run the automated WebDeploy command from Visual Studio or PowerShell:
```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" "D:\avi\Project\MVC\LMS\LMS.csproj" /p:Configuration=Release /p:DeployOnBuild=true /p:PublishProfile="Properties\PublishProfiles\MonsterASP.pubxml" /p:Password="2Po_R!9q=cC6" /p:AllowUntrustedCertificate=true
```

### Q3: How do I update the Python AI Microservice?
Simply push your changes to GitHub:
```powershell
git add AIService/
git commit -m "feat: updated prompt template"
git push origin main
```
Render automatically detects the commit on branch `main` and redeploys the container within ~90 seconds.
