# 所有的依赖和配置项都在startup里面配置好

if __name__ == "__main__":
    # 把依赖的配置项放在这里的目的
    # 就是防止新创建的子进程重复加载配置项
    from loguru import logger
    from startup import *
    import uvicorn
    from route.pdf_route import router as pdf_router
    from fastapi import FastAPI
    # 预加载vlm模型
    from processor.warmup.vlm_predictor_warmup import predictor
    app = FastAPI() # 启动服务
    app.include_router(pdf_router)
    logger.info("启动FastAPI服务，监听端口8000")
    uvicorn.run(app, host="0.0.0.0", port=5116)
