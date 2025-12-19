import os
import sys
import argparse
from PIL import Image
from mineru_vl_utils import MinerUClient
from mineru_vl_utils.structs import ContentBlock 

def test_layout_detection(server_url, model_name, image_path):
    # 2. 初始化客户端
    print(f"Connecting to VLLM server at {server_url} with model {model_name}...")
    try:
        client = MinerUClient(
            backend="http-client",
            server_url=server_url,
            model_name=model_name,
            abandon_paratext=True,  # 开启忽略页眉页脚
            http_timeout=120 # 增加超时时间防止网络波动
        )
    except Exception as e:
        print(f"Failed to initialize MinerUClient: {e}")
        return

    # 3. 加载测试图片
    if not os.path.exists(image_path):
        print(f"未找到测试图片 {image_path}，生成空白图片用于演示...")
        image = Image.new('RGB', (1000, 1000), color = 'white')
    else:
        print(f"Loading image from {image_path}...")
        image = Image.open(image_path)

    # 4. 执行布局检测和内容提取
    print("开始布局检测和内容提取...")
    try:
        # 使用 two_step_extract 替代 layout_detect
        blocks: list[ContentBlock] = client.two_step_extract(image)
        
        # 5. 输出结果
        print(f"检测到 {len(blocks)} 个区块:")
        for block in blocks:
            print(f"Type: {block.type}, Content: {block.content}")
            
    except Exception as e:
        print(f"Layout detection failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test layout detection with MinerUClient")
    parser.add_argument("--server_url", type=str, default="http://localhost:8000/v1", help="VLLM server URL")
    parser.add_argument("--model_name", type=str, default="opendatalab/MinerU2.5-2509-1.2B", help="Model name served by VLLM")
    parser.add_argument("--image_path", type=str, default="test1.png", help="Path to the image file")
    
    args = parser.parse_args()
    
    test_layout_detection(args.server_url, args.model_name, args.image_path)