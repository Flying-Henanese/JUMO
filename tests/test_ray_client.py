import requests
import os
import glob
import json

def test_image_rag_service():
    # Service endpoint
    url = "http://localhost:8000/process"
    
    # Test resource directory
    # Using the path provided by the user, correcting backslashes to forward slashes for Linux
    resource_dir = "/home/mineru_dev/mineru_universal/mineru-service/tests/test_resource"
    
    if not os.path.exists(resource_dir):
        print(f"Error: Directory not found: {resource_dir}")
        # Fallback to relative path if absolute path fails
        resource_dir = os.path.join(os.path.dirname(__file__), "test_resource")
        print(f"Trying relative path: {resource_dir}")
        if not os.path.exists(resource_dir):
            print("Error: Test resource directory not found.")
            return

    # Find all JPG images
    image_files = glob.glob(os.path.join(resource_dir, "*.jpg"))
    
    if not image_files:
        print(f"No .jpg files found in {resource_dir}")
        return
    
    print(f"Found {len(image_files)} images to process.")
    
    for image_path in image_files:
        print(f"\nProcessing: {os.path.basename(image_path)}")
        
        try:
            with open(image_path, "rb") as f:
                files = {"file": f}
                response = requests.post(url, files=files, data={"additional_prompt": "<CAPTION>"})
            
            if response.status_code == 200:
                print("Success!")
                result = response.json()
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"Failed with status code: {response.status_code}")
                print(response.text)
                
        except requests.exceptions.ConnectionError:
            print("Error: Could not connect to server. Is the Ray Serve service running?")
            print("Run: python src/serve/image_processing_ray.py")
            break
        except Exception as e:
            print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    test_image_rag_service()