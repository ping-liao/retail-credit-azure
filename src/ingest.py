"""
ingest.py — Download LendingClub dataset from Kaggle → ADLS Gen2 bronze/
"""
import os
import tempfile
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.filedatalake import DataLakeServiceClient

KV_URL       = "https://kv-retail-credit-rc01.vault.azure.net/"
STORAGE_ACCT = "stretailcreditrc01"
ADLS_URL     = f"https://{STORAGE_ACCT}.dfs.core.windows.net"
BRONZE       = "bronze"
DATASET      = "wordsforthewise/lending-club"


def main():
    credential = DefaultAzureCredential()

    # Load Kaggle credentials from Key Vault
    kv = SecretClient(vault_url=KV_URL, credential=credential)
    os.environ["KAGGLE_USERNAME"] = kv.get_secret("kaggle-username").value
    os.environ["KAGGLE_KEY"]      = kv.get_secret("kaggle-key").value
    print("Kaggle credentials loaded from Key Vault")

    # Download dataset to temp dir
    import kaggle
    kaggle.api.authenticate()
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Downloading {DATASET} ...")
        kaggle.api.dataset_download_files(DATASET, path=tmpdir, unzip=True)

        # Upload every file to bronze/lending-club/
        fs = DataLakeServiceClient(ADLS_URL, credential=credential) \
               .get_file_system_client(BRONZE)

        for f in Path(tmpdir).rglob("*"):
            if f.is_file():
                remote = f"lending-club/{f.name}"
                fc = fs.get_file_client(remote)
                data = f.read_bytes()
                fc.upload_data(data, overwrite=True, length=len(data))
                print(f"  Uploaded {remote}  ({f.stat().st_size / 1e6:.1f} MB)")

    print("✅ Ingest complete — data in bronze/lending-club/")


if __name__ == "__main__":
    main()
