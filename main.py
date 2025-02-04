from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from .parser import EmailParser
from .database import Database
import json
import os

# Get the current directory
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Email Parser API",
    description="API for parsing meeting-related emails",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount templates and static files
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

email_parser = EmailParser()

@app.on_event("startup")
async def startup_db_client():
    await Database.connect_db()

@app.on_event("shutdown")
async def shutdown_db_client():
    await Database.close_db()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        "index.html", 
        {"request": request}
    )

@app.post("/parse")
async def parse_email(request: Request):
    try:
        # Get the raw body content
        body = await request.body()
        content_type = request.headers.get("content-type", "").lower()

        # Extract email_text based on content type
        if "application/json" in content_type:
            try:
                data = json.loads(body)
                email_text = data.get("email_text")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON format")
        elif "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            email_text = form.get("email_text")
        else:
            try:
                email_text = body.decode()
            except:
                email_text = None

        if not email_text:
            raise HTTPException(
                status_code=400,
                detail="email_text is required in either JSON or form data"
            )

        # Parse the email
        parsed_data = email_parser.parse_email(email_text)
        
        # Save to database
        saved_data = await Database.save_responses([parsed_data])
        
        return JSONResponse(content=saved_data)

    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

# Only run uvicorn server in development
if __name__ == "__main__":
    import uvicorn
    # Check if running in development
    if os.getenv("VERCEL_ENV") is None:
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 