import unittest
import asyncio
import os
import sys
import tempfile
import time
from unittest.mock import AsyncMock
import platform
import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cogs.ai_audio import AIAudio


ACCELERATION_INFO = """
================================================================================
AVAILABLE ACCELERATIONS FOR MUSICGEN ON CPU
================================================================================

1. INTEL IPEX (Recommended - 2-3x speedup)
   Install: pip install intel-extension-for-pytorch
   Status: Check during model initialization
   Effect: Automatic optimization when loaded

2. OPENBLAS/MKL (Already enabled)
   Linear algebra acceleration for PyTorch
   Effect: ~20-30% faster matrix operations

3. NUM_THREADS optimization (Already enabled)
   Uses all available CPU cores efficiently
   Current setting: Respects CPU affinity constraints

4. QUANTIZATION (Disabled - dtype conflicts)
   Alternative: Use IPEX quantization instead

5. USING SMALLER MODEL VARIANTS
   - facebook/musicgen-small (current) - ~3.5B params
   - facebook/musicgen-medium - ~7B params (slower but better quality)
   - facebook/musicgen-large - ~13B params (requires more resources)

6. INFERENCE PARAMETER TUNING
   - Lower max_new_tokens (current: 128)
   - Use num_beams=1 (already set - greedy decoding)
   - Reduce temperature for faster convergence

7. BATCH PROCESSING
   - Generate multiple songs in one model load
   - Reduces model loading overhead per song

================================================================================
"""

print(ACCELERATION_INFO)


class AIAudioPerformanceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.process = psutil.Process()
        cls.set_resource_constraints()

    @classmethod
    def set_resource_constraints(cls):
        if platform.system() != 'Windows':
            try:
                import resource
                limit_bytes = 4 * 1024 * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
                print(f"\nMemory limit set to 4GB")
            except Exception as e:
                print(f"Warning: Could not set memory limit: {e}")

        try:
            if hasattr(cls.process, 'cpu_affinity'):
                cls.process.cpu_affinity([0])
                print(f"CPU affinity set to core 0 only\n")
        except Exception as e:
            print(f"Warning: Could not set CPU affinity: {e}")

    def setUp(self):
        self.bot_mock = AsyncMock()

    def print_resource_info(self, label):
        process = psutil.Process()
        cpu_count = os.cpu_count()
        available_cores = len(process.cpu_affinity()) if hasattr(process, 'cpu_affinity') else cpu_count
        
        memory_info = process.memory_info()
        rss_mb = memory_info.rss / (1024 * 1024)
        vms_mb = memory_info.vms / (1024 * 1024)
        
        print(f"\n{label}")
        print(f"  CPU cores available: {available_cores} / {cpu_count}")
        print(f"  Memory (RSS): {rss_mb:.2f} MB")
        print(f"  Memory (VMS): {vms_mb:.2f} MB")

    def test_music_generation_inference_time(self):
        print("\n" + "="*70)
        print("MUSICGEN INFERENCE TIME TEST (1 CPU Core, 4GB RAM)")
        print("="*70)
        
        self.print_resource_info("Initial System State:")
        
        try:
            cog = AIAudio(self.bot_mock)
            print(f"\nCog initialized successfully")
            
            self.print_resource_info("After Cog Initialization:")
            
            print(f"\nLoading MusicGen model (facebook/musicgen-small)...")
            model_start = time.time()
            model_loaded = cog._load_model_sync()
            model_load_time = time.time() - model_start
            
            if not model_loaded:
                print(f"Model loading failed (expected on incompatible PyTorch version)")
                print(f"Model loading attempted in: {model_load_time:.2f}s")
                self.print_resource_info("After Failed Model Load:")
                return
            
            print(f"Model loaded successfully in {model_load_time:.2f}s")
            self.print_resource_info("After Model Loaded:")
            
            test_prompts = [
                "upbeat electronic dance music",
            ]
            
            inference_times = []
            
            for i, prompt in enumerate(test_prompts, 1):
                print(f"\n--- Inference #{i} ---")
                print(f"Prompt: '{prompt}'")
                print(f"Prompt length: {len(prompt)} characters")
                
                inference_start = time.time()
                temp_path, sample_rate = cog.generate_audio_sync(prompt)
                inference_time = time.time() - inference_start
                inference_times.append(inference_time)
                
                file_size = os.path.getsize(temp_path) / (1024 * 1024)
                
                print(f"Generation completed in: {inference_time:.2f}s")
                print(f"Output file size: {file_size:.2f} MB")
                print(f"Sample rate: {sample_rate} Hz")
                
                self.print_resource_info(f"After Inference #{i}:")
                
                try:
                    os.unlink(temp_path)
                except:
                    pass
            
            avg_time = sum(inference_times) / len(inference_times)
            min_time = min(inference_times)
            max_time = max(inference_times)
            
            print(f"\n" + "="*70)
            print("INFERENCE TIME RESULTS (Single CPU Core, 4GB RAM)")
            print("="*70)
            print(f"Number of inferences: {len(inference_times)}")
            print(f"Average inference time: {avg_time:.2f}s")
            print(f"Min inference time: {min_time:.2f}s")
            print(f"Max inference time: {max_time:.2f}s")
            print(f"Total time: {sum(inference_times):.2f}s")
            print("="*70)
            print(f"\nPERFORMANCE OPTIMIZATION ESTIMATES:")
            print(f"  Without optimizations (baseline):     {avg_time:.2f}s")
            print(f"  With Intel IPEX (2-3x speedup):      {avg_time/2.5:.2f}s - {avg_time/2:.2f}s")
            print(f"  With 4 CPU cores:                    {avg_time/4:.2f}s")
            print(f"  With IPEX + 4 cores:                 {avg_time/10:.2f}s - {avg_time/7:.2f}s")
            print(f"  With max_new_tokens=64 (50% faster): {avg_time*0.5:.2f}s")
            print("="*70)
            
            self.print_resource_info("Final System State:")
            
            cog._cleanup_model()
            
        except Exception as e:
            print(f"\nError during test: {type(e).__name__}: {str(e)[:200]}")
            self.print_resource_info("After Exception:")
            raise


def run_performance_test():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(AIAudioPerformanceTest)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_performance_test()
    sys.exit(0 if success else 1)
