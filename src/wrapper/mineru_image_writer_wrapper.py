import argparse
import asyncio
import os
import threading
from pathlib import Path

import httpx
from loguru import logger
from mineru.data.data_reader_writer import FileBasedDataWriter
API_KEY = "sk-hyftruqbzgbteyuhuatympczxvkecwtrzevwdftxsqfxtrer"


def _extract_message_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "\n".join(p for p in parts if p)
    return str(content)


async def default_vlm_model_func(prompt: str, system_prompt: str, image_data: str) -> str:
    base_url = os.getenv("MM_VLM_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
    model = os.getenv("MM_VLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
    api_key = os.getenv("MM_VLM_API_KEY", API_KEY)
    timeout = float(os.getenv("MM_VLM_TIMEOUT", "60"))

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                ],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()

    content = body["choices"][0]["message"]["content"]
    return _extract_message_content(content)


class MyImageInterceptor(FileBasedDataWriter):
    def __init__(self, parent_dir, vlm_model_func=None, context_extractor=None, enable_caption=None, save_image=True):
        super().__init__(parent_dir)
        self.image_descriptions = {}
        self.context_extractor = context_extractor
        self.save_image = save_image
        self.enable_caption = (
            enable_caption
            if enable_caption is not None
            else os.getenv("MINERU_IMAGE_CAPTION_ENABLE", "false").lower() in ("1", "true", "yes")
        )
        self.vlm_model_func = vlm_model_func or default_vlm_model_func

    @staticmethod
    def _run_async(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result = {}
        error = {}

        def _runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:
                error["value"] = exc

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()

        if "value" in error:
            raise error["value"]
        return result.get("value")

    def write(self, path: str, data: bytes) -> None:
        if self.enable_caption and self.vlm_model_func:
            from processor.enhancer.image_caption_generator import generate_enhanced_caption_from_bytes

            async def get_caption():
                result = await generate_enhanced_caption_from_bytes(
                    image_bytes=data,
                    vlm_model_func=self.vlm_model_func,
                    context_extractor=self.context_extractor,
                    image_name=path,
                )
                if result and result.get("success"):
                    return result.get("enhanced_caption")
                return None

            try:
                logger.info(f"Start generating caption for {path}")
                description = self._run_async(get_caption())
                if description:
                    self.image_descriptions[path] = description
                    logger.info(f"Caption generated for {path}: {description[:100]}...")
                else:
                    logger.warning(f"Generated caption is empty for {path}")
            except Exception as e:
                logger.error(f"Caption generation failed for {path}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())

        if self.save_image:
            super().write(path, data)


def _parse_args():
    parser = argparse.ArgumentParser(description="测试图片描述完整流程")
    parser.add_argument("--image", required=True, help="测试图片绝对路径")
    parser.add_argument("--output-dir", default="./tmp_test_output", help="保存图片目录（仅 --save-image 时生效）")
    parser.add_argument("--save-name", default="test_image.png", help="保存文件名（仅 --save-image 时生效）")
    parser.add_argument("--enable-caption", action="store_true", help="是否启用描述生成")
    parser.add_argument("--save-image", action="store_true", help="是否同时保存图片（默认不保存）")
    return parser.parse_args()


async def _test_generator(image_bytes: bytes, image_name: str):
    from processor.enhancer.image_caption_generator import generate_enhanced_caption_from_bytes

    result = await generate_enhanced_caption_from_bytes(
        image_bytes=image_bytes,
        vlm_model_func=default_vlm_model_func,
        context_extractor=None,
        item_info=None,
        image_name=image_name,
    )
    logger.info(f"generator result: {result}")


def _test_interceptor(image_bytes: bytes, output_dir: str, save_name: str, enable_caption: bool, save_image: bool):
    if save_image:
        os.makedirs(output_dir, exist_ok=True)
    interceptor = MyImageInterceptor(
        parent_dir=output_dir,
        vlm_model_func=default_vlm_model_func,
        context_extractor=None,
        enable_caption=enable_caption,
        save_image=save_image,
    )
    interceptor.write(save_name, image_bytes)
    if save_image:
        saved_path = os.path.join(output_dir, save_name)
        logger.info(f"saved path: {saved_path}, exists={os.path.exists(saved_path)}")
    logger.info(f"image_descriptions: {interceptor.image_descriptions}")


def main():
    args = _parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    logger.info(f"MM_VLM_BASE_URL={os.getenv('MM_VLM_BASE_URL', 'https://api.siliconflow.cn/v1')}")
    logger.info(f"MM_VLM_MODEL={os.getenv('MM_VLM_MODEL', 'Qwen/Qwen3-VL-8B-Instruct')}")

    image_bytes = image_path.read_bytes()
    asyncio.run(_test_generator(image_bytes=image_bytes, image_name=image_path.name))
    _test_interceptor(
        image_bytes=image_bytes,
        output_dir=args.output_dir,
        save_name=args.save_name,
        enable_caption=args.enable_caption,
        save_image=args.save_image,
    )


if __name__ == "__main__":
    main()