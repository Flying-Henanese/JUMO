import argparse
import asyncio
import os
import sys
from pathlib import Path

# 确保可以导入 src 下模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processor.enhancer.image_caption_generator import generate_enhanced_caption_from_bytes
from wrapper.mineru_image_writer_wrapper import MyImageInterceptor, default_vlm_model_func


def parse_args():
    parser = argparse.ArgumentParser(description="测试图片描述完整流程（generator + interceptor）")
    parser.add_argument("--image", required=True, help="待测试图片路径")
    parser.add_argument("--output-dir", default="./tmp_test_output", help="拦截器写出目录")
    parser.add_argument("--save-name", default="test_image.png", help="写出的文件名")
    parser.add_argument("--enable-caption", action="store_true", help="是否启用拦截器描述生成")
    return parser.parse_args()


async def test_generator(image_bytes: bytes, image_name: str):
    print("\n[1/2] 测试 generate_enhanced_caption_from_bytes ...")
    result = await generate_enhanced_caption_from_bytes(
        image_bytes=image_bytes,
        vlm_model_func=default_vlm_model_func,
        context_extractor=None,
        item_info=None,
        image_name=image_name,
    )
    print("generator result:")
    print(result)
    return result


def test_interceptor(image_bytes: bytes, output_dir: str, save_name: str, enable_caption: bool):
    print("\n[2/2] 测试 MyImageInterceptor.write ...")
    os.makedirs(output_dir, exist_ok=True)

    interceptor = MyImageInterceptor(
        parent_dir=output_dir,
        vlm_model_func=default_vlm_model_func,
        context_extractor=None,
        enable_caption=enable_caption,
    )
    interceptor.write(save_name, image_bytes)

    saved_path = os.path.join(output_dir, save_name)
    print(f"写入文件: {saved_path}")
    print(f"文件存在: {os.path.exists(saved_path)}")
    print("image_descriptions:")
    print(interceptor.image_descriptions)
    return interceptor.image_descriptions


def main():
    args = parse_args()
    image_path = Path(args.image)

    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    # 关键配置提示（不打印完整 key）
    base_url = os.getenv("MM_VLM_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("MM_VLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
    api_key = os.getenv("MM_VLM_API_KEY", "")
    print("当前配置:")
    print(f"MM_VLM_BASE_URL={base_url}")
    print(f"MM_VLM_MODEL={model}")
    print(f"MM_VLM_API_KEY={'已设置' if api_key else '未设置(将使用代码内默认)'}")

    image_bytes = image_path.read_bytes()

    # 1) 直接测 generator
    asyncio.run(test_generator(image_bytes=image_bytes, image_name=image_path.name))

    # 2) 测完整拦截写入链路
    test_interceptor(
        image_bytes=image_bytes,
        output_dir=args.output_dir,
        save_name=args.save_name,
        enable_caption=args.enable_caption,
    )

    print("\n测试完成。")


if __name__ == "__main__":
    main()