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
	# print(f"MACD = {macd}")
	return macd_histo

def send_mail_alert(alert_message):

	time_now = datetime.now().isoformat(' ', 'seconds')

	# TODO: Get password from ./config file
	sender = input("Insert your email here:\n")
	password = getpass("Insert your password here:\n")
	receiver = ['vladmoldovan56@gmail.com', 'sirbu96vlad@gmail.com']
	# receiver = ['vladmoldovan56@gmail.com','octavbirsan@gmail.com', 'adrian_steau@yahoo.com']
	

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
	
	# print(f'TICKER={ticker.ticker}\n{df}\n')
	return df


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
		df_ticker = compute_ticker_df(ticker=ticker).tail(1)
		df_market = df_market.append(df_ticker)


	return df_market.sort_values(by=['RSI'])


def get_breakdowns_breakouts(ticker, tickers_to_manually_check, message):

	# tickers_to_manually_check = set()
	# message = []

	df_ticker = compute_ticker_df(ticker=ticker)

	last_day = df_ticker.iloc[-1]
	previous_day = df_ticker.iloc[-2]

	if last_day['Open'] < last_day['MA_20'] and last_day['Close'] > last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKOUT!!! PRICE JUST CLOSED ABOVE THE MA_20.")
		print(f"{ticker}: BREAKOUT!!! PRICE JUST CLOSED ABOVE THE MA_20.")
	
	#piata deschisa
	if last_day['Open'] > last_day['MA_20'] and last_day['Close'] > last_day['MA_20'] and previous_day['Close'] < previous_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKOUT!! PRICE JUST OPENED ABOVE THE MA_20.")
		print(f"{ticker}: BREAKOUT!! PRICE JUST OPENED ABOVE THE MA_20.")

	if last_day['Close'] < last_day['MA_20'] and last_day['Open'] > last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKDOWN!!!PRICE JUST CLOSED BELOW THE MA_20.")
		print(f"{ticker}: BREAKDOWN!!!PRICE JUST CLOSED BELOW THE MA_20.")
	
	#
	if previous_day['Close'] > previous_day['MA_20'] and last_day['Close'] < last_day['MA_20'] and last_day['Open'] < last_day['MA_20']:
		tickers_to_manually_check.add(ticker)
		message.append(f"{ticker}: BREAKDOWN!! PRICE JUST OPENED BELOW THE MA_20.")
		print(f"{ticker}: BREAKDOWN!! PRICE JUST OPENED BELOW THE MA_20.")


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


	# return tickers_to_manually_check, message 


def main():
	## aici imi construiesc market_df
	ticker_list = get_tickers(STOCKERS_URL)
	df_market = compute_last_day_market_df(ticker_list)
	# df_market = pd.read_csv('last_day.csv')
	df_market.to_csv('last_day.csv')
	# print(df_market)
	##

	# df_market = df_market.head(20).append(df_market.tail(20))


	tickers_to_manually_check = set()
	alert_message = []

	for ticker in ticker_list:
		get_breakdowns_breakouts(ticker, tickers_to_manually_check, alert_message) 

	tickers_to_manually_check = ', '.join(tickers_to_manually_check)
	alert_message = '\n'.join(map(str, alert_message))
	alert_message = 'Tickers you should check: ' + tickers_to_manually_check + '\n' + alert_message + '\n\n' + df_market.to_string()
	# print(alert_message)
	send_mail_alert(alert_message=alert_message)
	
	
if __name__ == '__main__':
	main()
