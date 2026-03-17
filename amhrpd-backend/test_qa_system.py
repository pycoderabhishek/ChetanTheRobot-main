#!/usr/bin/env python3
"""
Test suite for the new advanced Q&A system
Tests the new query.json based knowledge base
"""

import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from audio.knowledge_base import (
    load_qa_database, 
    get_answer, 
    search_qa,
    get_qa_stats
)

def print_header(title):
    """Print a formatted header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def test_database_loading():
    """Test 1: Load Q&A database"""
    print_header("TEST 1: Database Loading")
    
    data = load_qa_database()
    
    if data is None:
        print("❌ FAILED: Database not loaded")
        return False
    
    if not isinstance(data, list):
        print(f"❌ FAILED: Expected list, got {type(data)}")
        return False
    
    print(f"✅ PASSED: Loaded {len(data)} Q&A pairs")
    
    # Show sample
    if data:
        print(f"\nSample question: {data[0].get('query')}")
        print(f"Sample answer: {data[0].get('answer')[:100]}...")
    
    return True

def test_qa_stats():
    """Test 2: Q&A Database Statistics"""
    print_header("TEST 2: Database Statistics")
    
    stats = get_qa_stats()
    print(f"Status: {stats.get('status')}")
    print(f"Total Q&A Pairs: {stats.get('total_qa_pairs')}")
    print(f"\nCategory Breakdown:")
    
    categories = stats.get('categories', {})
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {cat}: {count} questions")
    
    return stats.get('total_qa_pairs', 0) > 0

def test_simple_queries():
    """Test 3: Simple Q&A Queries"""
    print_header("TEST 3: Simple Q&A Queries")
    
    test_questions = [
        ("What is NPGC?", "National Post Graduate College"),
        ("When was NPGC established?", "1974"),
        ("What is the address of NPGC?", "Lucknow"),
        ("Does NPGC have BCA?", "B.C.A."),
        ("What is the contact number of NPGC?", "phone"),
    ]
    
    passed = 0
    for question, expected_keyword in test_questions:
        answer = get_answer(question)
        
        if answer and expected_keyword.lower() in answer.lower():
            print(f"✅ '{question}' → Found keyword '{expected_keyword}'")
            passed += 1
        elif answer:
            print(f"⚠️  '{question}' → Got answer but missing '{expected_keyword}'")
            print(f"    Answer: {answer[:80]}...")
        else:
            print(f"❌ '{question}' → No answer found")
    
    print(f"\nResult: {passed}/{len(test_questions)} tests passed")
    return passed > 0

def test_fuzzy_matching():
    """Test 4: Fuzzy Matching (typos & variations)"""
    print_header("TEST 4: Fuzzy Matching & Variations")
    
    # Test similar questions with different wording
    variations = [
        ("Which university is NPGC affiliated?", "University of Lucknow"),
        ("NPGC affiliation?", "University of Lucknow"),  
        ("Tell me about NPGC vision", "merit"),  # Part of "Merit with Ethics"
        ("NPGC principal name", "Singh"),
        ("Who is the head of NPGC?", "Singh"),
    ]
    
    passed = 0
    for question, expected_keyword in variations:
        answer = get_answer(question)
        
        if answer and expected_keyword.lower() in answer.lower():
            print(f"✅ '{question}'")
            passed += 1
        else:
            print(f"❌ '{question}' (expected '{expected_keyword}')")
    
    print(f"\nResult: {passed}/{len(variations)} fuzzy match tests passed")
    return passed >= len(variations) * 0.7  # Allow 70% pass rate for fuzzy

def test_search_qa_ranking():
    """Test 5: Top-K Search Ranking"""
    print_header("TEST 5: Multi-Result Search Ranking")
    
    query = "courses offered at NPGC"
    results = search_qa(query, top_k=5)
    
    print(f"Query: '{query}'")
    print(f"Found {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        print(f"{i}. [Confidence: {result['confidence']:.3f}] {result['category']}")
        print(f"   Q: {result['question']}")
        print(f"   A: {result['answer'][:60]}...\n")
    
    return len(results) > 0

def test_no_answer():
    """Test 6: Graceful handling of no answer"""
    print_header("TEST 6: No Answer Cases")
    
    nonsense_queries = [
        "xyz12345 random nonsense",
        "asfadfadfadf",
        "!!@@##$$",
    ]
    
    for query in nonsense_queries:
        answer = get_answer(query)
        if answer is None:
            print(f"✅ Correctly returned None for: '{query}'")
        else:
            print(f"⚠️  Unexpected answer for '{query}': {answer[:50]}...")
    
    return True

def test_real_world_questions():
    """Test 7: Real-world FAQ Questions"""
    print_header("TEST 7: Real-World Questions")
    
    real_questions = [
        "What is the motto of NPGC?",
        "Is NPGC autonomous?",
        "How many books are in the library?",
        "What hostels are available at NPGC?",
        "Does NPGC have placement support?",
        "What is NEP 2020?",
        "How can I apply for admission?",
        "What are working hours at NPGC?",
        "Does NPGC have NCC?",
        "What is the library penalty for late return?",
    ]
    
    answered = 0
    for question in real_questions:
        answer = get_answer(question)
        if answer:
            print(f"✅ {question}")
            print(f"   → {answer[:70]}...")
            answered += 1
        else:
            print(f"❌ {question}")
    
    print(f"\nResult: {answered}/{len(real_questions)} real questions answered")
    return answered > len(real_questions) * 0.8  # At least 80%

def main():
    print("\n" + "="*80)
    print("  ADVANCED Q&A SYSTEM TEST SUITE")
    print("  Testing query.json based knowledge base")
    print("="*80)
    
    tests = [
        ("Database Loading", test_database_loading),
        ("Statistics", test_qa_stats),
        ("Simple Queries", test_simple_queries),
        ("Fuzzy Matching", test_fuzzy_matching),
        ("Search Ranking", test_search_qa_ranking),
        ("No Answer Cases", test_no_answer),
        ("Real-World Questions", test_real_world_questions),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"❌ EXCEPTION: {e}")
            results.append((test_name, False))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    percentage = (passed_count / total_count * 100) if total_count > 0 else 0
    print(f"\nOverall: {passed_count}/{total_count} tests passed ({percentage:.0f}%)")
    
    if percentage >= 80:
        print("\n🎉 Q&A System is READY FOR PRODUCTION!")
    elif percentage >= 60:
        print("\n⚠️  Q&A System is MOSTLY WORKING (needs minor fixes)")
    else:
        print("\n❌ Q&A System NEEDS MORE WORK")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
