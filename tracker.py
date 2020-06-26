import pandas as pd
import yfinance as yf

INFO_STATS = ['previousClose','regularMarketOpen','regularMarketDayHigh','regularMarketDayLow','market',
			'morningStarRiskRating','morningStarOverallRating','regularMarketPrice','dayHigh','dayLow',
			'fiftyTwoWeekLow','fiftyTwoWeekHigh','exDividendDate','fiftyDayAverage','twoHundredDayAverage',
			'dividendRate','trailingAnnualDividendRate']


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


def main():
	ticker = input("Introduceti ticker-ul companiei: ")
	ticker = yf.Ticker(ticker)
	
	ticker_stats = {}
	for info in INFO_STATS:
		if ticker.info[info]:
			ticker_stats[info] = ticker.info[info]

	df = ticker.history(period='max')

	df['MA_5'] = compute_ma(df, 5)
	df['MA_10'] = compute_ma(df, 10)
	df['MA_20'] = compute_ma(df, 20)
	df['MA_200'] = compute_ma(df, 200)
	# print(df.loc[df['Dividends'] != 0.0])

	# df['ticker'] = ticker
	df['RSI'] = compute_rsi(df, 14)
	df = df.drop(columns=['Volume', 'Stock Splits'])
	# print(df[-50:-11])

	df = df[-20:-14]
	print(df)
	print(ticker.info)
	last_day = df.iloc[-1]
	previous_day = df.iloc[-2]
	if last_day['Close'] > last_day['MA_20'] and previous_day['Close'] < previous_day['MA_20']:
		print("PRICE JUST CLOSED ABOVE THE MA_20")
	
	if df.iloc[-1]['Dividends']:
		print("EX DIVIDEND DATE!!!")

if __name__ == '__main__':
	main()
