# Groove Grind

Groove Grind is a Beatport browser that scrapes `www.beatport.com/_next/data/*` JSON endpoints to search artists and labels and surface an artist's top 10, their labels ordered by first release date, and their full track history grouped by label. Flask serves a compiled Svelte SPA from the same process and also proxies the Beatport-scraping endpoints.

## Local development

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The dev server runs at http://127.0.0.1:5000.

### Frontend

```bash
cd client
npm install
npm run autobuild
```

`npm run autobuild` rebuilds `client/public/bundle.{js,css}` on change. Flask serves `client/public/` directly, so prefer `autobuild` over `npm run dev` (which also spins up a redundant `sirv` static server).

## Running tests

```bash
python -m unittest discover -v
```

Tests hit live Beatport and include exact-count assertions (for example `len(john.tracks) == 25`) that drift as artist catalogs change. Treat failures as "data changed" before "scraper broke."

## Azure deployment

### Prerequisites

- An Azure subscription.
- The `az` CLI installed and logged in (`az login`).
- The repository pushed to GitHub.

### One-time Azure provisioning

Set the variables once per shell, then run the commands below in order.

```bash
RESOURCE_GROUP="groove-grind"
APP_NAME="groove-grind"
PLAN_NAME="flask-plan"
LOCATION="westeurope"
```

Create the resource group:

```bash
az group create --name $RESOURCE_GROUP --location $LOCATION
```

Create a Linux App Service plan on the B1 tier:

```bash
az appservice plan create \
  --name $PLAN_NAME \
  --resource-group $RESOURCE_GROUP \
  --sku B1 \
  --is-linux
```

Create the web app on Python 3.11:

```bash
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan $PLAN_NAME \
  --name $APP_NAME \
  --runtime "PYTHON|3.11"
```

Set the gunicorn startup command:

```bash
az webapp config set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"
```

Configure app settings. `SCM_DO_BUILD_DURING_DEPLOYMENT=true` tells Azure to run `pip install` on the uploaded package. `FLASK_SECRET_KEY` is intended to replace the hardcoded placeholder in `app.py:9` — generate a random value (`python -c 'import secrets; print(secrets.token_hex(32))'`) and set it now:

```bash
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true FLASK_SECRET_KEY=<paste-generated-value>
```

Note: `app.py` still has `app.secret_key = 'make_this_an_env'` hardcoded. Setting the app setting alone is not enough — the code must be changed to read `os.environ['FLASK_SECRET_KEY']` before the setting takes effect. This is tracked in Known issues below.

Download the publish profile XML. This is the credential the GitHub Actions workflow uses to deploy:

```bash
az webapp deployment list-publishing-profiles \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --xml > publish-profile.xml
```

Open `publish-profile.xml` and copy its full contents — it goes into a GitHub secret in the next step. Delete the local file afterwards.

### GitHub Actions wiring

`.github/workflows/azure-webapps-python.yml` runs on every push to `main`. It builds the Svelte bundle, installs Python dependencies, and deploys via `azure/webapps-deploy@v3`. It requires two repository secrets (Settings -> Secrets and variables -> Actions):

- `AZURE_WEBAPP_NAME` — the value of `$APP_NAME` (for example `groove-grind`).
- `AZURE_CREDENTIALS` — the full XML contents of the publish profile downloaded above.

Footgun: the secret is named `AZURE_CREDENTIALS` but the workflow passes it to the `publish-profile` input of `azure/webapps-deploy@v3`, which expects publish-profile XML — not the service-principal JSON that `AZURE_CREDENTIALS` usually implies. Rename this secret to `AZURE_WEBAPP_PUBLISH_PROFILE` in a future PR to match its actual contents.

### Tailing logs

```bash
az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP
```

## Known issues / TODO

- `app.secret_key` in `app.py:9` is hardcoded to `'make_this_an_env'`. Replace with `os.environ['FLASK_SECRET_KEY']` before any production traffic; the Azure app setting is already plumbed above and waiting.
- The test suite hits live Beatport with exact-count assertions that drift as catalogs update.
- The GitHub secret `AZURE_CREDENTIALS` actually holds publish-profile XML, not service-principal credentials. Rename to `AZURE_WEBAPP_PUBLISH_PROFILE` and update the workflow to match.
