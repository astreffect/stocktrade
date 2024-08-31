from flask import Flask, render_template, request, redirect, url_for, flash, Response, session, jsonify
import mysql.connector
from flask_bcrypt import Bcrypt
from config import Config
import random
import re 
import smtplib
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import csv
import io
import subprocess
import os
import sys
from api_helper import ShoonyaApiPy
from flask_socketio import SocketIO, emit
import pyotp
#import threading
#import backend
import yfinance as yf




app = Flask(__name__)
app.config.from_object(Config)
bcrypt = Bcrypt(app)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow connections from any origin
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='ny',
        password='abcdZ@123',
        database='trading'
    )
def get_token_by_symbol3(symbol):
    # Load CSV data into a DataFrame
    csv_file_path = './sym.csv'

    if not os.path.isfile(csv_file_path):
        print(f"File not found: {csv_file_path}")
    df = pd.read_csv(csv_file_path)
    
    # Filter DataFrame by the given symbol
    row = df[df['TradingSymbol'] == symbol]
    
    # Check if symbol exists in DataFrame
    if not row.empty:
        return row['Token'].values[0]
    else:
        return None
def get_next_thursday(start_date=None):
    """
    Returns the date of the next Thursday from the start_date.
    If start_date is None, uses today's date.
    """
    if start_date is None:
        start_date = datetime.date.today()

    # Calculate days until next Thursday (3 represents Thursday in datetime module)
    days_until_thursday = (3 - start_date.weekday() + 7) % 7
    next_thursday = start_date + datetime.timedelta(days=days_until_thursday)

    return next_thursday

def generate_symbol(LTP, signal_type):
    # Validate the signal_type
    if signal_type not in ['C', 'P']:
        raise ValueError("Signal type must be 'C' (Call) or 'P' (Put)")

    # Get the next Thursday's date
    next_thursday = get_next_thursday()
    
 # Extract day, month, and year
    new_day = next_thursday.strftime('%d')  # Ensures two-digit day
    new_month = next_thursday.strftime('%b').upper()  # Three-letter month abbreviation
    year_last_two_digits = next_thursday.strftime('%y')  # Last two digits of the year

    # Construct the initial symbol
    type_and_cost = f'{signal_type}{LTP}'
    new_symbol = f'NIFTY{new_day}{new_month}{year_last_two_digits}{type_and_cost}'
    #print(new_symbol)
    # Try to get the token for the symbol
    token = get_token_by_symbol3(new_symbol)

    # If token is not found, try +/- 1 day
    if not token:
        for offset in [-1, 1]:
            alternative_day = next_thursday + datetime.timedelta(days=offset)
            #print(alternative_day)
            alternative_day_str = alternative_day.strftime('%d%b').upper()
            #print(alternative_day_str)
            new_symbol = f'NIFTY{alternative_day_str}{year_last_two_digits}{type_and_cost}'
            #print(new_symbol)
            token = get_token_by_symbol3(new_symbol)
            if token:
                break

    return new_symbol


@app.route('/signal', methods=['POST'])
def receive_signal():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    signal_type = data.get("signal")
    adjusted_ltp = data.get("adjusted_ltp")

    if not signal_type or adjusted_ltp is None:
        return jsonify({"error": "Missing required fields"}), 400

    # Handle each signal type
    if signal_type == "Entry short":
        # Process Entry short signal
        sym_sh=generate_symbol(adjusted_ltp,'P')
        place_orders_for_users(sym_sh,'PE')
        print(f"Processed Entry short with Adjusted LTP: {adjusted_ltp}")
        # Add additional logic here

    elif signal_type == "Entry long":
        # Process Entry long signal
        sym_lo=generate_symbol(adjusted_ltp,'C')
        place_orders_for_users(sym_sh,'CE')

        print(f"Processed Entry long with Adjusted LTP: {adjusted_ltp}")
        # Add additional logic here

    elif signal_type == "Exit short":
        # Process Exit short signal
        sell_order('PE')

        print(f"Processed Exit short with Adjusted LTP: {adjusted_ltp}")
        # Add additional logic here

    elif signal_type == "Exit long":
        # Process Exit long signal
        sell_order('CE')
        print(f"Processed Exit long with Adjusted LTP: {adjusted_ltp}")
        # Add additional logic here

    else:
        return jsonify({"error": "Invalid signal type"}), 400

    return jsonify({"message": f"Signal '{signal_type}' processed successfully"}), 200



def sell_order(order_type):

    if order_type not in ['CE', 'PE']:
        raise ValueError("Order type must be 'CE' (Call Option) or 'PE' (Put Option)")

    conn = get_db_connection()
    cur = conn.cursor()

    # Retrieve open orders of the specified type
    cur.execute("""
        SELECT id, token, Quantity, userid 
        FROM ord 
        WHERE status = 'open' AND type = %s
    """, (order_type,))
    open_orders = cur.fetchall()
    cur.close()
    conn.close()
    
    print(open_orders)

    for order in open_orders:
        id, token, quantity, userid = order

        # Place sell order
        place_order_simu(quantity, token, 'S', user_id)
        print(f"Order {order_id} for token : {token} for user: {userid} sold.")

def place_orders_for_users(token, option_type):

    if option_type not in ['CE', 'PE']:
        raise ValueError("Option type must be 'CE' (Call Option) or 'PE' (Put Option)")

    conn = get_db_connection()
    cur = conn.cursor()

    # Retrieve users with start=1 and their corresponding quantity for the option type
    cur.execute(f"""
        SELECT id, {option_type} 
        FROM user 
        WHERE start = 1
    """)
    users = cur.fetchall()
    cur.close()
    conn.close()
    
    print(users)

    for id, quantity in users:
        if quantity > 0:
            # Place order for each user with a positive quantity
            q=quantity*25
            place_order_simu(q, token, 'B', id)
            print(f"Order placed for user {id} with quantity {q} & token {token}.")




scheduler = BackgroundScheduler()

def get_token_by_symbol(symbol):
    csv_file_path = './sym.csv'
    if not os.path.isfile(csv_file_path):
        print(f"File not found: {csv_file_path}")
        return None
    df = pd.read_csv(csv_file_path)
    row = df[df['TradingSymbol'] == symbol]
    if not row.empty:
        return row['Token'].values[0]
    else:
        return None
def check_and_sell_orders():
    conn = get_db_connection()
    cur = conn.cursor()    
    cur.execute("SELECT id, token, entryPrice, Quantity, max_profit, userid FROM ord WHERE status = 'open'")
    open_orders = cur.fetchall()
    cur.close()
    conn.close()
    print(open_orders)

    api = ShoonyaApiPy()
    user = "FA122220"
    pwd = "Monish@11"
    factor2 = "239952"
    vc = "FA122220_U"
    app_key = "865083c85467852a527e1f0b3fd22896"
    imei = "abc1234"
    TOKEN = 'EI5AJJ47S2V2HP2URRK65427GBL4Z62N'
    otp = pyotp.TOTP(TOKEN).now()

    api.login(userid=user, password=pwd, twoFA=otp, vendor_code=vc, api_secret=app_key, imei=imei)

    for order in open_orders:
        order_id, token, entry_price, quantity, max_profit, user_id = order

        # Fetch current price
        r1 = api.get_quotes('NFO', token)
        current_price = float(r1['lp'])
        cp=current_price*quantity

        # Calculate potential maximum profit
        potential_max_profit = (cp - entry_price*quantity)
        if max_profit is None:
            max_profit = 0.0
        
        # Update max_profit in the database if the new max profit is higher
        if potential_max_profit > max_profit:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE ord 
                SET max_profit = %s 
                WHERE id = %s
            """, (potential_max_profit, order_id))
            conn.commit()
            cur.close()
            conn.close()
        
        # Define thresholds
        loss_threshold = 5000
        profit_threshold = 500

        # Calculate current profit/loss
        current_profit_loss = (current_price*quantity - entry_price*quantity)
        print(current_profit_loss)
        print(max_profit)
        print(-loss_threshold)
        if(current_profit_loss < -loss_threshold):
            print("true")
        else:
            print("false")

        # Check if the conditions to sell are met
        if current_profit_loss < -loss_threshold or (potential_max_profit - current_profit_loss) > profit_threshold:
            # Place sell order
            place_order_simu(quantity, token, 'S', user_id)
            print(f"Order {order_id} sold due to profit/loss conditions.")


def trigger_rollover():
    if datetime.datetime.now().strftime('%H:%M') == '15:22' and datetime.datetime.now().weekday() == 3:  # 3 is Thursday
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, token, Quantity, userid FROM ord WHERE status = 'open'")
        open_orders = cur.fetchall()
        cur.close()

        api = ShoonyaApiPy()
        user = "FA122220"
        pwd = "Monish@11"
        factor2 = "239952"
        vc = "FA122220_U"
        app_key = "865083c85467852a527e1f0b3fd22896"
        imei = "abc1234"
        TOKEN = 'EI5AJJ47S2V2HP2URRK65427GBL4Z62N'
        otp = pyotp.TOTP(TOKEN).now()

        api.login(userid=user, password=pwd, twoFA=otp, vendor_code=vc, api_secret=app_key, imei=imei)

        for order in open_orders:
            order_id, token, quantity, user_id = order

            # Extract symbol details
            symbol_parts = re.search(r'NIFTY(\d{2})([A-Z]{3})(C|P)\d+$', token)
            if symbol_parts:
                day = int(symbol_parts.group(1))
                month = symbol_parts.group(2)
                type_and_cost = symbol_parts.group(3) + symbol_parts.group(4)

                # Find next Thursday
                next_thursday = datetime.date.today()
                while next_thursday.weekday() != 3:
                    next_thursday += datetime.timedelta(days=1)

                new_day = next_thursday.day
                new_month = next_thursday.strftime('%b').upper()

                new_symbol = f'NIFTY{new_day:02d}{new_month}{type_and_cost}'
                token = get_token_by_symbol(new_symbol)

                if not token:
                    # Try +/- 1 day if exact date not found
                    for offset in [-1, 1]:
                        alternative_day = next_thursday + datetime.timedelta(days=offset)
                        new_symbol = f'NIFTY{alternative_day.day:02d}{alternative_day.strftime("%b").upper()}{type_and_cost}'
                        token = get_token_by_symbol(new_symbol)
                        if token:
                            break

                if token:
                    # Place sell order for current position
                    place_order_simu(quantity, token, 'S', user_id)
                    
                    # Place buy order for new position
                    place_order_simu(quantity, new_symbol, 'B', user_id)
                    
                    print(f"Order {order_id} rolled over to {new_symbol}.")

scheduler.add_job(
    check_and_sell_orders,
    trigger=CronTrigger(day_of_week='mon,wed,thu,fri', hour='9-15', minute='0-59', second='*/5')
)
scheduler.add_job(
    trigger_rollover,
    trigger=CronTrigger(day_of_week='mon-fri', minute='*/5')
)

# Start the scheduler
scheduler.start()
def get_india_vix():
    vix_symbol = "^INDIAVIX"  # Make sure this is the correct symbol
    vix_data = yf.download(vix_symbol, period="1d", interval="1m")  # Adjust period and interval as needed
    
    if vix_data.empty:
        return None
    
    return vix_data['Close'].iloc[-1]

def get_token_by_symbol2(symbol):
    # Load CSV data into a DataFrame
    csv_file_path = './sym.csv'

    if not os.path.isfile(csv_file_path):
        print(f"File not found: {csv_file_path}")
    df = pd.read_csv(csv_file_path)
    
    # Filter DataFrame by the given symbol
    row = df[df['TradingSymbol'] == symbol]
    
    # Check if symbol exists in DataFrame
    if not row.empty:
        return row['Token'].values[0]
    else:
        return None
def place_order_simu(quantity, symbol, type, user_id):
        # Get the current date and time
    now = datetime.datetime.now()
    
    # Check if the current day is Monday (0), Wednesday (2), Thursday (3), or Friday (4)
    if now.weekday() not in [0, 2, 3, 4]:
        return {"error": "Orders can only be placed on Monday, Wednesday, Thursday, and Friday"}
    
    # Check if the current time is between 9:15 AM and 3:25 PM
    current_time = now.time()
    start_time = datetime.time(9, 15)
    end_time = datetime.time(15, 25)
    
    if not (start_time <= current_time <= end_time):
        return {"error": "Orders can only be placed between 9:15 AM and 3:25 PM"}

    current_vix = get_india_vix()
    print(current_vix)
    if current_vix is None:
        return {"error": "Unable to fetch India VIX data"}
    if not (13 <= current_vix <= 19):
        return {"error": "Orders can only be placed when India VIX is between 13 and 19"}
    
    # Get user credentials
    print(user_id)
    credentials = get_user_credentials(user_id)
    print(credentials)
    if not credentials:
        return {"error": "Invalid user ID or credentials not found"}
    
    if type == 'B':
        if credentials['start'] != 1:
            return {"error": "User is not allowed to place buy orders"}
        if has_open_order(user_id):
            return {"error": "User already has an open order"}
    elif type == 'S':
        if not has_open_order(user_id):
            return {"error": "User does not have any open orders to sell"}
    
    # Initialize the API
    api = ShoonyaApiPy()
    
    user = credentials['user']
    pwd = credentials['pwd']
    factor2 = credentials['factor2']
    vc = credentials['vc']
    app_key = credentials['app_key']
    imei = credentials['imei']
    
    otp = pyotp.TOTP(factor2).now()

    tok = get_token_by_symbol2(symbol).astype(str)
    
    # Login
    api.login(userid=user, password=pwd, twoFA=otp, vendor_code=vc, api_secret=app_key, imei=imei)
    r1 = api.get_quotes('NFO', tok)
    current_price = float(r1['lp'])
    avp=current_price

      # Convert quantity to integer
      # Convert average price to float
    
    total = quantity * avp
    
    if type == 'B':
        expiry = symbol.split('NIFTY')[1][:7]  # Extract expiry from the symbol
        insert_order(user_id, expiry, symbol, avp, quantity, type, symbol)
    elif type == 'S':
        update_order(user_id, avp)
    
    return {
        'quantity': quantity,
        'average_price': avp,
        'total_value': total
    }
    

def place_order(quantity, symbol, type, user_id):
    # Get the current date and time
    now = datetime.datetime.now()
    
    # Check if the current day is Monday (0), Wednesday (2), Thursday (3), or Friday (4)
    if now.weekday() not in [0, 2, 3, 4]:
        return {"error": "Orders can only be placed on Monday, Wednesday, Thursday, and Friday"}
    
    # Check if the current time is between 9:15 AM and 3:25 PM
    current_time = now.time()
    start_time = datetime.time(9, 15)
    end_time = datetime.time(15, 25)
    
    if not (start_time <= current_time <= end_time):
        return {"error": "Orders can only be placed between 9:15 AM and 3:25 PM"}

    current_vix = get_india_vix()
    if current_vix is None:
        return {"error": "Unable to fetch India VIX data"}
    if not (13 <= current_vix <= 19):
        return {"error": "Orders can only be placed when India VIX is between 13 and 19"}
    
    # Get user credentials
    print(user_id)
    credentials = get_user_credentials(user_id)
    print(credentials)
    if not credentials:
        return {"error": "Invalid user ID or credentials not found"}
    
    if type == 'B':
        if credentials['start'] != 1:
            return {"error": "User is not allowed to place buy orders"}
        if has_open_order(user_id):
            return {"error": "User already has an open order"}
    elif type == 'S':
        if not has_open_order(user_id):
            return {"error": "User does not have any open orders to sell"}
    
    # Initialize the API
    api = ShoonyaApiPy()
    
    user = credentials['user']
    pwd = credentials['pwd']
    factor2 = credentials['factor2']
    vc = credentials['vc']
    app_key = credentials['app_key']
    imei = credentials['imei']
    
    otp = pyotp.TOTP(factor2).now()
    
    # Login
    api.login(userid=user, password=pwd, twoFA=otp, vendor_code=vc, api_secret=app_key, imei=imei)
    
    # Place Order
    ret = api.place_order(
        buy_or_sell=type,
        product_type='M',
        exchange='NFO',
        tradingsymbol=symbol,
        quantity=quantity,
        discloseqty=0,
        price_type='MKT',
        price=0.00,
        trigger_price=0.00,
        retention='DAY',
        remarks='my_order_001'
    )
    
    orderno = ret['norenordno']
    
    # Retrieve Order History
    ret = api.single_order_history(orderno)
    fr = ret[0]
    quantity = int(fr['qty'])  # Convert quantity to integer
    avp = float(fr['avgprc'])  # Convert average price to float
    
    total = quantity * avp
    
    if type == 'B':
        expiry = symbol.split('NIFTY')[1][:7]  # Extract expiry from the symbol
        insert_order(user_id, expiry, symbol, avp, quantity, type, symbol)
    elif type == 'S':
        update_order(user_id, avp)
    
    return {
        'order_number': orderno,
        'quantity': quantity,
        'average_price': avp,
        'total_value': total
    }


def get_user_credentials(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT uid, pwd, totp, vc, app_key, imei, start 
        FROM user 
        WHERE id = %s
    """, (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if result:
        return {
            'user': result[0],
            'pwd': result[1],
            'factor2': result[2],
            'vc': result[3],
            'app_key': result[4],
            'imei': result[5],
            'start': result[6]
        }
    else:
        return None

def has_open_order(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM ord 
        WHERE userid = %s AND status = 'open'
    """, (user_id,))
    result = cur.fetchone()[0]
    cur.close()
    conn.close()
    return result > 0

def insert_order(user_id, expiry, token, entry_price, quantity, type, symbol):
    now = datetime.datetime.now()
    entry_date = now.strftime("%Y-%m-%d")
    entry_time = now.strftime("%H:%M:%S")
    match = re.search(r'([CP])(\d+)$', symbol)
    order_type = 'CE' if match and match.group(1) == 'C' else 'PE'
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ord (Expiry, token, status, strike, type, EntryDate, EntryTime, entryPrice, Quantity, userid)
        VALUES (%s, %s, 'open', 2, %s, %s, %s, %s, %s, %s)
    """, (expiry, token, order_type, entry_date, entry_time, entry_price, quantity, user_id))
    conn.commit()
    cur.close()
    conn.close()

def update_order(user_id, exit_price):
    now = datetime.datetime.now()
    exit_date = now.strftime("%Y-%m-%d")
    exit_time = now.strftime("%H:%M:%S")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, entryPrice FROM ord
        WHERE userid = %s AND status = 'open'
        ORDER BY id LIMIT 1
    """, (user_id,))
    order = cur.fetchone()
    if order:
        order_id = order[0]
        entry_price = order[1]
        pnl = exit_price - entry_price
        cur.execute("""
            UPDATE ord
            SET exitPrice = %s, ExitDate = %s, ExitTime = %s, pnl = %s, status = 'closed'
            WHERE id = %s
        """, (exit_price, exit_date, exit_time, pnl, order_id))
        conn.commit()
    cur.close()
    conn.close()


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        uid = request.form['uid']
        pwd = request.form['pwd']
        totp = request.form['totp']
        vc = request.form['vc']
        app_key = request.form['app_key']
        imei = request.form['imei']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        conn = get_db_connection()
        print(password)

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user (
                uid, pwd, totp, vc, app_key, imei, email, password
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (uid, pwd, totp, vc, app_key, imei, email, password))
        conn.commit()
        cur.close()
        conn.close()
        flash('Signup successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')
@app.route('/logout')
def logout():
    # Clear the user session
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        password2 = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        print(password2)

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)  # Use dictionary mode to access columns by name
        cur.execute("SELECT * FROM user WHERE email=%s", [email])
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            stored_hash = user['password']  # Access column by name
            print(stored_hash)
            
            # Check if the provided password matches the stored hash
            if bcrypt.check_password_hash(stored_hash, password):
                print("True")
                session['user_id'] = user['id']  # Store user ID in session (adjust if needed)
                flash('Login Successful!', 'success')
                return redirect(url_for('dashboard', user_id=user['id']))
            else:
                flash('Login Unsuccessful. Please check your email and password', 'danger')
        else:
            flash('Login Unsuccessful. Email not found', 'danger')
    
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    user_id = session.get('user_id')
    if user_id is None:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT start, CE, PE FROM user WHERE id = %s
    """, (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    print(user_data)
    credentials = get_user_credentials(user_id)
    print(credentials)
    print(user_id)
    print(place_order_simu(25,'NIFTY08AUG24P23500','S',user_id))


    
    if user_data:
        start_status = user_data[0] if user_data[0] is not None else 0
        ce_lot = user_data[1] if user_data[1] is not None else ""
        pe_lot = user_data[2] if user_data[2] is not None else ""
    else:
        start_status = 0
        ce_lot = ""
        pe_lot = ""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Fetch user's open orders
    cur.execute("""
        SELECT token, entryPrice, Quantity, type FROM ord
        WHERE status = 'open' AND userid = %s
    """, (user_id,))
    open_orders = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Initialize variables
    ce_entry, pe_entry = None, None
    current_ce, current_pe = None, None
    ce_pnl, pe_pnl = None, None
    
    # Define the API
    api = ShoonyaApiPy()
    user = "FA122220"
    pwd = "Monish@11"
    factor2 = "239952"
    vc = "FA122220_U"
    app_key = "865083c85467852a527e1f0b3fd22896"
    imei = "abc1234"
    TOKEN = 'EI5AJJ47S2V2HP2URRK65427GBL4Z62N'
    otp = pyotp.TOTP(TOKEN).now()

    api.login(userid=user, password=pwd, twoFA=otp, vendor_code=vc, api_secret=app_key, imei=imei)
    
    for order in open_orders:
        token, entry_price, quantity, order_type = order
        
        # Fetch current price
        r1 = api.get_quotes('NFO', token)
        current_price = float(r1['lp'])
        
        # Calculate P&L
        current_pnl = (current_price*quantity - entry_price*quantity) 
        
        if order_type == 'CE':
            ce_entry = entry_price
            current_ce = round(current_price , 2)
            ce_pnl = round(current_pnl , 2)
        elif order_type == 'PE':
            pe_entry = entry_price
            current_pe = round(current_price, 2)
            pe_pnl = round(current_pnl , 2)
    
    return render_template('user.html', user_id=user_id, start_status=start_status, ce_lot=ce_lot, pe_lot=pe_lot, ce_entry=ce_entry,pe_entry=pe_entry,current_ce=current_ce,current_pe=current_pe,ce_pnl=ce_pnl,pe_pnl=pe_pnl)

@app.route('/order_page', methods=['GET', 'POST'])
def order_page():
    user_id = session.get('user_id')
    if user_id is None:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        ce_lot = request.form.get('ce_lot')
        pe_lot = request.form.get('pe_lot')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE user
            SET CE = %s, PE = %s, start = 1
            WHERE id = %s
        """, (ce_lot, pe_lot, user_id))
        conn.commit()
        cur.close()
        conn.close()

       
        
        flash('Started successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('order.html', user_id=user_id)


@app.route('/confirm_order', methods=['GET', 'POST'])
def confirm_order():
    user_id = session.get('user_id')
    print(user_id)
    if user_id is None:
        return redirect(url_for('login'))
    print("Came here")
    action="Stop"

    if action =='Stop':
        print(action) # Check if 'action' parameter is provided
        
        if action == 'Stop':
            # Update user settings: Set start to 0 and CE & PE to 0
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE user
                SET start = 0, CE = 0, PE = 0
                WHERE id = %s
            """, (user_id,))
            conn.commit()

            # Check for open orders for the user
            cur.execute("""
                SELECT id FROM ord
                WHERE userid = %s AND status = 'OPEN'
            """, (user_id,))
            open_orders = cur.fetchall()

            # Close each open order
            for order in open_orders:
                order_id = order[0]
                # Here, replace 'sell()' with the actual function that handles selling
                # sell(order_id)
                print(f"Sold Order ID: {order_id}")

            cur.close()
            conn.close()

            flash('Stopped and all open orders processed!', 'success')
            return redirect(url_for('dashboard'))

        else:
            # Handle other actions if necessary, or just inform the user
            flash('Action not recognized. Please try again.', 'danger')
            return redirect(url_for('dashboard'))

    # Handle the case where request method is not POST
    return render_template('user.html', user_id=user_id)


@app.route('/past_orders')
def past_orders():
    user_id = session.get('user_id')
    if user_id is None:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, Expiry, token, status, strike, type, EntryDate, EntryTime, ExitDate, ExitTime, entryPrice, exitPrice, max_profit, pnl, Quantity, userid
        FROM ord
        WHERE userid = %s
    """, (user_id,))
    print(user_id)
    orders = cur.fetchall()
    print("Fetched Orders:")
    for order in orders:
        print(order)
    cur.close()
    conn.close()

    return render_template('past_trades.html', orders=orders, user_id=user_id)

@app.route('/download')
def download():
    user_id = session.get('user_id')
    if user_id is None:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, Expiry, token, status, type, EntryDate, EntryTime, ExitDate, ExitTime, entryPrice, exitPrice, pnl, Quantity, userid
        FROM ord
        WHERE userid = %s
    """, (user_id,))
    orders = cur.fetchall()
    cur.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    header = ['ID', 'Expiry', 'Token', 'Status', 'Type', 'EntryDate', 'EntryTime', 'ExitDate', 'ExitTime', 'EntryPrice', 'ExitPrice', 'PNL', 'Quantity', 'UserID']
    writer.writerow(header)
    
    for order in orders:
        writer.writerow(order)
    
    output.seek(0)
    return Response(output, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=orders.csv"})

if __name__ == '__main__':
    # Start the backend script in a background thread
    # backend_thread = threading.Thread(target=backend.start_backend)
    # backend_thread.daemon = True
    # backend_thread.start()
    app.run(host='0.0.0.0', port=5000 , debug=True)
