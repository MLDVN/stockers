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



def compute_ma(df, days):
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


def send_mail_alert(ticker, my_alert_message):

	time_now = datetime.now().isoformat(' ', 'seconds')

	# TODO: Get password from ./config file
	password = getpass("Insert your password here:\n")
	sender = input("Insert your email here:\n")
	receiver = ['vladmoldovan56@gmail.com','octavbirsan@gmail.com']
	message = """This message is sent from Stockers."""
	

	msg = EmailMessage()
	msg.set_content(message)
	msg['Subject'] = f"{time_now}: Stockers signal on {ticker}."
	msg['From'] = sender
	msg['To'] = receiver

	context = ssl.create_default_context()
	with smtplib.SMTP_SSL("smtp.gmail.com", port=465, context=context) as server:
		server.login(sender, password)
		server.send_message(msg)
		print("Email alert sent successfully!")



def get_bd_bo(ticker=None):
	# ticker_stats = {}
	# for info in INFO_STATS:
	# 	if ticker.info[info]:
	# 		ticker_stats[info] = ticker.info[info]

	df = ticker.history(period='max')

	df['MA_5'] = compute_ma(df, 5)
	df['MA_10'] = compute_ma(df, 10)
	df['MA_20'] = compute_ma(df, 20)
	df['MA_200'] = compute_ma(df, 200)
	# print(df.loc[df['Dividends'] != 0.0])

	df['RSI'] = compute_rsi(df, 14)
	# df = df.drop(columns=['Volume', 'Stock Splits'])

	df_nostru=pd.DataFrame()
	df_nostru['Open']=df['Open']
	df_nostru['Close']=df['Close']
	df_nostru['MA_20']=df['MA_20']
	df_nostru['RSI']=df['RSI']
	# df_nostru['Current_Price']=ticker.info['regularMarketPrice']
	print(df_nostru)
	# print(f"CURRENT PRICE AVEM?? {ticker.info['regularMarketPrice']}")
	# df=df[:-47]
	last_day = df.iloc[-1]
	previous_day = df.iloc[-2]
	if last_day['Open'] < last_day['MA_20'] and last_day['Close'] > last_day['MA_20']:
		print(f"BREAKOUT ON {ticker}!!! PRICE JUST CLOSED ABOVE THE MA_20")
	
	#piata deschisa
	if last_day['Open'] > last_day['MA_20'] and last_day['Close'] > last_day['MA_20'] and previous_day['Close'] < previous_day['MA_20']:
		print(f"BREAKOUT ON {ticker.ticker}!! PRICE JUST OPENED ABOVE THE MA_20")


	if last_day['Close'] < last_day['MA_20'] and last_day['Open'] > last_day['MA_20']:
		print(f"BREAKDOWN ON {ticker}!!!PRICE JUST CLOSED BELOW THE MA_20")
	
	#
	if previous_day['Close'] > previous_day['MA_20'] and last_day['Close'] < last_day['MA_20'] and last_day['Open'] < last_day['MA_20']:
		print(f"BREAKDOWN ON {ticker.ticker}!! PRICE JUST OPENED BELOW THE MA_20")


	if df.iloc[-1]['Dividends']:
		print("EX DIVIDEND DATE!!!")


def get_tickers(url):
	 sheets = Sheets.from_files(CREDENTIALS_JSON, STORAGE_JSON)
	 worksheet = sheets.get(url).find('Sheet2')
	 df_worksheet = worksheet.to_frame()
	 # print(type(df_worksheet))
	 return df_worksheet['TICKER'].tolist()


def main():
	# ticker = yf.Ticker('DFS')
	# get_bd_bo(ticker)


	ticker_list = get_tickers(STOCKERS_URL)
	print(ticker_list)


	for elem in ticker_list:
		ticker = yf.Ticker(elem)
		print(f"TICKER {elem}")
		get_bd_bo(ticker)
	
	
if __name__ == '__main__':
	# main()
	send_mail_alert("XOM",1)