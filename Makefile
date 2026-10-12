.PHONY: api web test test-api test-web lint up

api:            ## run the FastAPI server on :8000
	cd study-mate-backend && .venv/bin/python run.py

web:            ## run the Next.js dev server on :3000
	cd studyMate-frontend && npm run dev

test: test-api test-web

test-api:
	cd study-mate-backend && EMBEDDING_PROVIDER=hashed .venv/bin/pytest -q

test-web:
	cd studyMate-frontend && npm test

lint:
	cd study-mate-backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd studyMate-frontend && npm run lint && npm run typecheck

up:             ## both halves in Docker
	docker compose up --build
