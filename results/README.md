# Experimental results

The cloud preflight is complete and the pilot is **BLOCKED**. No candidate worker,
ingestion or question ran. See [COMPARISON.md](COMPARISON.md),
[cloud-capabilities.json](cloud-capabilities.json) and [run-manifest.json](run-manifest.json).

`preflight/` contains actual command evidence and the failed isolated Codex CLI
capability trace. Candidate JSONL files are explicitly marked NOT_RUN schedules,
with null telemetry, rather than worker measurements. No oracle was generated.
Engine version and license verification remain incomplete.

Reproduce artifact checks with `python3 scripts/validate-cloud-results.py` and
`python3 -m unittest discover -s tests -v` from the repository root. Re-running
`python3 -m benchkit.cloud_report` requires the saved denial evidence and refuses
changes to frozen public inputs. Do not score NOT_RUN records as abstentions.
