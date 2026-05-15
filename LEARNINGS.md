# Learnings
Honest notes on what was hard and how it was solved.
## MLflow incompatibility with AML tracking server
MLflow 3.8.1 introduced a new `logged-models` API that AzureML's tracking server doesn't support yet.
`log_model()` throws a 404. Fix: skip `log_model`, save the model manually with `joblib.dump` to ADLS Gen2 instead. Use pre-installed `azureml-mlflow` on the compute instance — don't pip install mlflow separately.
## AML terminal bracketed paste mode
Pasting multi-line scripts into the AML terminal corrupts indentation due to bracketed paste mode being enabled by default.
Fix: run `printf '\e[?2004l'` before pasting, which disables it for the session.
## Synapse Serverless SQL: GO separator required
Unlike regular SQL Server, Synapse Serverless SQL requires a `GO` statement between each `CREATE VIEW` in a batch script. Without it, the batch fails silently on the second view onward.
## Synapse view column mismatch
The scored predictions Parquet file contains `grade_int` (integer encoding) but not the original `grade` string. All Synapse views must reference `grade_int` — referencing `grade` returns a column-not-found error.
## Dockerfile base image for ODBC
`python:3.11-slim` doesn't support the Microsoft ODBC driver installation cleanly. Pinning to `python:3.10-slim-bullseye` (Debian Bullseye) resolves the apt package compatibility issue.
