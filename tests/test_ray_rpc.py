import ray
from ray import serve
import os
import asyncio
from PIL import Image
import sys

# Add src to path to allow importing ImageRAGMetadata if needed for type checking
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

async def test_rpc_call():
    print("Initializing Ray connection...")
    # Connect to the existing Ray cluster managed by the running service script
    # 'address="auto"' connects to the local ray cluster if it exists
    try:
        ray.init(address="auto", ignore_reinit_error=True)
    except Exception as e:
        print(f"Could not connect to existing Ray cluster: {e}")
        print("Starting a new local Ray instance (for standalone testing)...")
        ray.init(ignore_reinit_error=True)

    print("Getting Deployment Handle...")
    try:
        # NOTE: The app_name must match what was used in serve.run().
        # If run via `serve.run(image_rag)`, the default app name is "default".
        # If using `serve run ...`, it might be different.
        # We assume "default" here as per the `image_processing_ray.py` script.
        handle = serve.get_deployment_handle("ImageRAGDeployment", app_name="default")
    except Exception as e:
        print(f"Error getting handle: {e}")
        print("Make sure 'src/serve/image_processing_ray.py' is RUNNING in another terminal!")
        return

    # Find a test image
    resource_dir = os.path.join(os.path.dirname(__file__), "test_resource/")
    image_files = [f for f in os.listdir(resource_dir) if f.endswith(".jpg")]
    
    if not image_files:
        print("No test images found.")
        return

    test_image_path = os.path.join(resource_dir, image_files[0])
    print(f"Testing with image: {test_image_path}")

    # Test 1: Passing PIL Image Object (Zero-Copy efficiency)
    print("\n--- Test 1: Passing PIL Image Object (RPC) ---")
    try:
        img_obj = Image.open(test_image_path).convert("RGB")
        
        # Async RPC call
        print("Sending RPC request...")
        result_ref = await handle.process_image.remote(
            image=img_obj, 
            additional_prompt="<OD>"
        )
        
        print("RPC Result received!")
        print(f"Type: {type(result_ref)}")
        print(f"Caption: {result_ref.caption}")
        print(f"Tags: {result_ref.tags}")
        
    except Exception as e:
        print(f"RPC Call Failed: {e}")

    # Test 2: Passing Bytes (Simulating binary transfer)
    print("\n--- Test 2: Passing Bytes (RPC) ---")
    try:
        with open(test_image_path, "rb") as f:
            img_bytes = f.read()
            
        result_ref = await handle.process_image.remote(
            image=img_bytes,
            additional_prompt="<CAPTION>"
        )
        print(f"Caption from bytes: {result_ref.caption}")
        
    except Exception as e:
        print(f"RPC Call Failed: {e}")

if __name__ == "__main__":
    # Run the async test
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_rpc_call())