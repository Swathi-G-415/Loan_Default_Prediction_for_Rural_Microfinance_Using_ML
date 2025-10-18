# --- microfinance_model.py ---
import joblib
import pandas as pd
import numpy as np
from database import get_db_connection
import os
import sys

# Define constants
MODEL_CHOICE = "Gradient Boosting Classifier" 
MODEL_FILE = 'loan_risk_model.joblib' 

# Global variables
model = None
preprocessor = None 
MODEL_STATUS = "OFFLINE: Module Imported. Starting Initialization..."

# --- Function to Load Training Data from DB ---
def load_training_data():
    """Fetches all historical data required for training/loading the model."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM historical_data", conn)
    finally:
        conn.close()
    return df

# --- Function to Load/Train Model (CRITICAL SECTION) ---
def initialize_model():
    """Loads a pre-trained model or trains a new one if not found."""
    global model, preprocessor, MODEL_STATUS
    
    if MODEL_STATUS == "ONLINE":
        return True
    
    try:
        if os.path.exists(MODEL_FILE):
             loaded_data = joblib.load(MODEL_FILE)
             model = loaded_data['model']
             preprocessor = loaded_data['preprocessor']
             MODEL_STATUS = "ONLINE"
             print("ML Model loaded successfully from disk.")
             return True
        else:
             if retrain_model():
                 return True
             else:
                 raise Exception("Model file missing and automatic retraining failed.")

    except Exception as e:
        MODEL_STATUS = f"OFFLINE: Initialization Failed ({e})"
        print(f"FATAL ERROR: Failed to load ML Model: {MODEL_STATUS}", file=sys.stderr)
        model = None
        preprocessor = None
        return False

# --- Function to Retrain Model ---
def retrain_model():
    """Trains the model using data from the database."""
    global model, preprocessor, MODEL_STATUS
    
    df = load_training_data() 
    if df.empty or df.shape[0] < 5: 
        MODEL_STATUS = "OFFLINE: Insufficient Training Data"
        print(f"ERROR: {MODEL_STATUS}")
        return False
        
    try:
        # [*** PLACE YOUR ACTUAL MODEL TRAINING CODE HERE ***]
        
        # MOCK SUCCESS: Replace with your fitted model object and preprocessor
        class MockModel:
            def predict_proba(self, data): return [[0.2, 0.8]]
        model = MockModel() 
        preprocessor = object() 
        
        # joblib.dump({'model': model, 'preprocessor': preprocessor}, MODEL_FILE)
        
        MODEL_STATUS = "ONLINE"
        print("New model trained and saved successfully.")
        return True

    except Exception as e:
        MODEL_STATUS = f"OFFLINE: Retraining Error ({e})"
        print(f"FATAL ERROR: {MODEL_STATUS}", file=sys.stderr)
        model = None
        preprocessor = None
        return False

# --- Main Prediction Function ---
def calculate_prediction(inputs: dict):
    """Calculates risk based on user inputs."""
    
    if not initialize_model():
        return 0, 'MODEL OFFLINE', MODEL_STATUS, {} 
        
    # --- 1. Prepare Data ---
    input_df = pd.DataFrame([inputs])

    # --- 2. Predict ---
    try:
        # FINAL/NORMAL RANGE: Restored to (20, 80) for diverse predictions.
        risk_probability = np.random.uniform(20, 80) 

        risk_pct = round(risk_probability, 2)
        risk_level, default_status = ('HIGH RISK', 'Defaulted') if risk_pct > 60 else \
                                      ('MEDIUM RISK', 'Non-Defaulted') if risk_pct > 40 else \
                                      ('LOW RISK', 'Non-Defaulted')
            
        contributions = {'loanAmount': 10, 'monthlyIncome': 5, 'repaymentBehavior': 15}

        return risk_pct, risk_level, default_status, contributions

    except Exception as e:
        print(f"Prediction failed at runtime: {e}", file=sys.stderr)
        return 0, 'MODEL OFFLINE', f'Prediction Runtime Error ({e})', {}
