import argparse
import gspread
import os
import sys
import time
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

from operations import get_credentials, send_mail_alert
from scrapers import scrape_t212_tickers

CREDENTIALS_JSON = 'stockers_service_key.json'
STOCKERS_URL = 'https://docs.google.com/spreadsheets/d/1zEt_CQo8RI808xXFARTPvcTD7Rop_9zQ5Uw8Uq-Ywmk/edit#gid=0'

INFO_STATS = ['previousClose','regularMarketOpen','regularMarketDayHigh','regularMarketDayLow','market',
            'morningStarRiskRating','morningStarOverallRating','regularMarketPrice','dayHigh','dayLow',
            'fiftyTwoWeekLow','fiftyTwoWeekHigh','exDividendDate','fiftyDayAverage','twoHundredDayAverage',
            'dividendRate','trailingAnnualDividendRate']

PROFILE_SHEETS = ['T212', 'Revolut', 'Dida', 'Sirbu', 'Dividend', 'Moldo_Watchlist']
MARKETS_v1 = ['US', 'NON-US', 'L', 'DE', 'PA', 'MC', 'AS', 'SW']  # using tickers dot extensions
MARKETS = ['us', 'gb', 'de', 'es', 'fr', 'ch', 'nl', 'non-us']  # using ticker info market key


def get_parser():
    parser = argparse.ArgumentParser(description='Stock tracker argument parser.')
    parser.add_argument('-p','--profile', type=str, default='T212', choices=PROFILE_SHEETS,
                        help='profile of tickers to use representing a sheet; default: T212.')
    parser.add_argument('-e','--exchange', type=str, default='', choices=MARKETS,
                        help='stock exchange to use (us, gb, de, es, fr, ch, nl, non-us); default: all.')
    parser.add_argument('-t', '--ticker', type=str, default='',
                        help='provide data for one ticker only.')
    parser.add_argument('-l', '--last_day_only', action='store_true',
                        help='get only the last day of trading data if it is set.')
    parser.add_argument('-u', '--update_worksheet', action='store_true',
                        help='update worksheet if it is set.')
    parser.add_argument('-tp', '--ticker_period', type=str, default='max',
                        help='period of time to retrieve data for a ticker; default: max.')

    return parser.parse_args()


def compute_ema(df, days):
    return round(df['Close'].ewm(span=days, adjust=False).mean(), 2)


def compute_sma(df, days, shifted=False):
    if shifted:
        return df['Close'].shift().rolling(window=days).mean()
    else:
        return round(df['Close'].rolling(window=days).mean(), 2)


def compute_rsi(df, time_window=14):
    diff = df['Close'].diff().dropna()

    up_chg = 0 * diff
    down_chg = 0 * diff

    up_chg[diff > 0] = diff[ diff>0 ]
    down_chg[diff < 0] = diff[ diff < 0 ]

    up_chg_avg   = up_chg.ewm(com=time_window-1 , min_periods=time_window).mean()
    down_chg_avg = down_chg.ewm(com=time_window-1 , min_periods=time_window).mean()

    rs = abs(up_chg_avg/down_chg_avg)
    rsi = 100 - 100/(1+rs)

    return round(rsi, 2)


def compute_macd(df, fast_period=12, slow_period=26, signal_period=9):
    fast_ema = compute_ema(df, fast_period)
    slow_ema = compute_ema(df, slow_period)
    macd = fast_ema - slow_ema

    df_copy = df.copy()
    df_copy['Close'] = macd
    signal_ema = compute_ema(df_copy, signal_period)

    macd_histo = round(macd - signal_ema, 3)

    return macd_histo


def compute_trend(df):
    conditions = [
        (df['EMA_5'] > df['EMA_10']) & (df['EMA_10'] > df['SMA_20']),
        (df['EMA_5'] < df['EMA_10']) & (df['EMA_10'] < df['SMA_20']),
    ]
    values =['\u279A', '\u2798']
    return np.select(conditions, values, default = '\u2799')


def compute_box(df, trailing_days=4, threshold_percentage=0.04):
    # average_price_for_trailing_days = compute_sma(df, 4, shifted=True)
    conditions = [
        # abs(df['Close'] - average_price_for_trailing_days) > (threshold_percentage * average_price_for_trailing_days), 
        # abs(df['Close'] - average_price_for_trailing_days) < (threshold_percentage * average_price_for_trailing_days), 
        abs(df['Close'] - df['EMA_5']) > (threshold_percentage * df['EMA_5']), 
        abs(df['Close'] - df['EMA_5']) < (threshold_percentage * df['EMA_5']), 
    ]
    values = ['OUT', 'IN']

    return np.select(conditions, values)

def compute_break_sma_20(df):
    conditions = [
        (df['Close'] > df['SMA_20']) & (df['Close'].shift() < df['SMA_20'].shift()),
        (df['Close'] < df['SMA_20']) & (df['Close'].shift() > df['SMA_20'].shift()),
    ]
    values = ['\u279A', '\u2798']

    return np.select(conditions, values, default='')

## WIP
def compute_stage(df):
    conditions = [
        (df['Break_20'] == '\u279A') | ((df['Box'] == 'OUT') & (df['Close'] > df['SMA_20']) & (df['Trend'] != '\u2798')),
        (df['Break_20'] == '\u2798') | ((df['Box'] == 'OUT') & (df['Close'] < df['SMA_20']) & (df['Trend'] != '\u279A')),
        (df['Box'] == 'IN') & (df['RSI'] < 50),
        (df['Box'] == 'IN') & (df['RSI'] > 50),
        # (df['Break_20'] == '\u2798') | (df['Close'] < df['SMA_20'] & df['Box'] == 'OUT'),
    ]
    values = [2, 4, 1, 3]

    return np.select(conditions, values, default='???')


def compute_ticker_df(ticker=None, period='max'):
    try:
        time_now = datetime.now().isoformat(' ', 'seconds')
        print(f'{time_now} Requesting data for ticker: {ticker}')
        ticker = yf.Ticker(ticker)
        df = ticker.history(period=period)
        info = ticker.get_info()
    except:
        print(f"Ticker {ticker} failed!")
        return pd.DataFrame()

    else:
        df['Ticker'] = ticker.ticker
        df['Market'] = info['market'].split('_')[0]
        df['EMA_5'] = compute_ema(df, 5)
        df['EMA_10'] = compute_ema(df, 10)
        df['SMA_20'] = compute_sma(df, 20)
        df['SMA_200'] = compute_sma(df, 200)
        df['RSI'] = compute_rsi(df, 14)
        df['MACD'] = compute_macd(df)
        # df['prev4SMA'] = compute_sma(df, 4, shifted=True)
        df['Box'] = compute_box(df)
        df['Trend'] = compute_trend(df)
        df['Break_20'] = compute_break_sma_20(df)
        df['Stage'] = compute_stage(df)

        df = df.round(decimals=3)
        # df = df.drop(columns=['Volume', 'Stock Splits'])
        df = df.reset_index().set_index('Ticker')

        return df

def compute_market_df(ticker_list, last_day_only):
    # COLUMN_NAMES = ['Date', 'Ticker', 'Close', 'RSI', 'MACD', 'MA_5', 'MA_20', 'MA_200']
    # df_market = pd.DataFrame(columns=COLUMN_NAMES)
    df_market = pd.DataFrame()

    for ticker in ticker_list:
        df_ticker = compute_ticker_df(ticker=ticker)
        if not df_ticker.empty:
            if last_day_only:
                df_market = df_market.append(df_ticker.tail(1)) 
                df_market = df_market.sort_values(by=['RSI'])
            else:
                df_market = df_market.append(df_ticker)

    if not df_market.empty:
        return df_market
    else:
        return pd.DataFrame()


def get_market_df(ticker_list, last_day_only, save_to_file=False):
    if save_to_file:
        if os.path.isfile('last_day.csv') and os.path.getmtime('last_day.csv') > time.time() - 12 * 3600:
          df_market = pd.read_csv('last_day.csv', index_col='Ticker')
        else:
          df_market = compute_market_df(ticker_list, last_day_only)
          if not df_market.empty:
              df_market.to_csv('last_day.csv')
    else:
        df_market = compute_market_df(ticker_list, last_day_only)
    
    return df_market


def filter_exchange(df, exchange):
    if exchange == 'non-us':
        markets = set(MARKETS)
        markets.remove('non-us')
        markets.remove('us')
        df = df[df['Market'].isin(markets)] 
    else:
        df = df[df['Market'] == exchange]
    df = df.reset_index(drop=True)

    return df


def get_worksheet(url, sheet):
    gconn = gspread.service_account(filename=CREDENTIALS_JSON)
    worksheet = gconn.open_by_url(url).worksheet(sheet)

    return worksheet


def main():
    t0 = time.time()
    argp = get_parser()
    ticker = argp.ticker
    sheet_name = argp.profile
    exchange = argp.exchange
    update_worksheet = argp.update_worksheet
    last_day_only = argp.last_day_only

    tickers_to_manually_check = set()
    alert_message = []

    ## returnez date doar pentru un ticker, iar mai apoi opresc executia...WIP 
    if ticker:
        df_ticker = compute_ticker_df(ticker,period=argp.ticker_period)
        print(df_ticker)
        sys.exit(1)

    ## iau worksheet-ul de lucru in functie de profil
    worksheet = get_worksheet(STOCKERS_URL, sheet_name)

    ## descarc tickerele de pe t212
    # t212_tickers = scrape_t212_tickers()
    # worksheet.update('A1', [['Ticker']] + t212_tickers)

    ## iau lista de tickere
    df_worksheet = pd.DataFrame(worksheet.get_all_records())  # get the data in a DataFrame in case we store more data there, in the future
    ticker_list = df_worksheet['Ticker'].tolist()

    ## construiesc market_df
    df_market = get_market_df(ticker_list, last_day_only)
    df_market = df_market.reset_index()
    df_market = df_market.astype(str)

    ## filtrez in functie de bursa
    if exchange:
        df_market = filter_exchange(df_market, exchange)

    print(df_market)

    ## incarc market_df pe gsheet
    if update_worksheet:
        worksheet.update([df_market.columns.values.tolist()] + df_market.values.tolist())


    print(f'Computation took: {(time.time() - t0):.2f} seconds')

if __name__ == '__main__':
    main()
