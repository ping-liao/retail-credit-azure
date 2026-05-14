import io
import pandas as pd
import numpy as np
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

STORAGE_ACCOUNT = "stretailcreditrc01"
BRONZE_CONTAINER = "bronze"
SILVER_CONTAINER = "silver"
INPUT_PATH = "lending-club/accepted_2007_to_2018Q4.csv"
OUTPUT_PATH = "lending-club/accepted_cleaned.parquet"

COLS = [
    "loan_amnt", "funded_amnt", "term", "int_rate", "installment",
    "grade", "sub_grade", "emp_length", "home_ownership", "annual_inc",
    "verification_status", "issue_d", "loan_status", "purpose",
    "addr_state", "dti", "delinq_2yrs", "fico_range_low", "fico_range_high",
    "open_acc", "pub_rec", "revol_bal", "revol_util", "total_acc",
    "inq_last_6mths", "mths_since_last_delinq", "earliest_cr_line",
]


def get_adls_client():
    credential = DefaultAzureCredential()
    return DataLakeServiceClient(
        account_url=f"https://{STORAGE_ACCOUNT}.dfs.core.windows.net",
        credential=credential,
    )


def read_bronze(client):
    print(f"Reading {INPUT_PATH} from bronze...")
    file_client = (
        client.get_file_system_client(BRONZE_CONTAINER)
        .get_file_client(INPUT_PATH)
    )
    download = file_client.download_file()
    df = pd.read_csv(io.BytesIO(download.readall()), usecols=COLS, low_memory=False)
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def clean(df):
    print("Cleaning...")

    df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])].copy()
    print(f"  After filtering to closed loans: {len(df):,} rows")

    df["default"] = (df["loan_status"] == "Charged Off").astype(int)


    df["int_rate"] = pd.to_numeric(df["int_rate"].astype(str).str.rstrip("%"), errors="coerce")
    df["revol_util"] = pd.to_numeric(df["revol_util"].astype(str).str.rstrip("%"), errors="coerce")

    df["term"] = df["term"].str.strip().str.extract(r"(\d+)").astype(int)

    df["emp_length"] = (
        df["emp_length"]
        .str.replace("10+ years", "10", regex=False)
        .str.replace("< 1 year", "0", regex=False)
        .str.extract(r"(\d+)")
        .astype(float)
    )

    df["issue_d"] = pd.to_datetime(df["issue_d"], format="%b-%Y")
    df["earliest_cr_line"] = pd.to_datetime(df["earliest_cr_line"], format="%b-%Y")

    critical = ["annual_inc", "dti", "int_rate", "revol_util", "fico_range_low"]
    before = len(df)
    df = df.dropna(subset=critical)
    print(f"  Dropped {before - len(df):,} rows with missing critical fields")

    numeric_fill = ["mths_since_last_delinq", "inq_last_6mths", "open_acc", "total_acc"]
    for col in numeric_fill:
        df[col] = df[col].fillna(df[col].median())

    return df


def engineer_features(df):
    print("Engineering features...")

    df["fico_mid"] = (df["fico_range_low"] + df["fico_range_high"]) / 2
    df["loan_to_income"] = df["loan_amnt"] / df["annual_inc"].clip(lower=1)
    df["credit_age_months"] = (
        (df["issue_d"] - df["earliest_cr_line"]) / np.timedelta64(1, "M")
    ).astype(int)
    df["vintage_year"] = df["issue_d"].dt.year
    df["vintage_quarter"] = df["issue_d"].dt.to_period("Q").astype(str)

    grade_map = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}
    df["grade_int"] = df["grade"].map(grade_map)
    df["ever_delinq"] = (df["delinq_2yrs"] > 0).astype(int)

    return df


def write_silver(client, df):
    print(f"Writing {OUTPUT_PATH} to silver...")
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    fs_client = client.get_file_system_client(SILVER_CONTAINER)
    file_client = fs_client.get_file_client(OUTPUT_PATH)
    file_client.upload_data(buffer.read(), overwrite=True)
    print(f"  Done — {len(df):,} rows written to silver/{OUTPUT_PATH}")


def main():
    client = get_adls_client()
    df = read_bronze(client)
    df = clean(df)
    df = engineer_features(df)
    write_silver(client, df)
    print("\nPrep complete.")
    print(df[["loan_amnt", "int_rate", "grade", "dti", "fico_mid", "default"]].describe())


if __name__ == "__main__":
    main()