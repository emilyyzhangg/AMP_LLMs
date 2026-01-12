@echo off
echo === NCT Lookup API Setup ===

REM Create results directory
if not exist results mkdir results

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Check .env file
if not exist .env (
    echo Creating .env file...
    (
        echo # SERP API Key
        echo SERPAPI_KEY=c4c32ac751923eafd8d867eeb14c433e245aebfdbc0261cb2a8357e08ca34ff0
        echo.
        echo # NCBI API Key
        echo NCBI_API_KEY=ca84a2b20dc7059e4d06c9fd4ee52678c508
    ) > .env
)

REM Start API
echo.
echo Starting NCT Lookup API on port 9000...
echo API Documentation: http://localhost:9000/docs
echo.
uvicorn nct_api:app --reload --port 9000