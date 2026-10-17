# --- microfinance_model.py ---
# Real ML model for rural microfinance loan default prediction.
# Compares Decision Tree, Random Forest and Gradient Boosting, keeps the best one.
import os
import sys
import joblib
import numpy as np
import pandas as pd
 
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier
 
from database import get_db_connection
 
SEED = 42
MODEL_FILE = 'loan_risk_model.joblib'
 
NUMERIC_FEATURES = ['loanAmount', 'loanTerm', 'monthlyIncome', 'age', 'dependents']
CATEGORICAL_FEATURES = ['collateral', 'gender', 'maritalStatus', 'educationLevel',
                        'occupation', 'regionType', 'previousLoanHistory', 'repaymentBehavior']
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = 'is_default'
 
# Globals (read by app.py)
MODEL_CHOICE = "Not trained yet"
MODEL_STATUS = "OFFLINE: Module Imported. Starting Initialization..."
MODEL_METRICS = {}
model = None            # full sklearn Pipeline (preprocessing + classifier)
reference_df = None     # sample of real borrowers used for the explanation step
global_importance = {}
 
 
def load_training_data():
    """Fetches all historical data from SQLite."""
    conn = get_db_connection()
    try:
        return pd.read_sql_query("SELECT * FROM historical_data", conn)
    finally:
        conn.close()
 
 
def _build_pipeline(clf):
    pre = ColumnTransformer([
        ('cat', OneHotEncoder(handle_unknown='ignore'), CATEGORICAL_FEATURES),
        ('num', 'passthrough', NUMERIC_FEATURES),
    ])
    return Pipeline([('prep', pre), ('clf', clf)])
 
 
def _candidates():
    return {
        'Decision Tree': DecisionTreeClassifier(max_depth=5, min_samples_leaf=3,
                                                class_weight='balanced', random_state=SEED),
        'Random Forest': RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                                class_weight='balanced', random_state=SEED, n_jobs=1),
        'Gradient Boosting Classifier': GradientBoostingClassifier(random_state=SEED),
    }
 
 
def _compute_global_importance(pipe):
    """Sum one-hot importances back to the original feature names."""
    names = pipe.named_steps['prep'].get_feature_names_out()
    imps = pipe.named_steps['clf'].feature_importances_
    out = {f: 0.0 for f in FEATURES}
    for n, v in zip(names, imps):
        raw = n.split('__', 1)[1]
        for f in FEATURES:
            if raw == f or raw.startswith(f + '_'):
                out[f] += float(v)
                break
    return out
 
 
def retrain_model():
    """Train on historical_data, pick the best model by cross-validation, save it."""
    global model, MODEL_CHOICE, MODEL_STATUS, MODEL_METRICS, reference_df, global_importance
 
    df = load_training_data()
    if df.empty or df.shape[0] < 20 or df[TARGET].nunique() < 2:
        MODEL_STATUS = "OFFLINE: Insufficient Training Data (need 20+ rows with both classes)"
        print(f"ERROR: {MODEL_STATUS}", file=sys.stderr)
        return False
 
    try:
        X, y = df[FEATURES], df[TARGET].astype(int)
 
        # 1. Model selection with 5-fold stratified cross-validation
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
        cv_scores = {}
        for name, clf in _candidates().items():
            cv_scores[name] = float(cross_val_score(_build_pipeline(clf), X, y, cv=cv,
                                                    scoring='roc_auc').mean())
        best_name = max(cv_scores, key=cv_scores.get)
 
        # 2. Honest hold-out evaluation (20% never seen in training)
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
        eval_pipe = _build_pipeline(_candidates()[best_name]).fit(X_tr, y_tr)
        pred = eval_pipe.predict(X_te)
        proba = eval_pipe.predict_proba(X_te)[:, 1]
        MODEL_METRICS = {
            'accuracy': round(accuracy_score(y_te, pred) * 100, 1),
            'precision': round(precision_score(y_te, pred, zero_division=0) * 100, 1),
            'recall': round(recall_score(y_te, pred, zero_division=0) * 100, 1),
            'f1': round(f1_score(y_te, pred, zero_division=0) * 100, 1),
            'roc_auc': round(roc_auc_score(y_te, proba), 3),
            'cv_roc_auc': {k: round(v, 3) for k, v in cv_scores.items()},
            'train_rows': int(len(X_tr)), 'test_rows': int(len(X_te)),
        }
 
        # 3. Final model trained on ALL data
        final = _build_pipeline(_candidates()[best_name]).fit(X, y)
 
        # 4. Reference sample of real borrowers, used to explain each prediction
        reference_df = X.sample(n=min(40, len(X)), random_state=SEED).reset_index(drop=True)
        global_importance = _compute_global_importance(final)
 
        model, MODEL_CHOICE, MODEL_STATUS = final, best_name, "ONLINE"
        joblib.dump({'model': model, 'name': MODEL_CHOICE, 'metrics': MODEL_METRICS,
                     'reference': reference_df, 'importance': global_importance}, MODEL_FILE)
        print(f"Trained {best_name}. Hold-out accuracy: {MODEL_METRICS['accuracy']}%")
        return True
 
    except Exception as e:
        MODEL_STATUS = f"OFFLINE: Retraining Error ({e})"
        print(f"FATAL ERROR: {MODEL_STATUS}", file=sys.stderr)
        model = None
        return False
 
 
def initialize_model():
    """Load the saved model if it exists, otherwise train a new one."""
    global model, MODEL_CHOICE, MODEL_STATUS, MODEL_METRICS, reference_df, global_importance
    if MODEL_STATUS == "ONLINE":
        return True
    try:
        if os.path.exists(MODEL_FILE):
            d = joblib.load(MODEL_FILE)
            model, MODEL_CHOICE = d['model'], d['name']
            MODEL_METRICS, reference_df = d['metrics'], d['reference']
            global_importance = d['importance']
            MODEL_STATUS = "ONLINE"
            print("ML model loaded from disk.")
            return True
        return retrain_model()
    except Exception as e:
        MODEL_STATUS = f"OFFLINE: Initialization Failed ({e})"
        print(MODEL_STATUS, file=sys.stderr)
        model = None
        return False
 
 
def _explain(row_df, base_prob):
    """Per-prediction explanation (what-if / permutation style).
    For each feature, replace this borrower's value with values from 40 real
    borrowers and measure how much the default probability changes on average.
    A bigger change means that feature mattered more for THIS borrower."""
    contrib = {}
    for f in FEATURES:
        alt = pd.concat([row_df] * len(reference_df), ignore_index=True)
        alt[f] = reference_df[f].values
        contrib[f] = float(np.abs(base_prob - model.predict_proba(alt)[:, 1]).mean())
    if sum(contrib.values()) == 0:      # fall back to global importance
        contrib = dict(global_importance)
    return contrib
 
 
def calculate_prediction(inputs: dict):
    """Returns (risk_pct, risk_level, default_status, contributions)."""
    if not initialize_model():
        return 0, 'MODEL OFFLINE', MODEL_STATUS, {}
    try:
        row = pd.DataFrame([{f: inputs[f] for f in FEATURES}])
        for c in NUMERIC_FEATURES:
            row[c] = pd.to_numeric(row[c])
 
        prob = float(model.predict_proba(row)[0, 1])
        risk_pct = round(prob * 100, 2)
 
        if risk_pct >= 60:
            risk_level = 'HIGH RISK'
        elif risk_pct >= 40:
            risk_level = 'MEDIUM RISK'
        else:
            risk_level = 'LOW RISK'
        default_status = 'Defaulted' if risk_pct >= 50 else 'Non-Defaulted'
 
        return risk_pct, risk_level, default_status, _explain(row, prob)
    except Exception as e:
        print(f"Prediction failed at runtime: {e}", file=sys.stderr)
        return 0, 'MODEL OFFLINE', f'Prediction Runtime Error ({e})', {}
