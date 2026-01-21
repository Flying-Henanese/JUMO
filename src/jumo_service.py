# 所有的依赖和配置项都在startup里面配置好

if __name__ == "__main__":
    # 把依赖的配置项放在这里的目的
    # 就是防止新创建的子进程重复加载配置项
    import os
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
    from loguru import logger
    from startup import *
    import uvicorn
    from route.pdf_route import router as pdf_router
    from route.documents_route import router as documents_router
    from route.content_searching_route import router as content_searching_router
    from fastapi import FastAPI
    app = FastAPI() # 启动服务
    app.include_router(pdf_router)
    app.include_router(documents_router)
    app.include_router(content_searching_router)
    port_num = int(os.getenv("API_SERVICE_PORT", 5116))
    logger.info(f"启动FastAPI服务，监听端口{port_num}")
    uvicorn.run(app, host="0.0.0.0", port=port_num)
