import argparse
import os
import time
import smtplib
import ssl
import pandas as pd
import numpy as np
import yfinance as yf
import gspread
from datetime import datetime
from getpass import getpass
from email.message import EmailMessage
# from tabulate import tabulate

STOCKERS_URL = 'https://docs.google.com/spreadsheets/d/1zEt_CQo8RI808xXFARTPvcTD7Rop_9zQ5Uw8Uq-Ywmk/edit#gid=0'

INFO_STATS = ['previousClose','regularMarketOpen','regularMarketDayHigh','regularMarketDayLow','market',
			'morningStarRiskRating','morningStarOverallRating','regularMarketPrice','dayHigh','dayLow',
			'fiftyTwoWeekLow','fiftyTwoWeekHigh','exDividendDate','fiftyDayAverage','twoHundredDayAverage',
			'dividendRate','trailingAnnualDividendRate']
RECEIVERS = ['vladmoldovan56@gmail.com','octavbirsan@gmail.com', 'adrian_steau@yahoo.com', 'sirbu96vlad@gmail.com', 'bogdanrogojan96@gmail.com', 'barb.alin.gabriel.pp@gmail.com']
RECEIVERS_SHORTLIST = ['vladmoldovan56@gmail.com', 'adrian_steau@yahoo.com', 'sirbu96vlad@gmail.com']


CREDENTIALS_JSON = 'stockers_service_key.json'
CONFIG_FILE = '.config'

# def get_parser():
# 	parser = argparse.ArgumentParser(description='Process Stockers Tracker:P')
# 	parser.add_argument('profile', type=string, nargs='',default='all'
#                     help='Value for members profiles')

# 	print(parser)

def scrape_t212_tickers():
	import requests
	import bs4
	import re
	mappings = {'London Stock Exchange': '.L', 'Deutsche Börse Xetra': '.DE', 'Euronext Paris': '.PA', 'Bolsa de Madrid': '.MC', 
				'Euronext Netherlands': '.AS', 'LSE AIM': '.L', 'SIX Swiss': '.SW', 'NASDAQ': '', 
				'NON-ISA NASDAQ': '', 'NON-ISA NYSE': '', 'NYSE': '', 'OTC Markets': '', 'NON-ISA London Stock Exchange': ''}

	headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'}
	url = 'https://www.trading212.com/en/Trade-Equities'
	req = requests.get(url=url, headers=headers)
	
	soup = bs4.BeautifulSoup(req.text, 'lxml')

	l = [t for t in soup.find_all('div', {'id': re.compile('equity-row-[0-9]+')})]
	tickers = [[str(i.find('div', {'data-label': 'Instrument'}).text+mappings[i.find('div', {'data-label': 'Market name'}).text])] for i in l[6:]]

	return tickers

def get_credentials(account='email'):
	with open(CONFIG_FILE) as f:
		lines = f.readlines()

	for idx, line in enumerate(lines):
		if line.rstrip('\n') == f'[{account}]':
			break

	user = (lines[idx+1].rstrip('\n').split('='))[1]
	pw = lines[idx+2].rstrip('\n').split('=')[1]

	return user, pw


def send_mail_alert(alert_message):
	time_now = datetime.now().isoformat(' ', 'seconds')

	sender, password = get_credentials()

	msg = EmailMessage()
	msg.set_content(alert_message)
	msg['Subject'] = f"{time_now}: Stockers signals for today."
	msg['From'] = sender
	msg['To'] = RECEIVERS_SHORTLIST

	context = ssl.create_default_context()
	with smtplib.SMTP_SSL("smtp.gmail.com", port=465, context=context) as server:
		server.login(sender, password)
		server.send_message(msg)
		print("Email alert sent successfully!")


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
	# ticker_stats = {}
	# for info in INFO_STATS:
		# if ticker.info[info]:
			# ticker_stats[info] = ticker.info[info]

	try:
		ticker = yf.Ticker(ticker)
		df = ticker.history(period=period)

	except:
		print(f"Ticker {ticker} failed!")
		return pd.DataFrame()

	else:
		df['Ticker'] = ticker.ticker
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

def compute_last_day_market_df(ticker_list):
	# COLUMN_NAMES = ['Date', 'Ticker', 'Close', 'RSI', 'MACD', 'MA_5', 'MA_20', 'MA_200']
	# df_market = pd.DataFrame(columns=COLUMN_NAMES)
	df_market = pd.DataFrame()

	for ticker in ticker_list:
		df_ticker = compute_ticker_df(ticker=ticker)
		if not df_ticker.empty:
			df_market = df_market.append(df_ticker.tail(1)) 
			df_market = df_market.sort_values(by=['RSI'])

	if not df_market.empty:
		return df_market
	else:
		return pd.DataFrame()


def get_market_df(ticker_list):
	# if os.path.isfile('last_day.csv') and os.path.getmtime('last_day.csv') > time.time() - 12 * 3600:
	# 	df_market = pd.read_csv('last_day.csv', index_col='Ticker')
	# else:
	# 	df_market = compute_last_day_market_df(ticker_list)
	# 	if not df_market.empty:
	# 		df_market.to_csv('last_day.csv')

	df_market = compute_last_day_market_df(ticker_list)
	return df_market


## obsolete
def get_bo_bd(ticker, df_ticker, tickers_to_manually_check, message):
	current_day = df_ticker.iloc[-1]
	previous_day = df_ticker.iloc[-2]

	# breakout
	if previous_day.Close < previous_day['SMA_20'] and current_day.Close > current_day['SMA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker} breaking out above the 20-day SMA!")
		print(f"{ticker} breaking out above the 20-day SMA!")

	# breakdown
	if previous_day.Close > previous_day['SMA_20'] and current_day.Close < current_day['SMA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker} breaking down below the 20-day SMA!")
		print(f"{ticker} breaking down below the 20-day SMA!")

	# ex-dividend date (deocamdata nu merge, are delay de 1 zi :()
	if df_ticker.iloc[-1]['Dividends']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: EX DIVIDEND DATE!!!")
		print(f"{ticker}: EX DIVIDEND DATE!!!")

	return tickers_to_manually_check, message


def get_worksheet(url, sheet):
	gconn = gspread.service_account(filename=CREDENTIALS_JSON)
	worksheet = gconn.open_by_url(url).worksheet(sheet)

	return worksheet


def main():
	t0 = time.time()

	tickers_to_manually_check = set()
	alert_message = []

	## iau profilul dat ca argument
	# argp = get_parser()
	# sheet_name = argp['profile']

	## iau worksheet-ul de lucru in functie de profil
	sheet_name = "T212"
	# worksheet = get_worksheet(STOCKERS_URL, sheet_name)
	gconn = gspread.service_account(filename=CREDENTIALS_JSON)
	worksheet = gconn.open_by_url(STOCKERS_URL).worksheet(sheet_name)


	## descarc tickerele de pe t212
	# t212_tickers = scrape_t212_tickers()
	# worksheet.update('A1', [['Ticker']] + t212_tickers)


	## iau lista de tickere
	# ticker_list = pd.DataFrame(worksheet.get_all_records())['TICKER'].tolist()
	df_worksheet = pd.DataFrame(worksheet.get_all_records())
	ticker_list = df_worksheet['Ticker'].tolist()

	## construiesc market_df
	df_market = get_market_df(ticker_list)
	df_market = df_market.reset_index()
	df_market = df_market.astype(str)
	print(df_market)

	## incarc market_df pe gsheet
	worksheet.update([df_market.columns.values.tolist()] + df_market.values.tolist())


	## construiesc si trimit alerta
	# tickers_to_manually_check = ', '.join(tickers_to_manually_check)
	# alert_message = '\n'.join(map(str, alert_message))
	# alert_message = 'Tickers you should check: ' + tickers_to_manually_check + '\n\n' + alert_message + '\n\n'
	# # alert_message = 'Tickers you should check: ' + tickers_to_manually_check + '\n\n' + alert_message + '\n\n' + tabulate(df_market, headers='keys', tablefmt='psql')

	# print(alert_message)
	# send_mail_alert(alert_message=alert_message)

	print(f'Computation took: {(time.time() - t0):.2f} seconds')

if __name__ == '__main__':
	main()

