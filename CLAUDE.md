# TUFE_Rates (public data repo)
rates.json is written automatically each month by a GitHub Actions workflow (TCMB EVDS v3, series TP.TUKFIY2025.GENEL) that commits to main. The live apps read it.

## Rules
- Work only on branch agent-updates. Never push to main. Never force-push.
- Never edit rates.json by hand. Never rename files or change the JSON structure; only additive changes.
- Never commit secrets or personal data: this repo is public.
- Ask before changing the workflow file.
