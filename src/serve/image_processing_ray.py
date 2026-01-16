import os
import io
from ray import serve
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Union
from PIL import Image

# Import from the processor module
# Assumes 'src' is in PYTHONPATH or we are running from project root with src as package
from processor.image_processing.image_rag import ImageRAGProcessor, Florence2Backend

# Define FastAPI app
image_rag_app = FastAPI()

# Get resource allocation from env
# florence is a super lightweight model, 0.15 is sufficient even for T4
image_gpu_per_instance = float(os.getenv("IMAGE_GPU_PER_INSTANCE", "0.15"))

@serve.deployment(
    ray_actor_options={"num_gpus": image_gpu_per_instance},
    autoscaling_config={"min_replicas": 1, "max_replicas": 4}
)
@serve.ingress(image_rag_app)
class ImageRAGDeployment:
    def __init__(self):
        # Initialize the processor with Florence-2 backend
        # This will load the model into GPU memory
        self.processor = ImageRAGProcessor(model_backend=Florence2Backend())

    def _read_image_from_bytes(self, image_bytes: bytes) -> Image.Image:
        """Helper to convert bytes to PIL Image."""
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")

    @image_rag_app.post("/process")
    async def process_api(
        self, 
        file: UploadFile = File(...), 
        additional_prompt: Optional[str] = Form(None)
    ):
        """
        API endpoint to process an uploaded image file and return RAG metadata.
        Uses multipart/form-data for file upload.
        """
        # Read file content as bytes
        image_bytes = await file.read()
        
        # Convert to PIL Image
        try:
            image_obj = self._read_image_from_bytes(image_bytes)
        except Exception as e:
            return {"error": f"Invalid image file: {str(e)}"}

        # Process using the PIL Image object
        metadata = self.processor.process_image(
            image=image_obj,
            additional_prompt=additional_prompt
        )
        return metadata.to_dict()

    def process_image(self, image: Union[str, Image.Image, bytes], additional_prompt: str = None):
        """
        Direct method call for Ray handles.
        Supports file path (str), PIL Image object, or raw bytes.
        """
        if isinstance(image, bytes):
            image = self._read_image_from_bytes(image)
            
        return self.processor.process_image(
            image=image,
            additional_prompt=additional_prompt
        )

# Define application entrypoint
image_rag = ImageRAGDeployment.bind()

if __name__ == "__main__":
    import ray
    
    # Initialize Ray and Serve
    # This allows running the script directly for testing: python src/serve/image_processing_ray.py
    ray.init(ignore_reinit_error=True)
    serve.start(http_options={"host": "0.0.0.0", "port": 8000})
    
    print("Starting Image RAG Service on port 8000...")
    serve.run(image_rag)
    
    print("Service deployed successfully.")
    print("Test with curl:")
    print('curl -X POST "http://localhost:8000/process" -F "file=@/path/to/image.jpg"')
    
    # Keep the script running
    try:
        import time
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nShutting down...")
        serve.shutdown()