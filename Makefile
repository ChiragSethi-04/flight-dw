.PHONY: up down logs check-db test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f mysql

check-db:
	python run_all.py --check-db

test:
	pytest -q
