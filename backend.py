import pandas as pd
import sqlite3
from sqlalchemy import create_engine
from datetime import datetime, timedelta, date
from dhanhq import marketfeed
import asyncio
import requests
import numpy as np

def get_last_thursday(year, month):
    last_day = datetime(year, month, 1) + timedelta(days=32)
    last_day = last_day.replace(day=1) - timedelta(days=1)
    while last_day.weekday() != 3:
        last_day -= timedelta(days=1)
    return last_day

def create_token(symbol, current_date, contract_type):
    current_date_str = current_date.strftime("%Y-%m-%d")
    year = current_date.year
    month = current_date.month
    last_thursday = get_last_thursday(year, month)
    last_thursday_str = last_thursday.strftime("%Y-%m-%d")
    if current_date_str > last_thursday_str:
        next_month = current_date + timedelta(days=32)
        year = next_month.year
        month = next_month.month
    month_abbr = datetime(year, month, 1).strftime("%b").capitalize()
    year_str = datetime(year, month, 1).strftime("%Y")
    return f"{symbol}-{month_abbr}{year_str}-{contract_type}"

def get_security_id(scrip_master, token):
    row = scrip_master[scrip_master['SEM_TRADING_SYMBOL'] == token]
    if not row.empty:
        return row.iloc[0]['SEM_SMST_SECURITY_ID']
    return None

def round_to_nearest_50(x):
    return np.round(float(x) / 50) * 50

def adjust_ltp(ltp, signal_type):
    rounded_ltp = round_to_nearest_50(ltp)
    if signal_type == 'short':
        return rounded_ltp - 100
    elif signal_type == 'long':
        return rounded_ltp + 100
    return rounded_ltp

def add_auto_increment_id(df):
    df = df.copy()  # Make a copy of the DataFrame to avoid modifying the original
    df.reset_index(drop=True, inplace=True)  # Reset index to ensure proper incrementing
    df.insert(0, 'id', range(1, len(df) + 1))  # Add 'id' column with incrementing integers
    return df

def resample_and_generate_signals(df):
    df['LTT'] = pd.to_datetime(df['LTT'], format="%H:%M:%S")
    df.set_index('LTT', inplace=True)

    # Ensure 'avg_price' is numeric
    df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

    # Handle missing values if any
    df = df.dropna(subset=['avg_price', 'close', 'volume'])
    
    df_resampled_1_min = df.resample('1min').agg({
        'type': 'first',
        'exchange_segment': 'first',
        'security_id': 'first',
        'LTP': 'last',
        'LTQ': 'sum',
        'avg_price': 'mean',
        'volume': 'sum',
        'total_sell_quantity': 'sum',
        'total_buy_quantity': 'sum',
        'open': 'first',
        'close': 'last',
        'high': 'max',
        'low': 'min'
    })

    df_resampled_5_min = df.resample('5min').agg({
        'type': 'first',
        'exchange_segment': 'first',
        'security_id': 'first',
        'LTP': 'last',
        'LTQ': 'sum',
        'avg_price': 'mean',
        'volume': 'sum',
        'total_sell_quantity': 'sum',
        'total_buy_quantity': 'sum',
        'open': 'first',
        'close': 'last',
        'high': 'max',
        'low': 'min'
    })

    df_resampled_5_min['Entry short'] = False
    df_resampled_5_min['Entry long'] = False
    df_resampled_5_min['Exit short'] = False
    df_resampled_5_min['Exit long'] = False

    df_resampled_1_min['20_SMA'] = df_resampled_1_min['close'].rolling(window=20).mean()
    df_resampled_1_min['200_SMA'] = df_resampled_1_min['close'].rolling(window=200).mean()
    df_resampled_1_min['VWAP'] = (df_resampled_1_min['close'] * df_resampled_1_min['volume']).cumsum() / df_resampled_1_min['volume'].cumsum()


    
    # Fill other missing values with mean or forward fill as appropriate
    df_resampled_5_min['LTP'].fillna(method='ffill', inplace=True)
    df_resampled_5_min['avg_price'].fillna(df_resampled_5_min['avg_price'].mean(), inplace=True)
    df_resampled_5_min['volume'].fillna(df_resampled_5_min['volume'].mean(), inplace=True)
    df_resampled_5_min['total_sell_quantity'].fillna(df_resampled_5_min['total_sell_quantity'].mean(), inplace=True)
    df_resampled_5_min['total_buy_quantity'].fillna(df_resampled_5_min['total_buy_quantity'].mean(), inplace=True)

    # Calculate the SMAs
    df_resampled_5_min['20_SMA'] = df_resampled_5_min['close'].rolling(window=20).mean()
    df_resampled_5_min['200_SMA'] = df_resampled_5_min['close'].rolling(window=30).mean()

    # Handle NaN values in SMA with mean
    df_resampled_5_min['20_SMA'].fillna(df_resampled_5_min['20_SMA'].mean(), inplace=True)
    df_resampled_5_min['200_SMA'].fillna(df_resampled_5_min['200_SMA'].mean(), inplace=True)

    df_resampled_5_min['VWAP'] = (df_resampled_5_min['close'] * df_resampled_5_min['volume']).cumsum() / df_resampled_5_min['volume'].cumsum()

    for i in range(1, len(df_resampled_5_min)):
        current_data = df_resampled_5_min.iloc[i]
        previous_data = df_resampled_5_min.iloc[i - 1]

        sma_cross_previous_flag_sma = None
        sma_cross_previous_flag_vwap = None
        sma_cross_current_flag_sma = None
        sma_cross_current_flag_vwap = None

        time = current_data.name.time()
        day_of_week = current_data.name.weekday()

        if time > pd.to_datetime('09:14').time() and time < pd.to_datetime('15:30').time():
            if previous_data['20_SMA'] > previous_data['200_SMA']:
                sma_cross_previous_flag_sma = 0
            elif previous_data['20_SMA'] < previous_data['200_SMA']:
                sma_cross_previous_flag_sma = 1

            if previous_data['close'] > previous_data['VWAP']:
                sma_cross_previous_flag_vwap = 0
            elif previous_data['close'] < previous_data['VWAP']:
                sma_cross_previous_flag_vwap = 1

            if current_data['20_SMA'] > current_data['200_SMA']:
                sma_cross_current_flag_sma = 0
            elif current_data['20_SMA'] < current_data['200_SMA']:
                sma_cross_current_flag_sma = 1

            if current_data['close'] > current_data['VWAP']:
                sma_cross_current_flag_vwap = 0
            elif current_data['close'] < current_data['VWAP']:
                sma_cross_current_flag_vwap = 1

            if sma_cross_current_flag_sma is not None and sma_cross_current_flag_vwap is not None and sma_cross_previous_flag_vwap is not None and sma_cross_previous_flag_sma is not None:
                if (sma_cross_previous_flag_sma == 0 and sma_cross_current_flag_sma == 1) or (sma_cross_previous_flag_vwap == 0 and sma_cross_current_flag_vwap == 1):
                    df_resampled_5_min.at[current_data.name, 'Entry short'] = True
                elif (sma_cross_previous_flag_sma == 1 and sma_cross_current_flag_sma == 0) or (sma_cross_previous_flag_vwap == 1 and sma_cross_current_flag_vwap == 0):
                    df_resampled_5_min.at[current_data.name, 'Entry long'] = True

            if sma_cross_current_flag_vwap is not None and sma_cross_previous_flag_vwap is not None :
                if (sma_cross_previous_flag_vwap == 0 and sma_cross_current_flag_vwap == 1):
                    df_resampled_5_min.at[current_data.name, 'Exit long'] = True
                elif (sma_cross_previous_flag_vwap == 1 and sma_cross_current_flag_vwap == 0):
                    df_resampled_5_min.at[current_data.name, 'Exit short'] = True

    df_resampled_1_min = add_auto_increment_id(df_resampled_1_min)
    df_resampled_5_min = add_auto_increment_id(df_resampled_5_min)

    return df_resampled_1_min, df_resampled_5_min

async def on_connect(instance):
    print("Connected to websocket")

async def on_message(instance, message):
    print("Received")
    if message['type'] == 'Quote Data':

        df_quote_data = pd.DataFrame([message])
        print(df_quote_data)
        df_quote_data.to_sql('market_data2', con=engine, if_exists='append', index=False)

        # Resample and generate signals
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM market_data2", conn)
        df_resampled_1_min, df_resampled_5_min = resample_and_generate_signals(df)
        
        # Save resampled data back to database
        df_resampled_1_min.to_sql('market_data_resampled_1_min', conn, if_exists='replace', index=False)
        df_resampled_5_min.to_sql('market_data_resampled_5_min', conn, if_exists='replace', index=False)
        conn.close()
        print("Sql Op Done")
        
        # Send signals to Flask with adjusted LTP
        for index, row in df_resampled_5_min.iterrows():

            print(row)


            if row['Entry short'] == True:
                print("Executed Entry short")
                adjusted_ltp = adjust_ltp(row['LTP'], 'short')
                requests.post("http://localhost:5000/signal", json={"signal": "Entry short", "adjusted_ltp": adjusted_ltp})

            if row['Entry long'] == True:
                print("Executed Entry long")
                adjusted_ltp = adjust_ltp(row['LTP'], 'long')
                requests.post("http://localhost:5000/signal", json={"signal": "Entry long", "adjusted_ltp": adjusted_ltp})

            if row['Exit short'] == True:
                print("Executed Exit short")
                adjusted_ltp = adjust_ltp(row['LTP'], 'short')
                requests.post("http://localhost:5000/signal", json={"signal": "Exit short", "adjusted_ltp": adjusted_ltp})

            if row['Exit long'] == True:
                print("Executed Exit long")
                adjusted_ltp = adjust_ltp(row['LTP'], 'long')
                requests.post("http://localhost:5000/signal", json={"signal": "Exit long", "adjusted_ltp": adjusted_ltp})
db_path = '/root/myflaskapp/final/Important_Files/Final_files/market_data.db'
engine = create_engine(f'sqlite:///{db_path}')

# Load scrip master data
scrip_master = pd.read_csv('/root/myflaskapp/final/CSV/api-scrip-master.csv', low_memory=False)

# Example usage
symbol = 'NIFTY'
current_date = date.today()
contract_type = 'FUT'

token = create_token(symbol, current_date, contract_type)
security_id = get_security_id(scrip_master, token)
sid = str(security_id)
client_id = "1000481653"
access_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzI0ODE0OTA2LCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTAwMDQ4MTY1MyJ9.TqS-Abarn1Z0X3Z6Z1voLH5k--9JICJ4Co8hVjBiTDjgyx1fa2zQaZcDt3Th0u2bEYFnB8NMLE_k3zdFecfkPA"


print(f"Token: {token}")
print(f"SEM_SMST_SECURITY_ID: {security_id}")

instruments = [(2, sid)]
subscription_code = marketfeed.Quote
print("Started")
feed = marketfeed.DhanFeed(
    client_id,
    access_token,
    instruments,
    subscription_code,
    on_connect = on_connect,
    on_message = on_message,
)

# loop = asyncio.get_event_loop()
# loop.run_until_complete(feed.run_forever())
feed.run_forever()