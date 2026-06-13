from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import users, tasks,ai,profiles,resources,quizzes,plans,agent
app = FastAPI()
app.include_router(agent.router)
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
    return FileResponse("static/index.html")

