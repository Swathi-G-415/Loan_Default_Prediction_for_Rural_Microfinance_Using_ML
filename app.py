from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import io
import pandas as pd
from functools import wraps

app = Flask(__name__)
app.secret_key = 'loancompass_secure_interview_demo_key'

READABLE_NAMES = {
    'loanAmount': 'Loan Amount', 'loanTerm': 'Loan Term', 'monthlyIncome': 'Monthly Income',
    'age': 'Age Factor', 'dependents': 'Number of Dependents', 'collateral': 'Collateral Provided',
    'gender': 'Gender', 'maritalStatus': 'Marital Status', 'educationLevel': 'Education Level',
    'occupation': 'Occupation Type', 'regionType': 'Region Type', 'previousLoanHistory': 'Previous Loan History',
    'repaymentBehavior': 'Repayment Behavior'
}

from database import get_db_connection


def get_db():
    if 'db' not in g:
        g.db = get_db_connection()
        # Guarantee users table exists across instances
        g.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )
        """)
        g.db.commit()
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash('Please log in or register to access the application modules.', 'info')
            return redirect(url_for('auth'))
        return view(**kwargs)
    return wrapped_view


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('prediction_tool'))
    return render_template('index.html')


@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        action = request.form.get('action', '')
        db = get_db()

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('auth.html')

        # 1. Handle Explicit Registration
        if action == 'register':
            try:
                hashed = generate_password_hash(password)
                db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
                db.commit()
                flash('Registration successful! Please log in.', 'success')
            except sqlite3.IntegrityError:
                flash('Username already exists. Please choose another.', 'warning')
            return redirect(url_for('auth'))

        # 2. Handle Login: Lookup user in database
        user = db.execute("SELECT id, username, password FROM users WHERE username = ?", (username,)).fetchone()

        if not user:
            try:
                user = db.execute("SELECT id, username, password FROM user WHERE username = ?", (username,)).fetchone()
            except Exception:
                pass

        if user:
            stored_pw = user['password'] if isinstance(user, dict) or hasattr(user, 'keys') else user[2]
            user_id = user['id'] if isinstance(user, dict) or hasattr(user, 'keys') else user[0]

            # Verify password (hashed or plain-text)
            if check_password_hash(stored_pw, password) or stored_pw == password:
                session.clear()
                session['user_id'] = user_id
                session['username'] = username
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('prediction_tool'))
            else:
                flash('Invalid username or password.', 'danger')
                return render_template('auth.html')

        # 3. Seamless Auto-Registration on first login attempt (Prevents Demo Failures)
        try:
            hashed = generate_password_hash(password)
            cursor = db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
            db.commit()
            session.clear()
            session['user_id'] = cursor.lastrowid
            session['username'] = username
            flash(f'Welcome, {username}!', 'success')
            return redirect(url_for('prediction_tool'))
        except Exception:
            # Fallback if already inserted
            user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            uid = user[0] if user else 1
            session.clear()
            session['user_id'] = uid
            session['username'] = username
            return redirect(url_for('prediction_tool'))

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

    if request.method == 'POST':
        try:
            inputs.update({
                'loanAmount': float(request.form.get('loanAmount')),
                'loanTerm': int(request.form.get('loanTerm')),
                'monthlyIncome': float(request.form.get('monthlyIncome')),
                'age': int(request.form.get('age')),
                'dependents': int(request.form.get('dependents')),
                **{k: request.form.get(k) for k in request.form
                   if k not in ['loanAmount', 'loanTerm', 'monthlyIncome', 'age', 'dependents', 'action']}
            })

            risk_pct, risk_level, default_status, _ = calculate_prediction(inputs)

            if risk_level == 'MODEL OFFLINE':
                flash(f'Prediction failed: {default_status}', 'danger')

            if request.form.get('action') == 'save' and risk_level != 'MODEL OFFLINE':
                db = get_db()
                db.execute("""
                    INSERT INTO predictions (user_id, risk_percentage, risk_level, default_status,
                                             loan_amount, loan_term, monthly_income, age, occupation, prev_history)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (session.get('user_id', 1), risk_pct, risk_level, default_status,
                      inputs['loanAmount'], inputs['loanTerm'], inputs['monthlyIncome'],
                      inputs['age'], inputs['occupation'], inputs['previousLoanHistory']))
                db.commit()
                flash(f'Prediction saved! Risk: {risk_pct}% ({risk_level})', 'success')
        except Exception as e:
            flash(f'An error occurred: Please check all fields are valid. Error: {e}', 'danger')

    session['last_inputs'] = inputs
    return render_template('prediction.html', inputs=inputs, risk_pct=risk_pct,
                           risk_level=risk_level, default_status=default_status)


@app.route('/history')
@login_required
def recent_predictions():
    db = get_db()
    predictions = db.execute(
        """SELECT timestamp, loan_amount, risk_percentage, risk_level, default_status
           FROM predictions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20""",
        (session.get('user_id', 1),)
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
            breakdown_data.append({
                'name': READABLE_NAMES.get(key, key),
                'percent': round(contribution / total_impact_score * 100, 1),
                'model_weight': 'Dynamic'
            })
        breakdown_data.sort(key=lambda x: x['percent'], reverse=True)
    else:
        flash("Feature contribution analysis is temporarily unavailable.", "warning")

    return render_template('risk_breakdown.html', breakdown_data=breakdown_data, risk_pct=risk_pct,
                           risk_level=risk_level, default_status=default_status,
                           total_impact_score=total_impact_score)


@app.route('/dashboard')
@login_required
def analytical_dashboard():
    db = get_db()
    uid = session.get('user_id', 1)

    total_row = db.execute("SELECT COUNT(id) FROM predictions WHERE user_id = ?", (uid,)).fetchone()
    total_predictions = total_row[0] if total_row else 0

    default_row = db.execute(
        "SELECT COUNT(id) FROM predictions WHERE user_id = ? AND default_status = 'Defaulted'", (uid,)
    ).fetchone()
    defaulted_count = default_row[0] if default_row else 0

    risk_data_raw = db.execute(
        """SELECT risk_level, COUNT(id) AS count FROM predictions
           WHERE user_id = ? GROUP BY risk_level ORDER BY count DESC""", (uid,)
    ).fetchall()

    risk_distribution = {}
    for row in risk_data_raw:
        if isinstance(row, dict) or hasattr(row, 'keys'):
            risk_distribution[row['risk_level']] = row['count']
        else:
            risk_distribution[row[0]] = row[1]

    dashboard_data = {
        'total': total_predictions,
        'defaulted_count': defaulted_count,
        'non_defaulted_count': max(0, total_predictions - defaulted_count),
        'risk_distribution': risk_distribution
    }
    return render_template('dashboard.html', dashboard_data=dashboard_data)


@app.route('/data_tools', methods=['GET', 'POST'])
@login_required
def data_tools():
    from database import insert_historical_data_from_df
    import microfinance_model as mm

    if request.method == 'POST':
        file = request.files.get('csv_file')
        if file is None or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('data_tools'))
        if not file.filename.lower().endswith('.csv'):
            flash('Invalid file format. Please upload a CSV.', 'danger')
            return redirect(url_for('data_tools'))

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8"), newline=None)
            df_new = pd.read_csv(stream, sep=None, engine='python')
            rows = insert_historical_data_from_df(df_new)

            mm.MODEL_STATUS = "OFFLINE: retraining"
            if mm.retrain_model():
                flash(f'Inserted {rows} rows and retrained the {mm.MODEL_CHOICE} model. '
                      f'Hold-out accuracy: {mm.MODEL_METRICS["accuracy"]}%', 'success')
            else:
                flash(f'Inserted {rows} rows, but retraining failed: {mm.MODEL_STATUS}', 'danger')
        except ValueError as ve:
            flash(f'Data format error: {ve}', 'danger')
        except Exception as e:
            flash(f'Error processing file: {e}', 'danger')
        return redirect(url_for('data_tools'))

    try:
        mm.initialize_model()
        df_train = mm.load_training_data()
        data_stats = {
            'model_type': mm.MODEL_CHOICE,
            'training_rows': df_train.shape[0],
            'db_status': "OK" if mm.MODEL_STATUS == "ONLINE" else mm.MODEL_STATUS,
            'metrics': mm.MODEL_METRICS,
        }
    except Exception as e:
        data_stats = {'model_type': 'UNAVAILABLE', 'training_rows': 0,
                      'db_status': f'Error: Database/Model Access Failed ({e})', 'metrics': {}}

    return render_template('data_tools.html', data_stats=data_stats)


if __name__ == '__main__':
    from database import init_db
    DB_PATH = os.path.join(os.getcwd(), 'instance', 'loancompass.db')
    os.makedirs('instance', exist_ok=True)
    if not os.path.exists(DB_PATH):
        print("Database not found. Initializing database...")
        init_db()

    from microfinance_model import initialize_model
    initialize_model()

    app.run(debug=True, use_reloader=False)
