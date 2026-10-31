# Troubleshooting

## `flora ui` starts but the browser shows an error

- Check that the process is listening on the expected host and port
- Open `http://127.0.0.1:8765/api/status` directly and confirm the JSON response
- If using a compiled SPA, verify that `src/flora/ui/static/app/index.html` exists

## The UI loads but API calls fail

- Confirm that the request path starts with `/api/`
- Verify that the working directory exists and is writable
- Check the in-app log endpoint or console logs for handler errors

## The UI reports that the build is missing

That means the Angular SPA has not been built into the package assets yet. Run:

```bash
cd frontend/angular
npm install
npm run build
```

## Tests fail around the UI server

- Make sure no other process is occupying the selected port in manual runs
- Run `pytest tests/integration/test_ui_server.py -v` to isolate the smoke path
- If failures involve HTML rendering only, verify whether the embedded or built frontend mode is active

## Database or ingestion failures

- Confirm metadata, ASV table, and taxonomy files exist
- Validate required columns before ingestion
- Check `config.yaml` and `database.path` expectations relative to `--workdir`
