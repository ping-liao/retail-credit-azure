# Retail Credit Portfolio Analytics

A fully Azure-native retail credit risk dashboard built in Python.
Ingests LendingClub loan data, engineers features, trains a default-risk model,
and serves an interactive portfolio dashboard.

![Live Demo](https://img.shields.io/badge/demo-coming_soon-blue)

---

## Architecture

    Kaggle Dataset → Azure Data Factory → ADLS Gen2 (bronze)
                                               ↓
                                        AML Notebooks (prep)
                                               ↓
                                        ADLS Gen2 (silver)
                                               ↓
                                        AML (train: LR / XGBoost / LightGBM)
                                               ↓
                                        ADLS Gen2 (gold) → Synapse Serverless SQL
                                                                   ↓
                                                        Streamlit Dashboard
                                                                   ↓
                                                  Azure Container Apps (live)

---

## Progress

| Step | Description | Status |
|------|-------------|--------|
| 1 | Azure environment setup | ✅ Done |
| 2 | Data ingestion (Kaggle → ADLS bronze) | ✅ Done |
| 3 | Data prep & feature engineering (bronze → silver) | ✅ Done |
| 4 | Model training — LR / XGBoost / LightGBM, winner to gold | ✅ Done |
| 5 | Synapse Serverless SQL views over gold layer | ✅ Done |
| 6 | Plotly Dash dashboard (7 chart types) | 🔄 In progress |
| 7 | Containerize dashboard (Docker → ACR) | ⬜ Pending |
| 8 | CI/CD pipeline (GitHub Actions → Container Apps) | ⬜ Pending |
| 9 | Monitoring (Azure Monitor + App Insights) | ⬜ Pending |
| 10 | GitHub showcase polish (README, architecture diagram) | ⬜ Pending |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Storage | Azure Data Lake Storage Gen2 |
| Ingestion | Azure Data Factory + Python |
| Preparation | Python, pandas, pyarrow |
| Modelling | scikit-learn, XGBoost, LightGBM, MLflow |
| Serving | Azure Synapse Analytics (Serverless SQL) |
| Dashboard | Plotly Dash, Python |
| Hosting | Azure Container Apps |
| CI/CD | GitHub Actions |
| Secrets | Azure Key Vault |
| Auth | Azure Managed Identity |

---

## Dataset

[LendingClub Loan Data 2007–2018](https://www.kaggle.com/datasets/wordsforthewise/lending-club)
— 1.3M closed loans, 20 features after engineering, 19.5% default rate.

---

## Key Resource Names

| Resource | Name |
|----------|------|
| Resource Group | `rg-retail-credit` |
| Storage Account | `stretailcreditrc01` |
| AML Workspace | `aml-retail-credit-rc01` |
| Synapse | `synw-retail-credit-rc01` |
| Key Vault | `kv-retail-credit-rc01` |
| Container Registry | `acrretailcreditrc01` |