#!/bin/bash
# ── CONFIG — edit SUFFIX if any name is already taken ──────────────────────
LOCATION="centralus"
SUFFIX="rc01"
RG="rg-retail-credit"
STORAGE="stretailcredit${SUFFIX}"
ADF="adf-retail-credit-${SUFFIX}"
SYNAPSE="synw-retail-credit-${SUFFIX}"
AML="aml-retail-credit-${SUFFIX}"
KV="kv-retail-credit-${SUFFIX}"
ACR="acrretailcredit${SUFFIX}"
SYNAPSE_SQL_USER="sqladmin"
SYNAPSE_SQL_PASS="RetailCredit@2025!"   # change to your own password
# ───────────────────────────────────────────────────────────────────────────

set -e

echo "==> Installing ML extension..."
az extension add -n ml --upgrade -y 2>/dev/null || true

echo "==> 1. Resource Group"
az group create --name $RG --location $LOCATION

echo "==> 2. ADLS Gen2 + containers"
az storage account create \
  --name $STORAGE --resource-group $RG --location $LOCATION \
  --sku Standard_LRS --kind StorageV2 \
  --hierarchical-namespace true --output none

for fs in bronze silver gold synapse; do
  az storage fs create --name $fs --account-name $STORAGE \
    --auth-mode login --output none
  echo "    created: $fs"
done

echo "==> 3. Key Vault"
az keyvault create \
  --name $KV --resource-group $RG --location $LOCATION --output none

echo "==> 4. Azure Data Factory"
az datafactory create \
  --name $ADF --resource-group $RG --location $LOCATION --output none

echo "==> 5. Azure Container Registry"
az acr create \
  --name $ACR --resource-group $RG --location $LOCATION \
  --sku Basic --output none

echo "==> 6. Azure Machine Learning Workspace"
az ml workspace create \
  --name $AML --resource-group $RG --location $LOCATION --output none

echo "==> 7. Synapse Analytics Workspace"
az synapse workspace create \
  --name $SYNAPSE --resource-group $RG --location $LOCATION \
  --storage-account $STORAGE --file-system synapse \
  --sql-admin-login-user $SYNAPSE_SQL_USER \
  --sql-admin-login-password $SYNAPSE_SQL_PASS --output none

echo "==> 8. Synapse Firewall — allow Azure services"
az synapse workspace firewall-rule create \
  --workspace-name $SYNAPSE --resource-group $RG \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 --output none

echo "==> 9. Store secrets in Key Vault"
STORAGE_KEY=$(az storage account keys list \
  --account-name $STORAGE --resource-group $RG \
  --query '[0].value' -o tsv)

az keyvault secret set --vault-name $KV \
  --name "adls-storage-key" --value "$STORAGE_KEY" --output none
az keyvault secret set --vault-name $KV \
  --name "synapse-sql-password" --value "$SYNAPSE_SQL_PASS" --output none

echo "==> 10. Managed Identity: AML → ADLS"
AML_PRINCIPAL=$(az ml workspace show \
  --name $AML --resource-group $RG \
  --query identity.principalId -o tsv)
SUBSCRIPTION=$(az account show --query id -o tsv)

az role assignment create \
  --assignee $AML_PRINCIPAL \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/${SUBSCRIPTION}/resourceGroups/${RG}/providers/Microsoft.Storage/storageAccounts/${STORAGE}" \
  --output none

echo ""
echo "✅ Step 1 complete!"
echo "   Resource Group : $RG"
echo "   Storage        : $STORAGE"
echo "   ADF            : $ADF"
echo "   Synapse        : $SYNAPSE"
echo "   AML Workspace  : $AML"
echo "   Key Vault      : $KV"
echo "   ACR            : $ACR"
echo "   Region         : $LOCATION"
