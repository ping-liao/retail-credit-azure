CREATE DATABASE retail_credit;


CREATE MASTER KEY ENCRYPTION BY PASSWORD = 'RetailCredit2026!';

-- create credentials to access ADLS Gen2
CREATE DATABASE SCOPED CREDENTIAL SynapseIdentity
WITH IDENTITY = 'Managed Identity';

-- create external data source pointing to gold layer
CREATE EXTERNAL DATA SOURCE gold_lending_club
WITH (
    LOCATION = 'https://stretailcreditrc01.dfs.core.windows.net/gold/lending-club',
    CREDENTIAL = SynapseIdentity
);

-- create external table over scored predictions
CREATE EXTERNAL FILE FORMAT parquet_format
WITH (FORMAT_TYPE = PARQUET);

CREATE EXTERNAL TABLE dbo.scored_predictions (
    loan_amnt FLOAT,
    term INT,
    int_rate FLOAT,
    installment FLOAT,
    annual_inc FLOAT,
    dti FLOAT,
    delinq_2yrs FLOAT,
    open_acc FLOAT,
    pub_rec FLOAT,
    revol_bal FLOAT,
    revol_util FLOAT,
    total_acc FLOAT,
    inq_last_6mths FLOAT,
    mths_since_last_delinq FLOAT,
    fico_mid FLOAT,
    loan_to_income FLOAT,
    credit_age_months INT,
    grade_int INT,
    ever_delinq INT,
    emp_length FLOAT,
    actual_default INT,
    predicted_default INT,
    default_probability FLOAT
)
WITH (
    LOCATION = 'scored_predictions.parquet',
    DATA_SOURCE = gold_lending_club,
    FILE_FORMAT = parquet_format
);

-- portfolio summary by grade
CREATE VIEW dbo.vw_portfolio_summary AS
SELECT
    grade_int,
    COUNT(*) AS total_loans,
    SUM(loan_amnt) AS total_loan_amnt,
    AVG(int_rate) AS avg_int_rate,
    AVG(dti) AS avg_dti,
    AVG(default_probability) AS avg_default_prob,
    SUM(actual_default) AS actual_defaults,
    CAST(SUM(actual_default) AS FLOAT) / COUNT(*) AS default_rate
FROM dbo.scored_predictions
GROUP BY grade_int;
GO

-- default rate by grade and term
CREATE VIEW dbo.vw_default_by_segment AS
SELECT
    grade_int,
    term,
    COUNT(*) AS total_loans,
    SUM(actual_default) AS defaults,
    CAST(SUM(actual_default) AS FLOAT) / COUNT(*) AS default_rate,
    AVG(int_rate) AS avg_int_rate,
    AVG(fico_mid) AS avg_fico
FROM dbo.scored_predictions
GROUP BY grade_int, term;
GO

-- vintage curves
CREATE VIEW dbo.vw_vintage_curves AS
SELECT
    credit_age_months,
    COUNT(*) AS total_loans,
    SUM(actual_default) AS defaults,
    CAST(SUM(actual_default) AS FLOAT) / COUNT(*) AS default_rate,
    AVG(default_probability) AS avg_predicted_prob
FROM dbo.scored_predictions
GROUP BY credit_age_months;
GO

-- state level loan volume
CREATE VIEW dbo.vw_loans_by_state AS
SELECT
    predicted_default,
    COUNT(*) AS total_loans,
    SUM(loan_amnt) AS total_loan_amnt,
    AVG(default_probability) AS avg_default_prob
FROM dbo.scored_predictions
GROUP BY predicted_default;
GO

-- model performance summary
CREATE VIEW dbo.vw_model_performance AS
SELECT
    COUNT(*) AS total_scored,
    SUM(actual_default) AS total_actual_defaults,
    SUM(predicted_default) AS total_predicted_defaults,
    CAST(SUM(actual_default) AS FLOAT) / COUNT(*) AS actual_default_rate,
    CAST(SUM(predicted_default) AS FLOAT) / COUNT(*) AS predicted_default_rate,
    AVG(default_probability) AS avg_default_probability
FROM dbo.scored_predictions;
GO