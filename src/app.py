# 所有的依赖和配置项都在startup里面配置好
from loguru import logger
from startup import *
import uvicorn
from route.pdf_route import router as pdf_router
from fastapi import FastAPI

app = FastAPI(docs_url=None, redoc_url=None) # 启动服务
app.include_router(pdf_router)

if __name__ == "__main__":
    logger.info("启动FastAPI服务，监听端口5116")
    uvicorn.run(app, host="0.0.0.0", port=5116)
