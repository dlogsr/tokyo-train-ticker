.PHONY: dev install stop

dev:
	./dev.sh

install:
	python3 -m venv venv
	venv/bin/pip install -q -r backend/requirements.txt

stop:
	pkill -f "uvicorn main:app" || true
