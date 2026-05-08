# Repository Instructions

## Environment

- Work from the repository root on Windows PowerShell.
- If network access fails, retry through the local proxy `http://127.0.0.1:10808`.
- Use `python -m pip install -r requirements.txt` for Python dependencies.
- Keep device identifiers, API keys, APKs, and account details out of tracked files. Use environment variables such as `ANDROID_SERIAL` and `JUDGE_API_KEY`.

## Project Scope

- `phone2app/` contains the reusable framework code.
- `configs/` contains checked-in sample configuration.
- `data/eval_cases/` contains curated evaluation cases that may be committed when intentionally updated.
- `tools/` contains runnable evaluation, analysis, and report-generation scripts.
- `reports/`, `tools/reports/`, `tmp/`, `apk-transfer/`, caches, screenshots, logs, traces, recordings, and local binaries are generated or machine-local artifacts and should not be committed.

## Development Rules

- Prefer small, focused changes that match the existing script style.
- Do not overwrite generated reports unless the task is explicitly about regenerating them.
- Do not commit extracted tool bundles such as `tools/scrcpy-*`; keep only source scripts and lightweight project metadata.
- For report analysis scripts, write outputs under `reports/compare_eval/` or another ignored report directory.
- For app automation scripts, keep package names and UI selectors visible in code only when they are product-generic or already part of the evaluation workflow.

## Validation

- For framework code changes, run `python -m pytest` when practical.
- For individual scripts, at minimum run `python -m py_compile <script>` or the PowerShell parser equivalent before committing.
- For generated HTML or image reports, verify the output path exists and opens locally before sharing it.
