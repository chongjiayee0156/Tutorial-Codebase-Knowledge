# api.py

import sys
import subprocess
import os
import logging
import re # Import re for parsing repo name
from typing import Optional, List
from urllib.parse import urlparse # To help parse repo name

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
MAIN_SCRIPT_PATH = "main.py"
PYTHON_EXECUTABLE = sys.executable

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper Function to Get Project Name ---
def get_project_name_from_url(repo_url: str) -> Optional[str]:
    """Extracts project name from GitHub URL."""
    try:
        path = urlparse(repo_url).path
        # Remove leading slash and .git suffix if present
        name = path.lstrip('/').replace('.git', '')
        # Get the last part of the path
        project_name = name.split('/')[-1]
        if project_name:
            return project_name
    except Exception:
        pass # Ignore parsing errors
    return None

# --- Input Data Model (using Pydantic) ---
class GenerationRequest(BaseModel):
    repo_url: str
    name: Optional[str] = None
    token: Optional[str] = None
    output: str = Field(default="output")
    include: Optional[List[str]] = None
    exclude: Optional[List[str]] = None
    max_size: Optional[int] = None

# --- FastAPI App ---
app = FastAPI(
    title="Codebase Tutorial Generator API",
    description="API to trigger the generation of tutorials from GitHub codebases.",
    version="1.0.0",
)

# --- CORS Middleware ---
origins = [
    "http://127.0.0.1:5500", # VS Code Live Server default
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "null", # file:// origin
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- End CORS Middleware ---


# --- API Endpoint ---
@app.post(
    "/generate",
    summary="Trigger Tutorial Generation",
    description="Accepts repository details and options, then runs the tutorial generation script.",
    status_code=status.HTTP_200_OK
)
async def generate_tutorial(request_data: GenerationRequest):
    """
    API endpoint to trigger tutorial generation. Returns final output path on success.
    """
    # --- Determine Project Name (needed for final path) ---
    project_name = request_data.name
    if not project_name:
        project_name = get_project_name_from_url(request_data.repo_url)
        if not project_name:
             # If name wasn't provided and couldn't be derived, raise an error early
             # Or alternatively, let main.py handle it, but we need it for the return path.
             logger.error(f"Could not derive project name from URL: {request_data.repo_url}")
             raise HTTPException(
                 status_code=status.HTTP_400_BAD_REQUEST,
                 detail="Project name not provided and could not be derived from repository URL."
             )
    
    # --- Calculate Expected Final Output Path ---
    # This mirrors the logic in CombineTutorial.prep
    # Ensure forward slashes for URL compatibility later, though os.path.join is platform-aware
    expected_final_path = os.path.join(request_data.output, project_name, 'html').replace('\\', '/')


    # --- Build Command ---
    command = [PYTHON_EXECUTABLE, MAIN_SCRIPT_PATH, request_data.repo_url]
    # Use the derived or provided project name if specified (main.py will also derive if None)
    if request_data.name:
         command.extend(["-n", request_data.name])
    if request_data.token:
        command.extend(["-t", request_data.token])
    command.extend(["-o", request_data.output]) # Pass base output dir
    if request_data.max_size is not None:
        command.extend(["-s", str(request_data.max_size)])
    if request_data.include:
        for pattern in request_data.include:
            command.extend(["-i", pattern])
    if request_data.exclude:
        for pattern in request_data.exclude:
            command.extend(["-e", pattern])

    # --- Execute Script ---
    logger.info(f"Executing command: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ,
            encoding='utf-8'
        )

        logger.info(f"Script finished successfully.")
        logger.debug(f"Script stdout:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Script stderr:\n{result.stderr}")
        
        logger.info(f"Final output directory: {expected_final_path}")

        # --- Success Response ---
        # Return the *calculated* final path for redirection
        return {
            "message": "Tutorial generation completed successfully.",
            # Key changed for clarity
            "final_output_directory": expected_final_path, 
             # You could optionally still include stdout/stderr if needed for debugging
            # "script_stdout": result.stdout,
            # "script_stderr": result.stderr
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Script failed with exit code {e.returncode}")
        logger.error(f"Script stdout:\n{e.stdout}")
        logger.error(f"Script stderr:\n{e.stderr}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Script execution failed.",
                "details": "The tutorial generation script exited with an error.",
                "return_code": e.returncode,
                "script_stdout": e.stdout,
                "script_stderr": e.stderr
            }
        )
    except FileNotFoundError:
        error_msg = f"Error: Script '{MAIN_SCRIPT_PATH}' or Python '{PYTHON_EXECUTABLE}' not found."
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Server configuration error.", "details": error_msg}
        )
    except Exception as e:
        logger.exception("An unexpected error occurred during script execution.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "An unexpected internal server error occurred.", "details": str(e)}
        )

# --- Root endpoint ---
@app.get("/", summary="Health Check")
async def read_root():
    return {"message": "Tutorial Generator API is running."}

# --- Uvicorn runner ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)