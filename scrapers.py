import bs4
import re
import requests

def scrape_t212_tickers():
    exchanges_mappings = {'London Stock Exchange': '.L', 'Deutsche Börse Xetra': '.DE', 'Euronext Paris': '.PA', 'Bolsa de Madrid': '.MC', 
                'Euronext Netherlands': '.AS', 'LSE AIM': '.L', 'SIX Swiss': '.SW', 'NASDAQ': '', 
                'NON-ISA NASDAQ': '', 'NON-ISA NYSE': '', 'NYSE': '', 'OTC Markets': '', 'NON-ISA London Stock Exchange': ''}

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'}
    url = 'https://www.trading212.com/en/Trade-Equities'
    req = requests.get(url=url, headers=headers)
    
    soup = bs4.BeautifulSoup(req.text, 'lxml')

    l = [t for t in soup.find_all('div', {'id': re.compile('equity-row-[0-9]+')})]
    tickers = [[str(i.find('div', {'data-label': 'Instrument'}).text+mappings[i.find('div', {'data-label': 'Market name'}).text])] for i in l[6:]]

    return tickers
