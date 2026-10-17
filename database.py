# --- database.py ---
import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.getcwd(), 'instance', 'loancompass.db')

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def insert_historical_data_from_df(df: pd.DataFrame):
    REQUIRED_COLUMNS = [
        'loanAmount', 'loanTerm', 'monthlyIncome', 'age', 'dependents', 'collateral',
        'gender', 'maritalStatus', 'educationLevel', 'occupation', 'regionType',
        'previousLoanHistory', 'repaymentBehavior', 'is_default'
    ]
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing_cols)}")

    df_to_insert = df[REQUIRED_COLUMNS].dropna()   # drop rows with missing values
    conn = get_db_connection()
    try:
        df_to_insert.to_sql('historical_data', conn, if_exists='append', index=False)
        return len(df_to_insert)
    except Exception as e:
        raise Exception(f"SQLite insertion error: {e}")
    finally:
        conn.close()


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            risk_percentage REAL,
            risk_level TEXT,
            default_status TEXT,
            loan_amount REAL,
            loan_term INTEGER,
            monthly_income REAL,
            age INTEGER,
            occupation TEXT,
            prev_history TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loanAmount REAL, loanTerm INTEGER, monthlyIncome REAL,
            age INTEGER, dependents INTEGER, collateral TEXT,
            gender TEXT, maritalStatus TEXT, educationLevel TEXT,
            occupation TEXT, regionType TEXT, previousLoanHistory TEXT,
            repaymentBehavior TEXT,
            is_default INTEGER NOT NULL
        );
    """)

    # Only seed the 7 toy rows if the table is empty
    if cursor.execute("SELECT COUNT(*) FROM historical_data").fetchone()[0] == 0:
        sample_data = [
            (50000.0, 36, 35000.0, 45, 2, 'yes', 'female', 'married', 'graduate', 'trader', 'urban', 'good', 'good', 0),
            (10000.0, 12, 5000.0, 25, 1, 'no', 'male', 'single', 'primary', 'labor', 'rural', 'poor', 'poor', 1),
            (25000.0, 24, 15000.0, 30, 3, 'yes', 'male', 'married', 'secondary', 'farming', 'rural', 'none', 'average', 0),
            (80000.0, 48, 60000.0, 55, 0, 'yes', 'female', 'married', 'graduate', 'business', 'urban', 'good', 'excellent', 0),
            (15000.0, 18, 8000.0, 38, 4, 'no', 'male', 'married', 'primary', 'labor', 'rural', 'poor', 'poor', 1),
            (30000.0, 36, 20000.0, 40, 1, 'no', 'male', 'married', 'secondary', 'farming', 'rural', 'average', 'average', 0),
            (5000.0, 6, 4000.0, 22, 0, 'no', 'female', 'single', 'primary', 'labor', 'rural', 'defaulted', 'poor', 1),
        ]
        cursor.executemany("""
            INSERT INTO historical_data (
                loanAmount, loanTerm, monthlyIncome, age, dependents, collateral,
                gender, maritalStatus, educationLevel, occupation, regionType,
                previousLoanHistory, repaymentBehavior, is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_data)

    conn.commit()
    conn.close()
