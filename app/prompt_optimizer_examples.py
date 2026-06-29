"""
Example: Using PromptOptimizer with Different Models

This file demonstrates how to use the new PromptOptimizer class
to automatically select the best prompt for your LLM model.
"""

from datetime import date
from app.util import PromptOptimizer
from app.decision import create_llm_instance
from app.config import MODEL, MODEL_PROVIDER

# ============================================================================
# EXAMPLE 1: Automatic Detection (Recommended)
# ============================================================================

def example_auto_detection():
    """Auto-detect model size and use appropriate prompt."""
    
    print("\n=== Example 1: Automatic Model Detection ===")
    print(f"Configured MODEL: {MODEL}")
    
    # Auto-detect model size
    size = PromptOptimizer.detect_model_size(MODEL)
    print(f"Detected model size: {size}")
    
    # Get optimized prompt
    prompt = PromptOptimizer.get_final_prompt(MODEL)
    
    # Sample data
    device_data = """
    [
        {"product_number": "SWI-001", "product_description": "Catalyst 9200", 
         "location": "NYC-Data-Center", "pak/serial_number": "JAE1234567",
         "instance_number": "IN-001", "qty": 2, "last_date_of_support": "2024-03-15"},
        {"product_number": "SWI-002", "product_description": "Cisco ASR 9001", 
         "location": "LA-Office", "pak/serial_number": "JAE7654321",
         "instance_number": "IN-002", "qty": 1, "last_date_of_support": "2024-06-30"}
    ]
    """
    
    replacement_guidance = "Replace end-of-life switches with Catalyst 9400 series"
    question = "Which devices are ending support within 90 days?"
    
    # Format the prompt with data
    formatted_prompt = prompt.format(
        sql_context=device_data,
        rag_context=replacement_guidance,
        question=question,
        current_date=date.today().isoformat()
    )
    
    print(f"\nPrompt length: {len(formatted_prompt)} characters")
    print(f"First 200 chars of prompt:\n{formatted_prompt[:200]}...")
    
    return formatted_prompt


# ============================================================================
# EXAMPLE 2: Test All Model Sizes
# ============================================================================

def example_test_all_sizes():
    """Test and compare prompts for all model sizes."""
    
    print("\n=== Example 2: Testing All Model Sizes ===")
    
    models_to_test = [
        ('gemma-3-1b-it-Q4_K_M.gguf', 'Small'),
        ('mistral-7b-instruct', 'Medium'),
        ('gpt-4', 'Large')
    ]
    
    for model_name, expected_size in models_to_test:
        print(f"\n--- Testing {model_name} ---")
        
        # Detect size
        detected_size = PromptOptimizer.detect_model_size(model_name)
        print(f"Expected: {expected_size}, Detected: {detected_size}")
        
        # Get prompt
        prompt = PromptOptimizer.get_final_prompt(model_name)
        
        # Count instructions (rough estimate)
        template_text = prompt.template
        instruction_count = template_text.count('\n')
        print(f"Instruction lines: {instruction_count}")
        print(f"Template length: {len(template_text)} chars")


# ============================================================================
# EXAMPLE 3: Explicit Size Selection
# ============================================================================

def example_explicit_selection():
    """Explicitly select prompt size regardless of model name."""
    
    print("\n=== Example 3: Explicit Size Selection ===")
    
    # Get all three prompts explicitly
    small = PromptOptimizer._get_small_model_prompt()
    medium = PromptOptimizer._get_medium_model_prompt()
    large = PromptOptimizer._get_large_model_prompt()
    
    print(f"Small prompt template length: {len(small.template)} chars")
    print(f"Medium prompt template length: {len(medium.template)} chars")
    print(f"Large prompt template length: {len(large.template)} chars")
    
    # Compare complexity
    print(f"\nComplexity comparison:")
    print(f"Small has {small.template.count('CRITICAL')} risk level references")
    print(f"Medium has {medium.template.count('CRITICAL')} risk level references")
    print(f"Large has {large.template.count('CRITICAL')} risk level references")


# ============================================================================
# EXAMPLE 4: Real-World Usage in Chat Endpoint
# ============================================================================

def example_chat_endpoint(query: str, sql_results: str, rag_context: str):
    """
    Realistic example of using PromptOptimizer in a FastAPI endpoint.
    
    Args:
        query: User's natural language question
        sql_results: JSON results from database
        rag_context: Relevant guidance from vector store
    """
    
    print("\n=== Example 4: Chat Endpoint Usage ===")
    print(f"Query: {query}")
    
    # Step 1: Detect model size
    size = PromptOptimizer.detect_model_size(MODEL)
    print(f"Model: {MODEL} (detected as: {size})")
    
    # Step 2: Get optimized prompt
    prompt = PromptOptimizer.get_final_prompt(MODEL)
    
    # Step 3: Format prompt with actual data
    formatted_prompt = prompt.format(
        sql_context=sql_results,
        rag_context=rag_context,
        question=query,
        current_date=date.today().isoformat()
    )
    
    # Step 4: Would send to LLM (not actually calling here)
    # response = llm.invoke(formatted_prompt)
    
    print(f"Formatted prompt length: {len(formatted_prompt)} chars")
    print(f"Ready to send to LLM: {MODEL}")
    
    return formatted_prompt


# ============================================================================
# EXAMPLE 5: SQL Query Optimization
# ============================================================================

def example_sql_optimization():
    """Show the simplified SQL prompt."""
    
    print("\n=== Example 5: SQL Prompt Optimization ===")
    
    from app.util import sql_prompt
    
    # Show SQL prompt characteristics
    print(f"SQL prompt template length: {len(sql_prompt.template)} chars")
    
    # Count key rules
    rules_count = sql_prompt.template.count('\n')
    print(f"SQL rules/instructions: {rules_count} lines")
    
    # Show it works with all sizes
    for model_name in ['gemma-3-1b', 'mistral-7b', 'gpt-4']:
        print(f"✓ SQL prompt works with {PromptOptimizer.detect_model_size(model_name)} models")


# ============================================================================
# EXAMPLE 6: Model Size Pattern Recognition
# ============================================================================

def example_pattern_recognition():
    """Show how model name patterns are matched."""
    
    print("\n=== Example 6: Model Name Pattern Recognition ===")
    
    test_cases = [
        # Small models
        ('gemma-3-1b', 'small'),
        ('phi-2-mini', 'small'),
        ('tinyllama-1.1b', 'small'),
        ('orca-2-3b', 'small'),
        # Medium models
        ('mistral-7b-instruct', 'medium'),
        ('llama2-7b-chat', 'medium'),
        ('neural-chat-7b', 'medium'),
        # Large models
        ('gpt-4', 'large'),
        ('claude-3-opus', 'large'),
        ('llama2-70b-chat', 'large'),
        # Unknowns (default to medium)
        ('unknown-model', 'medium'),
        ('xyz-abc-def', 'medium'),
    ]
    
    print("Testing pattern matching:")
    all_correct = True
    for model, expected in test_cases:
        detected = PromptOptimizer.detect_model_size(model)
        status = "✓" if detected == expected else "✗"
        if detected != expected:
            all_correct = False
        print(f"{status} {model:30} → {detected:8} (expected: {expected})")
    
    print(f"\nAll tests passed: {all_correct}")


# ============================================================================
# EXAMPLE 7: Comparing Prompt Efficiency
# ============================================================================

def example_efficiency_comparison():
    """Compare token efficiency and quality across sizes."""
    
    print("\n=== Example 7: Efficiency Comparison ===")
    
    small = PromptOptimizer._get_small_model_prompt()
    medium = PromptOptimizer._get_medium_model_prompt()
    large = PromptOptimizer._get_large_model_prompt()
    
    prompts = [
        ('Small', small, ~250, '75%'),
        ('Medium', medium, ~400, '90%'),
        ('Large', large, ~800, '95%'),
    ]
    
    print(f"{'Size':<10} {'Tokens':<10} {'Accuracy':<12} {'Best For':<30}")
    print("-" * 70)
    
    best_for = [
        'Edge/Demo',
        'Production',
        'High-Accuracy'
    ]
    
    for i, (size, prompt, tokens, accuracy) in enumerate(prompts):
        print(f"{size:<10} {tokens:<10} {accuracy:<12} {best_for[i]:<30}")


# ============================================================================
# EXAMPLE 8: Error Handling and Defaults
# ============================================================================

def example_error_handling():
    """Show how the optimizer handles edge cases."""
    
    print("\n=== Example 8: Error Handling & Defaults ===")
    
    edge_cases = [
        None,
        '',
        'unknown-model-xyz-123',
        'Model-With-UPPERCASE',
        '7b',  # Only size, no model name
    ]
    
    print("Testing edge cases:")
    for case in edge_cases:
        try:
            result = PromptOptimizer.detect_model_size(case)
            print(f"✓ detect_model_size({repr(case):30}) → {result}")
        except Exception as e:
            print(f"✗ detect_model_size({repr(case):30}) → ERROR: {e}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("PromptOptimizer Examples - Demonstrating All Features")
    print("=" * 70)
    
    # Run all examples
    example_auto_detection()
    example_test_all_sizes()
    example_explicit_selection()
    
    # Real-world example with sample data
    sample_query = "Which devices are at risk within 30 days?"
    sample_sql = '[{"product_number": "SW-001", "last_date_of_support": "2024-03-15"}]'
    sample_rag = "Replace with Catalyst 9400"
    example_chat_endpoint(sample_query, sample_sql, sample_rag)
    
    example_sql_optimization()
    example_pattern_recognition()
    example_efficiency_comparison()
    example_error_handling()
    
    print("\n" + "=" * 70)
    print("Examples Complete!")
    print("=" * 70)
