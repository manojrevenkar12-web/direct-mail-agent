PY := PYTHONPATH=src python3

lint:        ## ruff format --check and ruff check
	ruff format --check src tests scripts && ruff check src tests scripts
test:        ## all Python tests, including dbt on DuckDB (about 15 seconds)
	$(PY) -m pytest -q
web-test:    ## typecheck, tests and build for the approval console
	cd web && npx tsc --noEmit && npx vitest run && npx vite build
demo:        ## three rounds on a small market, printed
	$(PY) -m mail_eval.demo demo --rounds 3
dev:         ## the development split: 7 policies x 5 seeds x 12 rounds (about 5 minutes)
	$(PY) scripts/evaluate.py dev
lock-check:  ## the held-out lock still verifies
	$(PY) scripts/lock.py verify heldout2
report:      ## RESULTS.md and web/public/data/console.json from reports/*.json
	$(PY) scripts/report.py
dbt:         ## regenerate the warehouse model from config/suppressions.yaml and build it on DuckDB
	$(PY) scripts/gen_dbt.py && $(PY) scripts/dbt_check.py /tmp/dma-dbt
