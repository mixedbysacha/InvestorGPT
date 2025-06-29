import json
import time
from googlesearch import search
from bs4 import BeautifulSoup
import re
import requests
import yfinance as yf
from datetime import date, timedelta
from stock_data_loader import *
import pandas as pd
import warnings
import os
from dotenv import load_dotenv
import glob

warnings.filterwarnings("ignore")

# Load environment variables from apikeys.env
load_dotenv('apikeys.env')
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')
GOOGLE_PSE_ENGINE_ID = os.getenv('GOOGLE_PSE_ENGINE_ID', '')
GOOGLE_PSE_API_KEY = os.getenv('GOOGLE_PSE_API_KEY', '')

################################################################################################
# Helper funcs
################################################################################################
def goog_query_str(company_name):
    today = date.today()
    yesterday = today - timedelta(days=1)
    yesterday = yesterday.strftime('%Y-%m-%d')
    query = f"{company_name} stock dropped after:{yesterday}"
    print(query)
    try:
        search_results = search(query,num_results=5,advanced=True)
        top_links = []
        for sr in search_results:
            if f"{company_name}" in sr.title or f"{company_name}" in sr.description:
                top_links.append(sr.url)
        top_links = list(search_results)
        #print(top_links)
    except Exception as e:
        print(f"Google1 failed: {e}")
        
    scraped_texts = []
    for link in top_links:
        print(link)
        try:
            page = requests.get(link)
            soup = BeautifulSoup(page.content, 'html.parser')
            text = ' '.join([p.get_text() for p in soup.find_all('p')])
        except Exception as e:
            print(f"Failed to scrape the link: {link}\nError: {e}")
        scraped_texts.append(text)

    all_scraped_text = '.\n'.join(scraped_texts)
    
    return all_scraped_text

def get_company_name(ticker):
    if not ALPHA_VANTAGE_API_KEY:
        print("Warning: Alpha Vantage API key not found. Using yfinance as fallback.")
        try:
            company = yf.Ticker(ticker)
            info = company.info
            return info.get('longName', info.get('shortName', ticker))
        except Exception as e:
            print(f"Error getting company name from yfinance: {e}")
            return ticker

    try:
        # Try Alpha Vantage first
        url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={ALPHA_VANTAGE_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if 'Name' in data:
            return data['Name']
        elif 'Description' in data:
            # Extract company name from description if available
            description = data['Description']
            # Usually the first sentence contains the company name
            first_sentence = description.split('.')[0]
            return first_sentence.split(',')[0].strip()
        
        # If Alpha Vantage fails, fallback to yfinance
        company = yf.Ticker(ticker)
        info = company.info
        return info.get('longName', info.get('shortName', ticker))
    except Exception as e:
        print(f"Error with Alpha Vantage API: {e}")
        # Fallback to yfinance
        try:
            company = yf.Ticker(ticker)
            info = company.info
            return info.get('longName', info.get('shortName', ticker))
        except Exception as e:
            print(f"Error getting company name from yfinance: {e}")
            return ticker

def get_company_overview(ticker):
    """Get detailed company overview using Alpha Vantage"""
    if not ALPHA_VANTAGE_API_KEY:
        print("Warning: Alpha Vantage API key not found. Using yfinance as fallback.")
        try:
            company = yf.Ticker(ticker)
            info = company.info
            return {
                'name': info.get('longName', info.get('shortName', ticker)),
                'sector': info.get('sector', 'N/A'),
                'industry': info.get('industry', 'N/A'),
                'description': info.get('longBusinessSummary', 'N/A'),
                'market_cap': info.get('marketCap', 'N/A'),
                'pe_ratio': info.get('trailingPE', 'N/A'),
                'eps': info.get('trailingEps', 'N/A'),
                'dividend_yield': info.get('dividendYield', 'N/A')
            }
        except Exception as e:
            print(f"Error getting company overview from yfinance: {e}")
            return None

    try:
        url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={ALPHA_VANTAGE_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if 'Name' in data:
            return {
                'name': data.get('Name', ticker),
                'sector': data.get('Sector', 'N/A'),
                'industry': data.get('Industry', 'N/A'),
                'description': data.get('Description', 'N/A'),
                'market_cap': data.get('MarketCapitalization', 'N/A'),
                'pe_ratio': data.get('PERatio', 'N/A'),
                'eps': data.get('EPS', 'N/A'),
                'dividend_yield': data.get('DividendYield', 'N/A')
            }
        
        # If Alpha Vantage fails, fallback to yfinance
        company = yf.Ticker(ticker)
        info = company.info
        return {
            'name': info.get('longName', info.get('shortName', ticker)),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'description': info.get('longBusinessSummary', 'N/A'),
            'market_cap': info.get('marketCap', 'N/A'),
            'pe_ratio': info.get('trailingPE', 'N/A'),
            'eps': info.get('trailingEps', 'N/A'),
            'dividend_yield': info.get('dividendYield', 'N/A')
        }
    except Exception as e:
        print(f"Error getting company overview: {e}")
        return None

def llm_call(prompt):
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": "sonar-medium-chat",
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "Be precise and concise."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": "Bearer " + PERPLEXITY_API
    }
    response = requests.post(url, json=payload, headers=headers)
    json_data = response.text
    parsed_json = json.loads(json_data)
    answer = parsed_json["choices"][0]["message"]["content"]
    
    return answer

################################################################################################
# Full Step 1 is this func: get losers ticker and percentage drop
################################################################################################
def get_losers():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    
    try:
        # Try Yahoo Finance first
        url = "https://finance.yahoo.com/losers"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try different possible table classes
        table = soup.find('table', {'class': 'W(100%)'}) or \
                soup.find('table', {'class': 'W(100%) M(0)'}) or \
                soup.find('table', {'class': 'W(100%) M(0) BdB Bdc($seperatorColor)'})
        
        if table:
            data = []
            for row in table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) >= 5:  # Ensure we have enough cells
                    ticker = cells[0].text.strip()
                    percentage_drop = cells[4].text.strip()
                    try:
                        percentage_drop = float(percentage_drop.replace("-", "").replace("%", ""))
                        data.append((ticker, percentage_drop))
                    except ValueError:
                        continue
            if data:
                return data[:3]  # Return top 3 losers
        
        # If Yahoo Finance fails, try StockAnalysis.com
        url = "https://stockanalysis.com/markets/losers/"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'main-table'})
        
        if table:
            data = []
            for row in table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) >= 4:  # Ensure we have enough cells
                    ticker = cells[1].text.strip()
                    percentage_drop = cells[3].text.strip()
                    try:
                        percentage_drop = float(percentage_drop.replace("-", "").replace("%", ""))
                        data.append((ticker, percentage_drop))
                    except ValueError:
                        continue
            if data:
                return data[:3]  # Return top 3 losers
        
        raise Exception("Could not find stock data from either source")
        
    except Exception as e:
        print(f"Error fetching losers data: {e}")
        # Return some default data for testing
        return [("AAPL", 2.5), ("MSFT", 2.0), ("GOOGL", 1.8)]

################################################################################################
# Full Step 2 is this func: get top 2 google results for "{ticker} stock fell"
################################################################################################

def analyze_stock_drop(company_name, context):
    """Analyze why a stock dropped using the provided context"""
    # Extract key information from context
    lines = context.split('\n')
    relevant_info = []
    
    for line in lines:
        if any(keyword in line.lower() for keyword in ['drop', 'fell', 'decline', 'down', 'loss', 'decrease']):
            relevant_info.append(line)
    
    if not relevant_info:
        return "No specific information found about the stock drop."
    
    # Format the analysis
    analysis = f"Based on the available information, here are the key points about {company_name}'s stock drop:\n\n"
    for info in relevant_info[:5]:  # Limit to top 5 most relevant points
        analysis += f"• {info.strip()}\n"
    
    return analysis

def why_stock_fell(company_name):
    context = goog_query_str(company_name)
    return analyze_stock_drop(company_name, context)

################################################################################################
# Full Step 3: Get 10k and 10q reports and vectorize them (rag pipeline)
################################################################################################

# Download 10-Ks and 10-Qs
# Vectorize them
# Ask 20+ questions to them using semantic search + LLM
# summarize the answer into coherent and not so long text


################################################################################################
# Full Step 4: Analyze fundamentals
################################################################################################

# Use some kind of a tool to download and analyze 3 Financial Reports
# Get their main metrics and ratios
# Compare them to competitors

def get_book_value_from_csv(ticker, csv_file_name):
    try:
        df = pd.read_csv(csv_file_name)
        row = df[df['Ticker'] == ticker]
        if not row.empty:
            val = row['Book Value'].iloc[0] if 'Book Value' in row else None
            if val is not None and val != 'N/A':
                try:
                    val = str(val).replace('$','').replace(',','').strip()
                    if val.endswith('B'):
                        return float(val[:-1]) * 1e9
                    elif val.endswith('M'):
                        return float(val[:-1]) * 1e6
                    elif val.endswith('K'):
                        return float(val[:-1]) * 1e3
                    return float(val)
                except:
                    return None
        return None
    except Exception as e:
        print(f"Error getting book value for {ticker} from CSV: {e}")
        return None

def get_pe_pb_from_csv(ticker, csv_file_name):
    try:
        df = pd.read_csv(csv_file_name)
        row = df[df['Ticker'] == ticker]
        pe = row['Fwd P/E'].iloc[0] if 'Fwd P/E' in row else None
        pb = row['P/B'].iloc[0] if 'P/B' in row else None
        return pe, pb
    except Exception as e:
        print(f"Error getting P/E and P/B for {ticker} from CSV: {e}")
        return None, None

def get_shares_outstanding_from_csv(ticker, csv_file_name):
    try:
        df = pd.read_csv(csv_file_name)
        row = df[df['Ticker'] == ticker]
        shares = row['Shares Outstanding'].iloc[0] if 'Shares Outstanding' in row else None
        if shares is not None and shares != 'N/A':
            try:
                shares = str(shares).replace(',','').strip()
                if shares.endswith('B'):
                    return float(shares[:-1]) * 1e9
                elif shares.endswith('M'):
                    return float(shares[:-1]) * 1e6
                elif shares.endswith('K'):
                    return float(shares[:-1]) * 1e3
                return float(shares)
            except:
                return None
        return None
    except Exception as e:
        print(f"Error getting shares outstanding for {ticker} from CSV: {e}")
        return None

def get_book_value(ticker, csv_file_name=None):
    # Try Yahoo
    try:
        company = yf.Ticker(ticker)
        balance_sheet = company.balance_sheet
        if balance_sheet is not None and not balance_sheet.empty:
            balance_sheet = balance_sheet.iloc[:, :1]
            total_assets = None
            asset_names = ['Total Assets', 'totalAssets', 'TotalAssets', 'Total assets', 'Total Assets', 'TotalAssets']
            for asset_name in asset_names:
                if asset_name in balance_sheet.index:
                    total_assets = balance_sheet.loc[asset_name][0]
                    break
            total_liabilities = None
            liability_names = ['Total Liabilities Net Minority Interest', 'TotalLiabilities', 'Total Liabilities', 'totalLiabilities', 'Total liabilities', 'Total Liab', 'TotalLiab']
            for liability_name in liability_names:
                if liability_name in balance_sheet.index:
                    total_liabilities = balance_sheet.loc[liability_name][0]
                    break
            if total_assets is not None and total_liabilities is not None:
                return total_assets - total_liabilities
    except Exception as e:
        print(f"Error getting book value for {ticker} from Yahoo: {e}")
    # Try CSV
    if csv_file_name:
        val = get_book_value_from_csv(ticker, csv_file_name)
        if val is not None:
            # Heuristic: if book value is small, assume per share and try to multiply by shares outstanding
            if val < 10000:
                shares = get_shares_outstanding_from_csv(ticker, csv_file_name)
                if shares is not None:
                    print(f"[DEBUG] Book value per share for {ticker}: {val}, shares outstanding: {shares}")
                    return val * shares
                else:
                    print(f"[DEBUG] Book value per share for {ticker} but no shares outstanding found. Returning 'N/A'.")
                    return 'N/A'
            return val
    # Try Alpha Vantage
    if ALPHA_VANTAGE_API_KEY:
        try:
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={ALPHA_VANTAGE_API_KEY}"
            response = requests.get(url)
            data = response.json()
            if 'BookValue' in data and data['BookValue'] not in [None, 'None', 'N/A', '']:
                # Alpha Vantage BookValue is per share, so try to get shares outstanding
                if 'SharesOutstanding' in data and data['SharesOutstanding'] not in [None, 'None', 'N/A', '']:
                    return float(data['BookValue']) * float(data['SharesOutstanding'])
                else:
                    print(f"[DEBUG] Alpha Vantage BookValue per share for {ticker} but no shares outstanding found. Returning 'N/A'.")
                    return 'N/A'
        except Exception as e:
            print(f"Error getting book value for {ticker} from Alpha Vantage: {e}")
    return 'N/A'

def get_market_cap(ticker, csv_file_name=None):
    if "." in ticker:
        ticker = ticker.split(".")[0]
    # Try Yahoo Finance first
    try:
        company = yf.Ticker(ticker)
        info = company.info
        market_cap = None
        for key in ['marketCap', 'MarketCap', 'market_cap', 'Market Cap']:
            if key in info:
                market_cap = info[key]
                print(f"Found market cap using key: {key}")
                break
        if market_cap is not None:
            return market_cap
        print(f"Warning: Could not find market cap for {ticker} in Yahoo Finance.")
    except Exception as e:
        print(f"Error getting market cap for {ticker} from Yahoo Finance: {e}")
    # Fallback to CSV if provided
    if csv_file_name:
        try:
            df = pd.read_csv(csv_file_name)
            row = df[df['Ticker'] == ticker]
            if not row.empty:
                cap = row['Market Cap'].iloc[0]
                if isinstance(cap, str):
                    cap = cap.replace('$','').replace(',','')
                try:
                    cap = float(cap)
                except:
                    cap = None
                if cap:
                    print(f"Using market cap from CSV for {ticker}: {cap}")
                    return cap
        except Exception as e:
            print(f"Error getting market cap for {ticker} from CSV: {e}")
    return None

def get_net_value(ticker):
    try:
        book_value = get_book_value(ticker)
        if book_value is None:
            return None
            
        market_cap = get_market_cap(ticker)
        if market_cap is None:
            return None
            
        return book_value - market_cap
    except Exception as e:
        print(f"Error calculating net value for {ticker}: {e}")
        return None
    
def get_stock_numeric_rating(ticker, csv_file_name):
    try:
        # Look for the most recent StockRatings CSV file
        import glob
        import os
        from datetime import datetime
        
        # Get all StockRatings CSV files
        csv_files = glob.glob("StockRatings*.csv")
        
        if not csv_files:
            print(f"Warning: No StockRatings CSV files found. Skipping numeric rating.")
            return None
            
        # Sort files by date (newest first)
        csv_files.sort(reverse=True)
        latest_file = csv_files[0]
        print(f"Using ratings from: {latest_file}")
            
        # Read the CSV file into a DataFrame
        df = pd.read_csv(latest_file)
        
        # Find the row for the given ticker
        ticker_row = df[df['Ticker'] == ticker]
        
        if ticker_row.empty:
            print(f"Warning: No rating found for {ticker} in {latest_file}")
            return None
            
        # Get the rating from the 'Overall Rating' column
        rating = ticker_row['Overall Rating'].iloc[0]
        return rating
        
    except Exception as e:
        print(f"Error getting numeric rating for {ticker}: {e}")
        return None

#def get_stock_txt_rating(ten_k,ten_q):
def get_stock_txt_rating(company_name):    
    # Uses Embeddings + LLMs to ask ~20 questions to company's 10-Ks and 10-Qs and assess its overall health
    
    prompt = f"What is overall financial health of {company_name}?"
    
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": "sonar-small-online",
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": "Bearer " + PERPLEXITY_API
    }
    response = requests.post(url, json=payload, headers=headers)
    
    json_data = response.text
    parsed_json = json.loads(json_data)
    answer = parsed_json["choices"][0]["message"]["content"]
    return answer

################################################################################################
# Full Step 5: Estimate a chance for a stock to fix the problem 
################################################################################################

# using monte carlo simulation and bayes rule
#   based on the stock fundamentals
#   reasons why stock fell
#   company's unique advantages
#   company's health compared to competitotrs
#   general market trends

# General idea: 
# 1. Probability of recovering stock price due to health of fundamentals (0-1) 
# p(H) = probability to recover stock price from bad news (general case)
# p(E) = probability of a company having an E financial health (health is the value from 0 to 1)
# P(E|H) = probability of a company to have an E financial health after recovering stock price from bad news
# General formula :
###       P(H|E) = ( P(E|H) * P(H) ) / P(E)
#
# 2. Probability of recovering stock price due to how bad are the news 
# 3. average?

# NOT USED NOT USED
'''
def chance_to_recover(company_name,ticker):
    
    why_fell = why_stock_fell(ticker)
        
    stock_n_rating = get_stock_numeric_rating(ticker, "StockRatings.csv")
    print(f"{company_name} Overall Financial score: {stock_n_rating}")
    
    stock_txt_rating = get_stock_txt_rating(company_name)
    print(f"{company_name} Overall Financial health: {stock_txt_rating}")
    
    prompt = f"""You are the greatest and most competent financial analyst that can understand and predict company's future.
        Read this context about the company:\n
        Reason {company_name} stock fell last 24 hours: {why_fell}.\n
        {company_name} overall description: {stock_txt_rating}\n
        {company_name} overall financial rating from world class analytical experts: {stock_n_rating} out of 100.\n
        Question: What is the chance of a company to recover its stock price based on the reason the stock fell, company description, company financial health?
        Answer from a financial expert:
        """
    
    result = llm_call(prompt)
    print(f"{company_name} chances to recover stock price: {result}")
    
    return result
'''
################################################################################################
# Full Step 6: Calculate end value of a company
################################################################################################

def get_top_stocks_by_rating(csv_file, num_stocks=50):
    """Get top stocks by rating from the CSV file"""
    try:
        df = pd.read_csv(csv_file)
        # Sort by Overall Rating in descending order
        df = df.sort_values('Overall Rating', ascending=False)
        return df.head(num_stocks)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return None

def analyze_index(ticker):
    """Analyze a market index"""
    try:
        index = yf.Ticker(ticker)
        info = index.info
        
        # Get current price and daily change
        current_price = info.get('regularMarketPrice', 0)
        prev_close = info.get('regularMarketPreviousClose', 0)
        daily_change = ((current_price - prev_close) / prev_close) * 100
        
        # Get 52-week high/low
        year_high = info.get('fiftyTwoWeekHigh', 0)
        year_low = info.get('fiftyTwoWeekLow', 0)
        
        return {
            'price': current_price,
            'daily_change': daily_change,
            'year_high': year_high,
            'year_low': year_low
        }
    except Exception as e:
        print(f"Error analyzing index {ticker}: {e}")
        return None

def get_yahoo_news_headlines(ticker, num_results=3):
    try:
        url = f'https://finance.yahoo.com/quote/{ticker}'
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(resp.text, 'html.parser')
        headlines = []
        for a in soup.select('h3 a, h2 a'):
            title = a.get_text(strip=True)
            link = a['href']
            if not link.startswith('http'):
                link = 'https://finance.yahoo.com' + link
            headlines.append({'title': title, 'link': link})
            if len(headlines) >= num_results:
                break
        return headlines if headlines else [{'title': 'No recent news found (Yahoo fallback).', 'link': ''}]
    except Exception as e:
        print(f"Error scraping Yahoo news for {ticker}: {e}")
        return [{'title': 'No recent news found (Yahoo fallback).', 'link': ''}]

def get_news_articles(company_name, num_results=5, ticker=None):
    # Try Google PSE
    if not GOOGLE_PSE_ENGINE_ID or not GOOGLE_PSE_API_KEY:
        print("Google PSE API keys not found.")
        return get_yahoo_news_headlines(ticker or company_name)
    query = f"{company_name} stock news"
    url = (
        f"https://www.googleapis.com/customsearch/v1?q={query}"
        f"&cx={GOOGLE_PSE_ENGINE_ID}&key={GOOGLE_PSE_API_KEY}&num={num_results}&gl=us&hl=en"
    )
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        articles = []
        for item in data.get('items', [])[:num_results]:
            title = item.get('title', 'No Title')
            link = item.get('link', '')
            articles.append({'title': title, 'link': link})
        if not articles:
            return get_yahoo_news_headlines(ticker or company_name)
        return articles
    except Exception as e:
        print(f"Error fetching news articles: {e}")
        return get_yahoo_news_headlines(ticker or company_name)

# Analyst price targets (bearish, neutral, bullish)
def get_analyst_targets_from_yahoo(ticker):
    try:
        url = f'https://finance.yahoo.com/quote/{ticker}/analysis'
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Yahoo's analyst price targets are on the /quote/{ticker} page, not /analysis
        url_main = f'https://finance.yahoo.com/quote/{ticker}'
        resp_main = requests.get(url_main, headers={'User-Agent': 'Mozilla/5.0'})
        soup_main = BeautifulSoup(resp_main.text, 'html.parser')
        # Look for price target table
        table = soup_main.find('section', {'data-test': 'qsp-analyst'})
        if not table:
            # Try to find by text
            for span in soup_main.find_all('span'):
                if '1y Target Est' in span.text:
                    try:
                        mean = span.find_next('td').text.strip()
                        return {'bearish': 'N/A', 'neutral': mean, 'bullish': 'N/A', 'note': 'Scraped from Yahoo Finance web page.'}
                    except:
                        continue
            return {'bearish': 'N/A', 'neutral': 'N/A', 'bullish': 'N/A', 'note': 'Could not scrape analyst targets from Yahoo.'}
        # Try to extract low, mean, high from the table
        rows = table.find_all('tr')
        low = mean = high = 'N/A'
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 2:
                label = cells[0].text.lower()
                value = cells[1].text.strip()
                if 'low' in label:
                    low = value
                elif 'average' in label or 'mean' in label:
                    mean = value
                elif 'high' in label:
                    high = value
        return {'bearish': low, 'neutral': mean, 'bullish': high, 'note': 'Scraped from Yahoo Finance web page.'}
    except Exception as e:
        print(f"Error scraping analyst targets for {ticker} from Yahoo: {e}")
        return {'bearish': 'N/A', 'neutral': 'N/A', 'bullish': 'N/A', 'note': 'Could not scrape analyst targets from Yahoo.'}

def get_analyst_price_targets(ticker):
    try:
        company = yf.Ticker(ticker)
        rec = company.recommendations
        if rec is not None and not rec.empty:
            info = company.info
            bearish = info.get('targetLowPrice', 'N/A')
            neutral = info.get('targetMeanPrice', 'N/A')
            bullish = info.get('targetHighPrice', 'N/A')
            if all(x in [None, 'N/A', ''] for x in [bearish, neutral, bullish]):
                # Fallback to scraping
                return get_analyst_targets_from_yahoo(ticker)
            return {
                'bearish': bearish if bearish is not None else 'N/A',
                'neutral': neutral if neutral is not None else 'N/A',
                'bullish': bullish if bullish is not None else 'N/A'
            }
        else:
            # Fallback to scraping
            return get_analyst_targets_from_yahoo(ticker)
    except Exception as e:
        print(f"Error fetching analyst price targets for {ticker}: {e}")
        return get_analyst_targets_from_yahoo(ticker)

def main():
    print("\n=== InvestorGPT: Stock Recovery Analysis ===\n")
    
    # First, analyze major indices
    print("Market Indices Analysis:")
    print("=" * 80)
    
    indices = {
        '^GSPC': 'S&P 500',
        '^IXIC': 'NASDAQ',
        '^DJI': 'Dow Jones'
    }
    
    for ticker, name in indices.items():
        analysis = analyze_index(ticker)
        if analysis:
            print(f"\n{name} ({ticker}):")
            print(f"Current Price: ${analysis['price']:,.2f}")
            print(f"Daily Change: {analysis['daily_change']:+.2f}%")
            print(f"52-Week Range: ${analysis['year_low']:,.2f} - ${analysis['year_high']:,.2f}")
    
    print("\n" + "="*80 + "\n")
    
    # Get the most recent StockRatings CSV file
    csv_files = glob.glob("StockRatings*.csv")
    if not csv_files:
        print("No StockRatings CSV files found.")
        return
        
    csv_files.sort(reverse=True)
    latest_file = csv_files[0]
    print(f"Analyzing stocks from: {latest_file}\n")
    
    # Get top 50 stocks by rating
    top_stocks = get_top_stocks_by_rating(latest_file, 50)
    if top_stocks is None:
        return
    
    # List of specific stocks to include
    specific_stocks = ['AMD', 'NVDA', 'QCOM', 'NOC', 'LMT', 'INTC', 'AMZN', 'META', 'GOOGL']
    
    # Create a set of all stocks to analyze
    stocks_to_analyze = set(top_stocks['Ticker'].tolist() + specific_stocks)
    
    print(f"Analyzing {len(stocks_to_analyze)} stocks...\n")
    
    for ticker in stocks_to_analyze:
        try:
            # Get company name
            company_name = get_company_name(ticker)
            
            # Get numeric rating
            rating = get_stock_numeric_rating(ticker, latest_file)
            
            # Get book value and market cap
            book_value = get_book_value(ticker)
            market_cap = get_market_cap(ticker)
            
            # Calculate net value if possible
            net_value = None
            if book_value is not None and market_cap is not None:
                net_value = book_value - market_cap
            
            # Get why the stock fell
            why_fell = why_stock_fell(company_name)
            
            # Print analysis in a clean format
            print(f"\n{'='*80}")
            print(f"Company: {company_name} ({ticker})")
            
            if rating is not None:
                print(f"Overall Financial Health Rating: {rating}/100")
            
            if net_value is not None:
                print(f"Net Value (Book - MarketCap): ${net_value:,.2f}")
            
            print("\nRecent News & Analysis:")
            print("-" * 40)
            print(why_fell)
            
            print("\nRecovery Potential Assessment:")
            print("-" * 40)
            if rating is not None:
                if rating >= 80:
                    print("High recovery potential based on strong financial health")
                elif rating >= 60:
                    print("Moderate recovery potential with solid fundamentals")
                else:
                    print("Lower recovery potential due to weaker financial metrics")
            
            if net_value is not None:
                if net_value > 0:
                    print("Positive net value suggests potential undervaluation")
                else:
                    print("Negative net value indicates potential overvaluation")
            
            print(f"{'='*80}\n")
            
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
            continue
    
    print("\nAnalysis complete. Use this information as part of your investment research.")
    print("Remember: Past performance is not indicative of future results.")

if __name__ == "__main__":
    main()
