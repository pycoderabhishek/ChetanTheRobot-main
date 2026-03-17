import json
import os
import difflib
import re
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple

# Path to the Q&A database file
# From app/audio/ → ../../dataset/ (go up 2 levels to amhrpd-backend/)
QA_DATABASE_FILE = "../../dataset/query.json"

# In-memory cache of the Q&A data
_qa_database = None
_qa_index = None  # Quick lookup index

class QAMatch:
    """Data class for Q&A match results"""
    def __init__(self, question: str, answer: str, category: str, confidence: float):
        self.question = question
        self.answer = answer
        self.category = category
        self.confidence = confidence  # 0.0 to 1.0
    
    def __repr__(self):
        return f"QAMatch(q='{self.question[:30]}...', confidence={self.confidence:.2f})"

def load_qa_database() -> Optional[List[Dict]]:
    """Load Q&A database from query.json with caching"""
    global _qa_database
    
    if _qa_database is not None:
        return _qa_database
    
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Navigate to dataset folder (../../dataset/)
        data_path = os.path.join(current_dir, QA_DATABASE_FILE)
        data_path = os.path.abspath(data_path)  # Resolve to absolute path
        
        if not os.path.exists(data_path):
            print(f"Q&A database not found at: {data_path}")
            return None
        
        with open(data_path, "r", encoding="utf-8") as f:
            _qa_database = json.load(f)
            print(f"✓ Loaded {len(_qa_database)} Q&A pairs from query.json")
            return _qa_database
            
    except json.JSONDecodeError as e:
        print(f"Error parsing Q&A database JSON: {e}")
        return None
    except Exception as e:
        print(f"Error loading Q&A database: {e}")
        return None

def _normalize_text(text: str) -> str:
    """Normalize text for comparison"""
    text = text.lower().strip()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text

def _calculate_similarity(query: str, target: str) -> float:
    """
    Calculate similarity score between query and target text (0.0 to 1.0)
    Uses SequenceMatcher for fuzzy matching
    """
    query = _normalize_text(query)
    target = _normalize_text(target)
    
    # Direct match gets highest score
    if query in target or target in query:
        return 1.0
    
    # Fuzzy matching
    return SequenceMatcher(None, query, target).ratio()

def _tokenize_query(query: str) -> List[str]:
    """Extract keywords from query"""
    query = _normalize_text(query)
    # Remove common stop words
    stop_words = {'is', 'the', 'a', 'an', 'what', 'how', 'where', 'when', 'who', 'why', 'does', 'do', 'at', 'in', 'of'}
    tokens = [w for w in query.split() if w not in stop_words]
    return tokens

def search_qa_database(query: str, top_k: int = 3, min_confidence: float = 0.5) -> List[QAMatch]:
    """
    Advanced Q&A search with fuzzy matching and multiple scoring strategies
    
    Args:
        query: User's question
        top_k: Return top K matches
        min_confidence: Minimum confidence threshold (0.0 to 1.0)
    
    Returns:
        List of QAMatch objects sorted by confidence (highest first)
    """
    qa_data = load_qa_database()
    if not qa_data:
        return []
    
    query_normalized = _normalize_text(query)
    query_tokens = _tokenize_query(query)
    
    matches = []
    
    for item in qa_data:
        question = item.get("query", "")
        answer = item.get("answer", "")
        category = item.get("category", "Unknown")
        
        # Strategy 1: Direct question similarity
        question_similarity = _calculate_similarity(query_normalized, _normalize_text(question))
        
        # Strategy 2: Token-based matching (how many keywords match)
        question_tokens = _tokenize_query(question)
        token_matches = len(set(query_tokens) & set(question_tokens))
        token_score = token_matches / max(len(query_tokens), 1) if query_tokens else 0
        
        # Strategy 3: Category-based boost
        category_tokens = _tokenize_query(category)
        category_match = len(set(query_tokens) & set(category_tokens)) > 0
        
        # Combined confidence score (weighted average)
        confidence = (question_similarity * 0.6 + token_score * 0.3 + 
                     (0.1 if category_match else 0.0))
        
        if confidence >= min_confidence:
            matches.append(QAMatch(
                question=question,
                answer=answer,
                category=category,
                confidence=confidence
            ))
    
    # Sort by confidence (highest first)
    matches.sort(key=lambda x: x.confidence, reverse=True)
    
    return matches[:top_k]

def get_answer(query: str) -> Optional[str]:
    """
    Main entry point: Get answer for a user query
    
    Returns:
        Answer string if found, None otherwise
    """
    if not query or not query.strip():
        return None
    
    # Search Q&A database
    matches = search_qa_database(query, top_k=1, min_confidence=0.45)
    
    if matches:
        best_match = matches[0]
        # Return answer if confidence is reasonable
        if best_match.confidence >= 0.45:
            return best_match.answer
    
    return None

def search_qa(query: str, top_k: int = 3) -> List[Dict]:
    """
    Public API for Q&A search (returns full match details)
    Useful for debugging or showing multiple options
    
    Returns:
        List of dictionaries with question, answer, category, confidence
    """
    matches = search_qa_database(query, top_k=top_k, min_confidence=0.40)
    
    return [
        {
            "question": m.question,
            "answer": m.answer,
            "category": m.category,
            "confidence": round(m.confidence, 3)
        }
        for m in matches
    ]

def get_qa_stats() -> Dict:
    """Get statistics about the Q&A database"""
    qa_data = load_qa_database()
    if not qa_data:
        return {"status": "Database not loaded"}
    
    categories = {}
    for item in qa_data:
        cat = item.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1
    
    return {
        "total_qa_pairs": len(qa_data),
        "categories": categories,
        "status": "✓ Ready"
    }
