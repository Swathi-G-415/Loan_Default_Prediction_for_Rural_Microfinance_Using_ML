# Run once:  python seed_data.py
# Creates the DB and loads your CSV (loan_data.csv) into historical_data.
import os
import pandas as pd
from database import init_db, get_db_connection, insert_historical_data_from_df

os.makedirs('instance', exist_ok=True)
init_db()                                   # creates tables (+ 7 sample rows)

conn = get_db_connection()
conn.execute("DELETE FROM historical_data")  # remove the 7 toy rows, use real CSV only
conn.commit()
conn.close()

df = pd.read_csv('loan_data.csv', sep=None, engine='python')   # works for comma or tab
n = insert_historical_data_from_df(df)
print(f"Loaded {n} rows into historical_data")

if os.path.exists('loan_risk_model.joblib'):
    os.remove('loan_risk_model.joblib')      # force a fresh training
from microfinance_model import retrain_model, MODEL_METRICS
import microfinance_model as m
retrain_model()
print("Model:", m.MODEL_CHOICE)
print("Metrics:", m.MODEL_METRICS)
