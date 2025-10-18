from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3
import os
import pandas as pd
import io
import app_predictions_logic 

# 1. INITIALIZE APP FIRST 
app = Flask(__name__)
app.secret_key = 'your_super_secret_key_for_flask_session'

READABLE_NAMES = {
    'loanAmount': 'Loan Amount', 'loanTerm': 'Loan Term', 'monthlyIncome': 'Monthly Income', 
    'age': 'Age Factor', 'dependents': 'Number of Dependents', 'collateral': 'Collateral Provided',
    'gender': 'Gender', 'maritalStatus': 'Marital Status', 'educationLevel': 'Education Level', 
    'occupation': 'Occupation Type', 'regionType': 'Region Type', 'previousLoanHistory': 'Previous Loan History', 
    'repaymentBehavior': 'Repayment Behavior'
}

# --- Database Connection Management ---
# Import function here to avoid circular dependency errors common in Flask apps
from database import get_db_connection 

def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- Authentication Decorator ---
def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash('Please log in or register to access the application modules.', 'info')
            return redirect(url_for('auth')) 
        return view(**kwargs)
    return wrapped_view

# --- Routes ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('prediction_tool'))
    return render_template('index.html') 

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        action = request.form.get('action') 
        db = get_db()
        
        if action == 'register':
            try:
                db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                db.commit()
                flash('Registration successful! Please log in.', 'success')
            except sqlite3.IntegrityError:
                flash('That username is already taken.', 'danger')
        
        elif action == 'login':
            user = db.execute("SELECT id, username, password FROM users WHERE username = ?", (username,)).fetchone()
            
            if user and user['password'] == password: 
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash(f'Welcome back, {user["username"]}!', 'success')
                return redirect(url_for('prediction_tool'))
            else:
                flash('Login failed. Check your username and password.', 'danger')

    return render_template('auth.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You have been successfully logged out.', 'success')
    return redirect(url_for('index'))


@app.route('/prediction_tool', methods=['GET', 'POST'])
@login_required
def prediction_tool():
    from microfinance_model import calculate_prediction
    
    inputs = {
        'loanAmount': 50000.0, 'loanTerm': 24, 'monthlyIncome': 15000.0, 'collateral': 'yes',
        'gender': 'male', 'age': 35, 'dependents': 3, 'maritalStatus': 'married',
        'educationLevel': 'graduate', 'occupation': 'farming', 'regionType': 'rural',
        'previousLoanHistory': 'good', 'repaymentBehavior': 'good'
    }
    risk_pct, risk_level, default_status = 0, "LOW RISK", "Non-Defaulted"
    contributions = {} 

    if request.method == 'POST':
        try:
            inputs.update({
                'loanAmount': float(request.form.get('loanAmount')),
                'loanTerm': int(request.form.get('loanTerm')),
                'monthlyIncome': float(request.form.get('monthlyIncome')),
                'age': int(request.form.get('age')),
                'dependents': int(request.form.get('dependents')),
                **{k: request.form.get(k) for k in request.form if k not in ['loanAmount', 'loanTerm', 'monthlyIncome', 'age', 'dependents', 'action']}
            })
            
            risk_pct, risk_level, default_status, contributions = calculate_prediction(inputs)
            
            if risk_level == 'MODEL OFFLINE':
                 flash(f'Prediction failed: {default_status}', 'danger')

            if request.form.get('action') == 'save' and risk_level != 'MODEL OFFLINE':
                db = get_db()
                db.execute("""
                    INSERT INTO predictions (user_id, risk_percentage, risk_level, default_status, loan_amount, loan_term, monthly_income, age, occupation, prev_history)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session['user_id'], 
                    risk_pct, 
                    risk_level, 
                    default_status,
                    inputs['loanAmount'], 
                    inputs['loanTerm'], 
                    inputs['monthlyIncome'], 
                    inputs['age'],
                    inputs['occupation'], 
                    inputs['previousLoanHistory']
                )) # SYNTAX ERROR FIX: Closing parenthesis is correct.
                db.commit()
                flash(f'Prediction saved! Risk: {risk_pct}% ({risk_level})', 'success')
        except Exception as e:
            flash(f'An error occurred: Please check all fields are valid. Error: {e}', 'danger')

    session['last_inputs'] = inputs
    return render_template('prediction.html', inputs=inputs, risk_pct=risk_pct, risk_level=risk_level, default_status=default_status)

@app.route('/history')
@login_required
def recent_predictions():
    db = get_db()
    predictions = db.execute(
        """
        SELECT timestamp, loan_amount, risk_percentage, risk_level, default_status
        FROM predictions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT 20
        """,
        (session['user_id'],)
    ).fetchall()
    return render_template('history.html', predictions=predictions) 

@app.route('/risk_breakdown')
@login_required
def risk_breakdown():
    from microfinance_model import calculate_prediction
    
    inputs = session.get('last_inputs')
    if not inputs:
        flash("Please perform a prediction first on the Prediction Tool page.", "warning")
        return redirect(url_for('prediction_tool'))

    risk_pct, risk_level, default_status, contributions = calculate_prediction(inputs)
    
    breakdown_data = []
    total_impact_score = sum(contributions.values())
    
    if risk_level == 'MODEL OFFLINE':
         flash(f"The ML Model is currently offline. Error: {default_status}", "danger")
    elif total_impact_score > 0: 
        for key, contribution in contributions.items():
            percent_of_total = (contribution / total_impact_score) * 100
            breakdown_data.append({
                'name': READABLE_NAMES.get(key, key),
                'percent': round(percent_of_total, 1),
                'model_weight': 'Dynamic' 
            })
        breakdown_data.sort(key=lambda x: x['percent'], reverse=True)
    else:
         flash("Feature contribution analysis is temporarily unavailable.", "warning")

    return render_template('risk_breakdown.html', breakdown_data=breakdown_data, risk_pct=risk_pct, risk_level=risk_level, default_status=default_status, total_impact_score=total_impact_score)
                           
@app.route('/dashboard')
@login_required
def analytical_dashboard():
    db = get_db()
    
    # 1. Total and Default Counts (Existing)
    total_predictions = db.execute("SELECT COUNT(id) FROM predictions WHERE user_id = ?", (session['user_id'],)).fetchone()[0]
    defaulted_count = db.execute("SELECT COUNT(id) FROM predictions WHERE user_id = ? AND default_status = 'Defaulted'", (session['user_id'],)).fetchone()[0]
    
    # 2. Risk Level Distribution (NEW for Chart.js)
    risk_data_raw = db.execute(
        """
        SELECT risk_level, COUNT(id) AS count
        FROM predictions
        WHERE user_id = ?
        GROUP BY risk_level
        ORDER BY count DESC
        """,
        (session['user_id'],)
    ).fetchall()

    # Format data for Chart.js: { 'LOW RISK': 50, 'MEDIUM RISK': 30, ... }
    risk_distribution = {row['risk_level']: row['count'] for row in risk_data_raw}
    
    dashboard_data = {
        'total': total_predictions,
        'defaulted_count': defaulted_count,
        'non_defaulted_count': total_predictions - defaulted_count,
        'risk_distribution': risk_distribution
    }
    return render_template('dashboard.html', dashboard_data=dashboard_data)

@app.route('/data_tools', methods=['GET', 'POST']) 
@login_required
def data_tools():
    from database import insert_historical_data_from_df
    from microfinance_model import load_training_data, MODEL_CHOICE, MODEL_STATUS

    # --- 1. Handle POST Request (File Upload) ---
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(url_for('data_tools'))
        
        file = request.files['csv_file']
        
        if file.filename == '':
            flash('No selected file.', 'danger')
            return redirect(url_for('data_tools'))
        
        if file and file.filename.endswith('.csv'):
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                df_new_data = pd.read_csv(stream)
                rows_inserted = insert_historical_data_from_df(df_new_data) 
                
                flash(f'Successfully uploaded and inserted {rows_inserted} new rows into historical_data! Please restart the app for the model to use the new data.', 'success')
                return redirect(url_for('data_tools'))

            except ValueError as ve: 
                 flash(f'Data format error: {ve}', 'danger')
                 return redirect(url_for('data_tools'))
            except Exception as e:
                flash(f'Error processing file: {e}', 'danger')
                return redirect(url_for('data_tools'))
        else:
            flash('Invalid file format. Please upload a CSV.', 'danger')
            return redirect(url_for('data_tools'))
            
    # --- 2. Handle GET Request (Display Page) ---
    try:
        df_train = load_training_data()
        
        data_stats = {
            'model_type': MODEL_CHOICE,
            'training_rows': df_train.shape[0] if not df_train.empty else 0,
            'db_status': MODEL_STATUS if MODEL_STATUS != "ONLINE" else "OK"
        }
    except Exception as e:
        data_stats = {
            'model_type': 'UNAVAILABLE',
            'training_rows': 0,
            'db_status': f'Error: Database/Model Access Failed ({e})'
        }

    return render_template('data_tools.html', data_stats=data_stats)


# --- Run App ---
if __name__ == '__main__':
    from database import init_db
    DB_PATH = os.path.join(os.getcwd(), 'instance', 'loancompass.db')
    
    # 1. Ensure the instance directory exists
    if not os.path.exists('instance'):
        os.makedirs('instance')
        
    # 2. Check for database file and initialize if missing
    if not os.path.exists(DB_PATH):
        print("Database not found. Initializing database and training data...")
        init_db() 
        
    # 3. Restart the model initialization AFTER the DB is guaranteed to exist
    from microfinance_model import initialize_model
    initialize_model()
    
    app.run(debug=True)

set_all_seeds(DETERMINISTIC_SEED)
