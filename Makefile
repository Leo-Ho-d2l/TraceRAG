.PHONY: install dev test lint up down migrate seed eval-retrieval eval-ablation

install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	ruff check .

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

seed:
	python scripts/seed_demo.py

eval-retrieval:
	python -m eval.run_retrieval --dataset eval/dataset.jsonl


eval-ablation:
	python -m eval.run_ablation
