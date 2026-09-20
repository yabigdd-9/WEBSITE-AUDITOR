import os
from llama_cpp import Llama

# Configuration
MODEL_PATH = "llama-2-7b-chat.Q4_K_M.gguf"
MODEL_N_CTX = 2048  # Context window size
MODEL_N_GPU_LAYERS = -1  # -1 = use Metal GPU acceleration on Mac

# Global model cache (so we don't reload 4GB every time we call a function)
_llm_instance = None

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        print("🧠 Loading AI model into memory (this takes ~5 seconds)...")
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model not found! Please download {MODEL_PATH} first.")
        
        _llm_instance = Llama(
            model_path=MODEL_PATH,
            n_ctx=MODEL_N_CTX,
            n_gpu_layers=MODEL_N_GPU_LAYERS,  # Metal acceleration
            verbose=False  # Hide llama.cpp debug logs
        )
        print("✅ AI Model loaded and ready!")
    return _llm_instance

def generate_text(prompt, max_tokens=250, temperature=0.7, stop_sequences=None):
    """
    Core AI generation function.
    Returns the generated text string.
    """
    llm = get_llm()
    
    if stop_sequences is None:
        stop_sequences = ["</s>", "User:", "Human:", "System:"]
    
    try:
        response = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop_sequences,
            echo=False
        )
        return response['choices'][0]['text'].strip()
    except Exception as e:
        return f"[AI Error: {str(e)}]"

# Quick test function
if __name__ == "__main__":
    print("\n🧪 Testing AI Writer...")
    test_prompt = """You are an SEO expert. Write a 1-sentence meta description for a plumber in Auckland, New Zealand.
    
    Meta description:"""
    
    result = generate_text(test_prompt, max_tokens=100)
    print(f"\n✨ AI Output:\n{result}")
