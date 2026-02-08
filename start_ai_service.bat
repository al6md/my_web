@echo off
echo Starting AI Engine on port 8001...
cd ai_engine
uvicorn main:app --reload --port 8001
pause
