.PHONY: up down logs verify debug clean setup build publish

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

verify:
	@bash scripts/verify.sh

debug:
	docker compose --profile debug up -d

clean:
	docker compose down -v

setup:
	@bash scripts/install.sh

build:
	uv build

publish:
	twine upload --skip-existing dist/*
