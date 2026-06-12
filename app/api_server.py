from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import ask_jarvis

app = FastAPI()


class AskRequest(BaseModel):
    query: str


@app.post("/ask")
async def ask(req: AskRequest):
    answer = await ask_jarvis(req.query)
    return {"answer": answer}

@app.get("/ping")
def ping():
    return {"answer": "Jarvis API is reachable."}