"""Core agent logic: orchestrates retrieval, LLM calls, and response validation."""
import json
import os
import re
from dotenv import load_dotenv
from groq import Groq

from app.models import Message, ChatResponse, Recommendation
from app.retrieval import search_catalog, get_catalog
from app.prompts import build_catalog_context, build_messages_for_llm

load_dotenv()

# Initialize Groq client
_groq_client = None


def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def extract_search_query(messages: list[Message]) -> str:
    """Extract a search query from the conversation history."""
    # Combine all user messages to form the search context
    user_messages = [m.content for m in messages if m.role == "user"]
    # Weight recent messages more heavily
    if len(user_messages) > 2:
        query = " ".join(user_messages[-3:])
    else:
        query = " ".join(user_messages)
    return query


def detect_intent(messages: list[Message]) -> str:
    """Detect the user's intent from conversation history.
    
    Returns one of: 'clarify', 'recommend', 'refine', 'compare', 'refuse'
    """
    if not messages:
        return "clarify"

    last_user_msg = ""
    for m in reversed(messages):
        if m.role == "user":
            last_user_msg = m.content.lower()
            break

    # Check for off-topic / prompt injection
    off_topic_patterns = [
        r"ignore.*instructions",
        r"forget.*previous",
        r"you are now",
        r"pretend to be",
        r"what is your (system|prompt)",
        r"(salary|compensation|pay|legal|lawsuit|sue)",
        r"(recipe|weather|news|sports|movie)",
    ]
    for pattern in off_topic_patterns:
        if re.search(pattern, last_user_msg):
            return "refuse"

    # Check for comparison request
    compare_patterns = [
        r"(compare|difference|versus|vs\.?|between.*and)",
        r"(which.*better|how.*differ|pros.*cons)",
    ]
    for pattern in compare_patterns:
        if re.search(pattern, last_user_msg):
            return "compare"

    # Check for refinement (user already got recommendations and is adjusting)
    has_prior_recommendations = False
    for m in messages:
        if m.role == "assistant" and "recommendations" in m.content.lower():
            has_prior_recommendations = True

    refine_patterns = [
        r"(also add|include|remove|drop|replace|instead|actually|change|update|modify)",
        r"(more|fewer|shorter|longer|different|another)",
        r"(what about|can you also|and personality|and cognitive)",
    ]
    if has_prior_recommendations:
        for pattern in refine_patterns:
            if re.search(pattern, last_user_msg):
                return "refine"

    # Check if query is too vague to recommend
    vague_patterns = [
        r"^(hi|hello|hey|help)\.?$",
        r"^i need (an|some) assessment",
        r"^(assessment|test|recommend)",
        r"^(help me|can you help)",
    ]
    
    # If it's the first user message and it's vague, clarify
    user_msg_count = sum(1 for m in messages if m.role == "user")
    if user_msg_count == 1:
        for pattern in vague_patterns:
            if re.search(pattern, last_user_msg.strip()):
                return "clarify"
        # Even with some detail, if no specific role or skill mentioned, clarify
        has_specifics = bool(re.search(
            r"(developer|engineer|manager|analyst|designer|sales|support|admin|nurse|teacher|accountant|"
            r"java|python|sql|excel|leadership|cognitive|personality|verbal|numerical|"
            r"junior|senior|mid|entry|executive|graduate|intern)",
            last_user_msg
        ))
        if not has_specifics:
            return "clarify"

    return "recommend"


def extract_type_filters(messages: list[Message]) -> list[str] | None:
    """Extract test type preferences from conversation."""
    full_text = " ".join(m.content.lower() for m in messages if m.role == "user")
    
    types = set()
    if any(kw in full_text for kw in ["personality", "behavioral style", "opq", "motivation"]):
        types.add("P")
    if any(kw in full_text for kw in ["cognitive", "reasoning", "numerical", "verbal", "inductive", "ability", "aptitude"]):
        types.add("A")
    if any(kw in full_text for kw in ["knowledge", "technical test", "coding test"]):
        types.add("K")
    if any(kw in full_text for kw in ["situational", "judgment", "sjt", "behavioral assessment"]):
        types.add("B")
    if any(kw in full_text for kw in ["simulation", "coding simulation", "hands-on"]):
        types.add("E")
    if any(kw in full_text for kw in ["competency", "360", "leadership assessment"]):
        types.add("C")
    
    return list(types) if types else None


def validate_recommendations(recs: list[dict]) -> list[Recommendation]:
    """Validate and filter recommendations to ensure they're from the catalog."""
    catalog = get_catalog()
    catalog_urls = {item["url"] for item in catalog}
    catalog_names = {item["name"].lower(): item for item in catalog}
    
    valid = []
    for rec in recs[:10]:  # Max 10
        name = rec.get("name", "")
        url = rec.get("url", "")
        test_type = rec.get("test_type", "")
        
        # Validate URL is from catalog
        if url in catalog_urls:
            valid.append(Recommendation(name=name, url=url, test_type=test_type))
        elif name.lower() in catalog_names:
            # Fix URL from catalog
            item = catalog_names[name.lower()]
            valid.append(Recommendation(
                name=item["name"],
                url=item["url"],
                test_type=item.get("test_type", test_type)
            ))
        else:
            # Try fuzzy name match
            for cat_name, item in catalog_names.items():
                if name.lower() in cat_name or cat_name in name.lower():
                    valid.append(Recommendation(
                        name=item["name"],
                        url=item["url"],
                        test_type=item.get("test_type", "")
                    ))
                    break
    
    return valid


def parse_llm_response(text: str) -> dict:
    """Parse the LLM response JSON, handling common formatting issues."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    
    # Try parsing as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try extracting JSON from the text
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # Fallback: return a safe default
    return {
        "reply": text[:500] if text else "I apologize, I encountered an issue. Could you rephrase your question?",
        "recommendations": [],
        "end_of_conversation": False,
    }


async def handle_chat(messages: list[Message]) -> ChatResponse:
    """Main chat handler: orchestrates retrieval, LLM call, and response."""
    
    # Detect intent
    intent = detect_intent(messages)
    
    # Handle refusal immediately (no LLM call needed for obvious cases)
    if intent == "refuse":
        return ChatResponse(
            reply="I'm specifically designed to help with SHL assessment recommendations. I can't help with that topic. Is there anything about SHL assessments I can assist you with?",
            recommendations=[],
            end_of_conversation=False,
        )
    
    # Build search query from conversation
    search_query = extract_search_query(messages)
    
    # Get type filters if user expressed preferences
    type_filters = extract_type_filters(messages)
    
    # Retrieve relevant assessments from catalog
    retrieved = search_catalog(search_query, top_k=20, type_filter=type_filters)
    
    # Build catalog context for LLM
    catalog_context = build_catalog_context(retrieved)
    
    # Build LLM messages
    conversation_dicts = [{"role": m.role, "content": m.content} for m in messages]
    llm_messages = build_messages_for_llm(conversation_dicts, catalog_context)
    
    # Call Groq LLM
    try:
        client = get_groq_client()
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=llm_messages,
            temperature=0.3,
            max_tokens=1500,
            top_p=0.9,
        )
        response_text = completion.choices[0].message.content
    except Exception as e:
        # Fallback response on LLM error
        return ChatResponse(
            reply=f"I'm having trouble processing your request. Could you try rephrasing? (Error: service temporarily unavailable)",
            recommendations=[],
            end_of_conversation=False,
        )
    
    # Parse LLM response
    parsed = parse_llm_response(response_text)
    
    # Validate recommendations
    raw_recs = parsed.get("recommendations", [])
    valid_recs = validate_recommendations(raw_recs) if raw_recs else []
    
    # Build response
    return ChatResponse(
        reply=parsed.get("reply", ""),
        recommendations=valid_recs,
        end_of_conversation=parsed.get("end_of_conversation", False),
    )
