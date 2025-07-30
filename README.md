# Groove Grid

## API - Flask
- Search for artists via Beatport API
- Get all tracks of an artist
- Get all labels an artist has released on
- Get top 10 tracks of an artist

### TODO
- Get all tracks of a label
- Get all artists of a label
- Get top 10 tracks of a label

## Front-end - Svelte
- Made to facilitate the use of the API

#### Svelte.js + Flask
Run the following for development:

- `python server.py` to start the Flask server.
- `cd client; npm install; npm run autobuild` to automatically build and reload the Svelte frontend when it's changed.

- `python -m venv .venv`
- `source .venv/bin/activate`
- `python -m pip install -r requirements.txt`
- `python -m pip freeze > requirements.txt`
- `deactivate`


```bash
# Variables (choose your own names)
RESOURCE_GROUP="groove-grind"
APP_NAME="groove-grind"
PLAN_NAME="flask-plan"
LOCATION="westeurope"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create App Service plan (Linux, Basic tier)
az appservice plan create --name $PLAN_NAME --resource-group $RESOURCE_GROUP --sku B1 --is-linux

# Create Web App
az webapp create --resource-group $RESOURCE_GROUP \
    --plan $PLAN_NAME \
    --name $APP_NAME \
    --runtime "PYTHON|3.11" \
    --deployment-local-git

az account show --query id --output tsv    # to find id
az ad sp create-for-rbac --name "flask-deploy-gh" --role contributor \
    --scopes /subscriptions/<your-subscription-id>/resourceGroups/groove-grind \
    --sdk-auth
```
