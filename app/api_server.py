from fastapi import FastAPI
from pydantic import BaseModel

from app.tools.db_retrieval import search_components_records
from app.tools.note_search import read_note_content

app = FastAPI()

class SearchComponentsRequest(BaseModel):
    query: str


class ReadNoteRequest(BaseModel):
    notes_path: str


@app.post("/tools/search-components")
def search_components(req: SearchComponentsRequest):
    return search_components_records(req.query)


@app.post("/tools/read-note")
def read_note_tool(req: ReadNoteRequest):
    return read_note_content(req.notes_path)


@app.get("/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": "search-components",
                "method": "POST",
                "path": "/tools/search-components",
                "body": {"query": "raspberry pi"},
            },
            {
                "name": "read-note",
                "method": "POST",
                "path": "/tools/read-note",
                "body": {"notes_path": "notes/example.md"},
            },
        ]
    }


@app.get("/ping")
def ping():
    return {
        "answer": "Jarvis n8n tool API is reachable.",
        "n8n_ready": True,
    }
