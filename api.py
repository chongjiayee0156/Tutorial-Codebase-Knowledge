# api.py

import sys
import subprocess
import os
import logging
import re 
from typing import Optional, List
from urllib.parse import urlparse
from pathlib import Path # Better path handling

# Import dotenv and load environment variables
from dotenv import load_dotenv
load_dotenv() 

from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel, Field, model_validator # Use model_validator for Pydantic v2+

from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
MAIN_SCRIPT_PATH = "main.py"
PYTHON_EXECUTABLE = sys.executable

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def get_project_name_from_source(repo_url: Optional[str], local_dir: Optional[str]) -> Optional[str]:
    """Extracts project name from GitHub URL or local directory path."""
    try:
        if repo_url:
            path = urlparse(repo_url).path
            name = path.lstrip('/').replace('.git', '')
            project_name = name.split('/')[-1]
            if project_name:
                return project_name
        elif local_dir:
            # Use Pathlib for robust path handling
            return Path(local_dir).name
    except Exception as e:
        logger.warning(f"Could not automatically derive project name: {e}")
    return None

# --- Input Data Model (using Pydantic) ---
class GenerationRequest(BaseModel):
    # Make both optional, validation will enforce one is chosen
    repo_url: Optional[str] = Field(default=None, description="URL of the public GitHub repository.")
    local_dir: Optional[str] = Field(default=None, description="Path to the local directory.")
    
    name: Optional[str] = Field(default=None, description="Project name (optional, derived if omitted).")
    token: Optional[str] = Field(default=None, description="GitHub token (only used if repo_url is provided).")
    output: str = Field(default="output", description="Base directory for output.")
    include: Optional[List[str]] = Field(default=None, description="Include file patterns.")
    exclude: Optional[List[str]] = Field(default=None, description="Exclude file patterns.")
    max_size: Optional[int] = Field(default=None, description="Maximum file size in bytes.")

    # Pydantic v2+ model validator
    @model_validator(mode='before')
    @classmethod
    def check_source_provided(cls, data):
        if isinstance(data, dict): # Ensure it's dictionary-like access
            repo_url = data.get('repo_url')
            local_dir = data.get('local_dir')

            if not repo_url and not local_dir:
                raise ValueError("Either 'repo_url' or 'local_dir' must be provided.")
            if repo_url and local_dir:
                raise ValueError("Provide either 'repo_url' or 'local_dir', not both.")
        return data

    # Additional validation (optional): Check if local_dir exists if provided
    # Be careful with this on a web server due to security/permissions
    # @validator('local_dir')
    # def check_local_dir_exists(cls, v):
    #     if v and not Path(v).is_dir():
    #         raise ValueError(f"Local directory not found: {v}")
    #     return v

# --- FastAPI App ---
app = FastAPI(
    title="Codebase Tutorial Generator API",
    description="API to trigger the generation of tutorials from GitHub codebases or local directories.",
    version="1.1.0", # Version bump
)

# --- CORS Middleware ---
origins = [
    "http://127.0.0.1:5500", 
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "null",
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
    description="Accepts repository URL *or* local directory path and options, then runs the tutorial generation script.",
    status_code=status.HTTP_200_OK
)
async def generate_tutorial(request_data: GenerationRequest):
    """
    API endpoint to trigger tutorial generation. Validates input, builds the
    correct CLI command, executes it, and returns the final output path on success.
    """
    # --- Determine Project Name ---
    project_name = request_data.name
    if not project_name:
        project_name = get_project_name_from_source(request_data.repo_url, request_data.local_dir)
        if not project_name:
             source = request_data.repo_url or request_data.local_dir
             logger.error(f"Could not derive project name from source: {source}")
             raise HTTPException(
                 status_code=status.HTTP_400_BAD_REQUEST,
                 detail=f"Project name not provided and could not be derived from source: {source}"
             )
    
    # --- Calculate Expected Final Output Path ---
    # Ensure forward slashes for URL compatibility
    expected_final_path = os.path.join(request_data.output, project_name, 'html').replace('\\', '/')
    # SECURITY WARNING: Allowing generation from arbitrary local paths specified
    # via an API can be a security risk if the API is exposed publicly.
    # Ensure the server running this API has appropriate permissions and trust.
    if request_data.local_dir:
        logger.warning(f"Processing local directory request: {request_data.local_dir}. Ensure server permissions are secure.")


    # --- Build Command ---
    command = [PYTHON_EXECUTABLE, MAIN_SCRIPT_PATH]

    # Add source argument (--repo or --dir)
    if request_data.repo_url:
        command.extend(["--repo", request_data.repo_url])
        # Only add token if using repo
        if request_data.token:
            command.extend(["-t", request_data.token])
    elif request_data.local_dir:
        command.extend(["--dir", request_data.local_dir])

    # Add common optional arguments
    if request_data.name: # Pass name explicitly if provided
         command.extend(["-n", request_data.name])
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

        # --- Success Response ---
        return {
            "message": "Tutorial generation completed successfully.",
            "final_output_directory": expected_final_path,
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