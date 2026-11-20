# Thin wrappers around the rbc-bi CLI (macOS/Linux, or Windows with make installed).
# On Windows without make, run the rbc-bi commands directly (see README).

ifeq ($(OS),Windows_NT)
  BIN := .venv/Scripts
else
  BIN := .venv/bin
endif

.PHONY: setup data validate run test snapshot schema

setup:
	python -m venv .venv
	$(BIN)/python -m pip install --upgrade pip setuptools
	$(BIN)/python -m pip install -e ".[dev]"
	$(BIN)/python -m pip install playwright && $(BIN)/python -m playwright install chromium

data:
	$(BIN)/rbc-bi data

validate:
	$(BIN)/rbc-bi validate

run:
	$(BIN)/rbc-bi run

test:
	$(BIN)/python -m pytest -q

snapshot:
	$(BIN)/rbc-bi snapshot $(DASH)

schema:
	$(BIN)/rbc-bi schema
