from fastapi import FastAPI
from app.routes import hello

app = FastAPI()

app.include_router(hello.router)

@app.get("/")
def root():
    return {"message": "Welcome to FastAPI!"}
