.DEFAULT_GOAL := help
PY := backend/.venv/bin/python

.PHONY: help setup backend frontend test demo up down logs docs clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the backend venv, install deps, copy .env
	python3 -m venv backend/.venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r backend/requirements.txt
	cd frontend && npm install
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

backend:  ## Run the shared memory service on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:  ## Run the dashboard on :3000
	cd frontend && npm run dev

test:  ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest -q

demo:  ## Drive the full loop against a running backend
	$(PY) backend/scripts/demo.py

up:  ## Start postgres + backend + frontend in docker
	docker compose up --build

down:  ## Stop the docker stack
	docker compose down

docs:  ## Rebuild the PDF specification from docs/
	$(PY) docs/build_pdf.py

clean:  ## Remove build artefacts
	rm -rf backend/.venv backend/.pytest_cache frontend/node_modules frontend/.next
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
