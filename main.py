import pymysql

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from routers import users, tasks,ai,profiles,resources,quizzes,plans,agent,materials,evaluations,external_resources
from utils import error

app = FastAPI()


@app.exception_handler(pymysql.MySQLError)
async def mysql_exception_handler(request: Request, exc: pymysql.MySQLError):
    return JSONResponse(
        status_code=500,
        content=error(
            code=500,
            message="数据库连接失败，请检查 .env 中的 DATABASE_* 配置，并确认已导入 sql/init.sql。"
        )
    )

app.include_router(materials.router)
app.include_router(agent.router)
app.include_router(evaluations.router)
app.include_router(external_resources.router)
app.include_router(plans.router)
app.include_router(quizzes.router)
app.include_router(resources.router)
app.include_router(profiles.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(ai.router)

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/vue/index.html")

