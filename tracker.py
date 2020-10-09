import os, time
import smtplib, ssl
import pandas as pd
import yfinance as yf
from gsheets import Sheets
from datetime import datetime
from getpass import getpass
from email.message import EmailMessage

STOCKERS_URL = 'https://docs.google.com/spreadsheets/d/1zEt_CQo8RI808xXFARTPvcTD7Rop_9zQ5Uw8Uq-Ywmk/edit#gid=0'

INFO_STATS = ['previousClose','regularMarketOpen','regularMarketDayHigh','regularMarketDayLow','market',
			'morningStarRiskRating','morningStarOverallRating','regularMarketPrice','dayHigh','dayLow',
			'fiftyTwoWeekLow','fiftyTwoWeekHigh','exDividendDate','fiftyDayAverage','twoHundredDayAverage',
			'dividendRate','trailingAnnualDividendRate']
CREDENTIALS_JSON = './credentials.json'
STORAGE_JSON = './storage.json'
CONFIG_FILE = '.config'



def get_credentials(account='email'):
	with open(CONFIG_FILE) as f:
		lines = f.readlines()

	for idx, line in enumerate(lines):
		if line.rstrip('\n') == f'[{account}]':
			break 

	user = (lines[idx+1].rstrip('\n').split('='))[1]
	pw = lines[idx+2].rstrip('\n').split('=')[1]

	return user, pw


def compute_ema(df, days):
	return round(df['Close'].ewm(span=days, adjust=False).mean(), 2)


def compute_sma(df, days):
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
	
	df2 = df.copy()
	df2['Close'] = macd
	signal_ema = compute_ema(df2, signal_period)
	
	macd_histo = round(macd - signal_ema, 3)

	return macd_histo


def send_mail_alert(alert_message):

	time_now = datetime.now().isoformat(' ', 'seconds')

	sender, password = get_credentials()
	# receiver = ['vladmoldovan56@gmail.com']
	receiver = ['vladmoldovan56@gmail.com','octavbirsan@gmail.com', 'adrian_steau@yahoo.com', 'sirbu96vlad@gmail.com', 'bogdanrogojan96@gmail.com',]
	

	msg = EmailMessage()
	msg.set_content(alert_message)
	msg['Subject'] = f"{time_now}: Stockers signals for today."
	msg['From'] = sender
	msg['To'] = receiver

	context = ssl.create_default_context()
	with smtplib.SMTP_SSL("smtp.gmail.com", port=465, context=context) as server:
		server.login(sender, password)
		server.send_message(msg)
		print("Email alert sent successfully!")


def compute_ticker_df(ticker=None, period='max'):
	# ticker_stats = {}
	# for info in INFO_STATS:
		# if ticker.info[info]:
			# ticker_stats[info] = ticker.info[info]

	try:
		ticker = yf.Ticker(ticker)
		df = ticker.history(period=period)
		
		df['Ticker'] = ticker.ticker
		df['EMA_5'] = compute_ema(df, 5)
		# df['MA_5'] = compute_sma(df, 5)
		df['MA_10'] = compute_sma(df, 10)
		df['MA_20'] = compute_sma(df, 20)
		df['MA_200'] = compute_sma(df, 200)
		df['RSI'] = compute_rsi(df, 14)
		df['MACD'] = compute_macd(df)

		# print(df.loc[df['Dividends'] != 0.0])
		# df = df.drop(columns=['Volume', 'Stock Splits'])
	
		df = df.reset_index().set_index('Ticker')
		# df = df[['Date', 'Open', 'Close', 'RSI', 'MA_5', 'MA_20']]
	
		return df

	except:
		print(f"Ticker {ticker} failed!")
		return pd.DataFrame()

def get_tickers(url):
	 sheets = Sheets.from_files(CREDENTIALS_JSON, STORAGE_JSON)
	 worksheet = sheets.get(url).find('Sheet3')
	 df_worksheet = worksheet.to_frame()

	 return df_worksheet['TICKER'].tolist()


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


def get_breakdowns_breakouts(ticker, tickers_to_manually_check, message):

	print(f"Checking ticker {ticker}!")
	df_ticker = compute_ticker_df(ticker=ticker)

	last_day = df_ticker.iloc[-1]
	previous_day = df_ticker.iloc[-2]


	three_smallest = df_ticker.nsmallest(3, 'Close')
	second_min = float(three_smallest.head(2).tail(1).Close)
	# print(f"{ticker} with SECOND_MIN= {second_min}, ")
	# print(f"ALST DAY CLOSE {type(last_day.Close)}")
	if last_day.Close <= second_min:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker} just closed lower or equal than second min ({last_day.Close} <= {second_min}")
		print(f"{ticker} just closed lower or equal than second min ({last_day.Close} <= {second_min}")

	#fake close above (2 days in a row above)
	if previous_day['Close'] > previous_day['MA_20'] and last_day['Open'] < last_day['MA_20'] and last_day['Close'] > last_day['MA_20'] :
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: FAKE BREAKOUT!!! PRICE JUST CLOSED ABOVE THE MA_20.")
		print(f"{ticker}: FAKE BREAKOUT!!! PRICE JUST CLOSED ABOVE THE MA_20.")
	
	#opened and closed above
	if previous_day['Close'] < previous_day['MA_20'] and last_day['Open'] > last_day['MA_20'] and last_day['Close'] > last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKOUT!! PRICE OPENED AND CLOSED ABOVE THE MA_20.")
		print(f"{ticker}: BREAKOUT!! PRICE OPENED AND CLOSED ABOVE THE MA_20.")

	#opened below closed above
	if previous_day['Close'] < previous_day['MA_20'] and last_day['Open'] < last_day['MA_20'] and last_day['Close'] > last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKOUT!! PRICE OPENED BELOW AND CLOSED ABOVE THE MA_20.")
		print(f"{ticker}: BREAKOUT!! PRICE OPENED BELOW AND CLOSED ABOVE THE MA_20.")


	#fake close below
	if previous_day['Close'] < previous_day['MA_20'] and last_day['Open'] > last_day['MA_20'] and last_day['Close'] < last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: FAKE BREAKDOWN!!!PRICE JUST CLOSED BELOW THE MA_20.")
		print(f"{ticker}: FAKE BREAKDOWN!!!PRICE JUST CLOSED BELOW THE MA_20.")
	
	#opened above closed below
	if previous_day['Close'] > previous_day['MA_20'] and last_day['Open'] > last_day['MA_20'] and last_day['Close'] < last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKDOWN!! PRICE OPENED ABOVE AND CLOSED BELOW THE MA_20.")
		print(f"{ticker}: BREAKDOWN!! PRICE OPENED ABOVE AND CLOSED BELOW THE MA_20.")

	#opened and closed below
	if previous_day['Close'] > previous_day['MA_20'] and last_day['Open'] < last_day['MA_20'] and last_day['Close'] < last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKDOWN!! PRICE OPENED AND CLOSED BELOW THE MA_20.")
		print(f"{ticker}: BREAKDOWN!! PRICE OPENED AND CLOSED BELOW THE MA_20.")


	if last_day['RSI'] < 30 and previous_day['RSI'] > 30:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: RSI JUST CLOSED BELOW 30!!!!")
		print(f"{ticker}: RSI JUST CLOSED BELOW 30!!!!")

	if last_day['RSI'] > 70 and previous_day['RSI'] < 70:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: RSI JUST CLOSED ABOVE 70!!!!")
		print(f"{ticker}: RSI JUST CLOSED ABOVE 70!!!!")


	if df_ticker.iloc[-1]['Dividends']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: EX DIVIDEND DATE!!!")
		print(f"{ticker}: EX DIVIDEND DATE!!!")


	return tickers_to_manually_check, message 


def main():
	## aici imi construiesc market_df
	ticker_list = get_tickers(STOCKERS_URL)

	if os.path.getmtime('last_day.csv') < time.time() - 12 * 3600:
		df_market = compute_last_day_market_df(ticker_list)
	else:
		df_market = pd.read_csv('last_day.csv')

	if not df_market.empty:
		df_market.to_csv('last_day.csv')
	##

	df_market = compute_last_day_market_df(ticker_list)
	print(df_market)

	# df_market = df_market.head(20).append(df_market.tail(20))

	## aici imi verific fiecare ticker
	tickers_to_manually_check = set()
	breakdown_tickers = set()
	breakout_tickers = set()
	alert_message = []

	for ticker in ticker_list:
		get_breakdowns_breakouts(ticker, tickers_to_manually_check, alert_message) 


	## aici imi construiesc alerta
	tickers_to_manually_check = ', '.join(tickers_to_manually_check)
	alert_message = '\n'.join(map(str, alert_message))
	alert_message = 'Tickers you should check: ' + tickers_to_manually_check + '\n\n' + alert_message + '\n\n' + df_market.to_string()

	# print(alert_message)
	send_mail_alert(alert_message=alert_message)
	
	
if __name__ == '__main__':
	main()
