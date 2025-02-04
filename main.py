from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from parser import EmailParser
import json

# Get the current directory
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Email Parser API",
    description="API for parsing meeting-related emails",
    version="1.0.0"
)

# Mount templates and static files
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

email_parser = EmailParser()

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
        return JSONResponse(content=parsed_data)
            
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 