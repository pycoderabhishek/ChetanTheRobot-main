from app.audio.knowledge_base import get_answer

def test_queries():
    queries = [
        "who is Dr. Preeti Singh?",
        "tell me about BCA course",
        "what is the address of the college?",
        "admission dates",
        "eligibility for B.Com.",
        "who teaches Computer Science?",
        "vision of the college"
    ]

    print("--- Testing Knowledge Base ---")
    for q in queries:
        print(f"Query: {q}")
        ans = get_answer(q)
        print(f"Answer: {ans}")
        print("-" * 20)

if __name__ == "__main__":
    test_queries()
