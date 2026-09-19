from fastapi import FastAPI
from pydantic import BaseModel

from rag import ask


app = FastAPI(
    title="Agriculture Knowledge Graph RAG"
)


class Question(BaseModel):

    question: str


@app.get("/")
def home():

    return {
        "message": "Agriculture KG-RAG API is running"
    }


@app.post("/ask")
def ask_question(
    request: Question
):

    result = ask(
        request.question
    )

    return result