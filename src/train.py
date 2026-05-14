import io
import json
import pandas as pd
import numpy as np
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    roc_auc_score, f1_score, accuracy_score,
    precision_score, recall_score, classification_report,
)
import xgboost as xgb
import lightgbm as lgb
import mlflow
import mlflow.sklearn
import mlflow.xgboost
import mlflow.lightgbm
import joblib, tempfile, os

STORAGE_ACCOUNT = "stretailcreditrc01"
SILVER_CONTAINER = "silver"
GOLD_CONTAINER = "gold"
SILVER_PATH = "lending-club/accepted_cleaned.parquet"
GOLD_PATH = "lending-club/scored_predictions.parquet"

FEATURES = [
    "loan_amnt", "term", "int_rate", "installment", "annual_inc",
    "dti", "delinq_2yrs", "open_acc", "pub_rec", "revol_bal",
    "revol_util", "total_acc", "inq_last_6mths", "mths_since_last_delinq",
    "fico_mid", "loan_to_income", "credit_age_months", "grade_int",
    "ever_delinq", "emp_length",
]
TARGET = "default"


def get_adls_client():
    credential = DefaultAzureCredential()
    return DataLakeServiceClient(
        account_url=f"https://{STORAGE_ACCOUNT}.dfs.core.windows.net",
        credential=credential,
    )


def read_silver(client):
    print("Reading silver parquet...")
    file_client = (
        client.get_file_system_client(SILVER_CONTAINER)
        .get_file_client(SILVER_PATH)
    )
    data = file_client.download_file().readall()
    df = pd.read_parquet(io.BytesIO(data))
    print(f"  {len(df):,} rows loaded")
    return df


def prepare_data(df):
    df = df.dropna(subset=FEATURES + [TARGET])
    X = df[FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  Train: {len(X_train):,}  Test: {len(X_test):,}")
    print(f"  Default rate — train: {y_train.mean():.2%}  test: {y_test.mean():.2%}")
    return X_train, X_test, y_train, y_test


def evaluate(model, X_test, y_test):
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    return {
        "auc_roc":   round(roc_auc_score(y_test, y_prob), 4),
        "f1":        round(f1_score(y_test, y_pred), 4),
        "accuracy":  round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred), 4),
        "recall":    round(recall_score(y_test, y_pred), 4),
    }


def train_logistic(X_train, y_train):
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")),
    ])
    model.fit(X_train, y_train)
    return model


def train_xgboost(X_train, y_train):
    scale = (y_train == 0).sum() / (y_train == 1).sum()
    model = xgb.XGBClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        scale_pos_weight=scale,
        use_label_encoder=False,
        eval_metric="auc",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model


def train_lightgbm(X_train, y_train):
    scale = (y_train == 0).sum() / (y_train == 1).sum()
    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        scale_pos_weight=scale,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(X_train, y_train)
    return model


def write_gold(client, model, X_test, y_test):
    print(f"Writing scored predictions to gold/{GOLD_PATH}...")
    results = X_test.copy()
    results["actual_default"] = y_test.values
    results["predicted_default"] = model.predict(X_test)
    results["default_probability"] = model.predict_proba(X_test)[:, 1]

    buffer = io.BytesIO()
    results.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    fs_client = client.get_file_system_client(GOLD_CONTAINER)
    file_client = fs_client.get_file_client(GOLD_PATH)
    file_client.upload_data(buffer.read(), overwrite=True)
    print(f"  Done — {len(results):,} rows written")


def main():
    client = get_adls_client()
    df = read_silver(client)
    X_train, X_test, y_train, y_test = prepare_data(df)

    candidates = {
        "logistic_regression": train_logistic,
        "xgboost":             train_xgboost,
        "lightgbm":            train_lightgbm,
    }

    results = {}
    mlflow.set_experiment("retail-credit-default-risk")

    for name, train_fn in candidates.items():
        print(f"\nTraining {name}...")
        with mlflow.start_run(run_name=name):
            model = train_fn(X_train, y_train)
            metrics = evaluate(model, X_test, y_test)
            results[name] = {"model": model, "metrics": metrics}

            mlflow.log_params({"model_type": name, "n_features": len(FEATURES)})
            mlflow.log_metrics(metrics)


            print(f"  AUC-ROC: {metrics['auc_roc']}  F1: {metrics['f1']}  Accuracy: {metrics['accuracy']}")

    # pick winner by AUC-ROC
    winner_name = max(results, key=lambda n: results[n]["metrics"]["auc_roc"])
    winner_model = results[winner_name]["model"]
    winner_metrics = results[winner_name]["metrics"]

    print(f"\nWinner: {winner_name}")
    print(json.dumps(winner_metrics, indent=2))
    print(classification_report(y_test, winner_model.predict(X_test),
                                target_names=["Fully Paid", "Charged Off"]))

    # register winner in AML Model Registry via MLflow
    with tempfile.TemporaryDirectory() as tmp:
        model_path = os.path.join(tmp, "model.joblib")
        joblib.dump(winner_model, model_path)
        with open(model_path, "rb") as f:
            fs_client = client.get_file_system_client(GOLD_CONTAINER)
            fs_client.get_file_client("lending-club/model.joblib").upload_data(f.read(), overwrite=True)
    print(f"  Winner model saved to gold/lending-club/model.joblib")

    write_gold(client, winner_model, X_test, y_test)
    print("\nTraining complete.")


if __name__ == "__main__":
    main()