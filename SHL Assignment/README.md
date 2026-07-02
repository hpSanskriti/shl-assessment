# SHL Assessment Recommender

A conversational AI agent that recommends SHL Individual Test Solutions based on hiring needs.

## Architecture

- **FastAPI** backend with two endpoints: `GET /health` and `POST /chat`
- **Groq** (Llama 3.3 70B) for conversational AI
- **Sentence-Transformers** (all-MiniLM-L6-v2) for semantic search over the assessment catalog
- **NumPy** for cosine similarity computation
- **380 assessments** scraped from the SHL Product Catalog

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Create a `.env` file:
```
GROQ_API_KEY=your_groq_api_key_here
```
Get a free API key at https://console.groq.com/keys

### 3. Run the server
```bash
python run.py
```
Or directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The first request will download the embedding model (~90MB) and build the catalog embeddings. Subsequent starts will load the cached embeddings from `data/catalog_embeddings.npy`.

## API Endpoints

### GET /health
Returns `{"status": "ok"}` when the service is running.

### POST /chat
Accepts a JSON body with the conversation history and returns recommendations.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "I need assessments for a Java developer position"}
  ]
}
```

**Response:**
```json
{
  "reply": "For a Java developer position, I recommend...",
  "recommendations": [
    {
      "name": "Java 8 (New)",
      "url": "https://www.shl.com/solutions/products/product-catalog/view/java-8-new/",
      "test_type": "K"
    }
  ],
  "end_of_conversation": false
}
```

## Agent Behavior

1. **Clarifies** vague requests before recommending
2. **Recommends** 1-10 assessments from the SHL catalog when enough context is available
3. **Refines** recommendations when the user adjusts constraints
4. **Compares** assessments when asked
5. **Refuses** off-topic queries politely

## Test Type Codes

| Code | Meaning |
|------|---------|
| K | Knowledge/Technical |
| A | Ability/Cognitive |
| P | Personality |
| B | Behavioral/SJT |
| C | Competency |
| E | Exercise/Simulation |
| S | Skills |

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI endpoints
│   ├── agent.py         # Core agent logic (retrieval + LLM orchestration)
│   ├── models.py        # Pydantic request/response schemas
│   ├── prompts.py       # System prompts and message construction
│   └── retrieval.py     # Semantic search over catalog
├── data/
│   └── catalog.json     # 380 SHL assessments (scraped)
├── scraper/
│   ├── scrape_fast.py   # Catalog scraper (Wayback Machine CDX API)
│   └── fix_types.py     # Post-processor for test type classification
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py               # Entry point
└── README.md
```

## Design Decisions

- **Stateless API**: Full conversation history is passed with each request (no server-side session state)
- **Semantic retrieval**: Embeddings are pre-built from assessment name + description + metadata, enabling fast cosine similarity search
- **Validation layer**: All recommendations are verified against the catalog before returning (prevents hallucinated assessments)
- **Type filtering**: User intent analysis extracts assessment type preferences to boost relevant results
- **Guardrails**: Off-topic and prompt injection attempts are detected and refused
