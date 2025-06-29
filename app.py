from flask import Flask, render_template, jsonify
from datetime import datetime
import pandas as pd
import glob
import os
from stock_data_loader import load_and_save
from InvestorGPT import get_stock_numeric_rating, get_book_value, get_market_cap, get_news_articles, get_analyst_price_targets, why_stock_fell, get_pe_pb_from_csv
import logging
import yfinance as yf

app = Flask(__name__)

def get_latest_csv_file():
    files = glob.glob("StockRatings*.csv")
    if not files:
        return None
    latest_file = max(files, key=os.path.getctime)
    return latest_file

def get_latest_csv_date():
    latest_file = get_latest_csv_file()
    if not latest_file:
        return None
    # Extract MM.DD.YY from filename
    import re
    match = re.search(r'StockRatings-(\d{2}\.\d{2}\.\d{2})', latest_file)
    if match:
        date_str = match.group(1)
        # Convert to MM-DD-YYYY
        mm, dd, yy = date_str.split('.')
        yyyy = '20' + yy
        return f"{mm}-{dd}-{yyyy}"
    return None

@app.route('/')
def index():
    """Render the main page with current date and last fetch date."""
    current_date = datetime.now().strftime('%m-%d-%Y')
    last_fetch_date = get_latest_csv_date()
    return render_template('index.html', 
                         current_date=current_date,
                         last_fetch_date=last_fetch_date)

@app.route('/run_analysis')
def run_analysis():
    """Run the stock analysis and generate a new CSV file."""
    try:
        load_and_save()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/get_stocks')
def get_stocks():
    """Get the list of stocks from the most recent CSV file."""
    try:
        files = glob.glob("StockRatings*.csv")
        if not files:
            return jsonify({'status': 'error', 'message': 'No stock data available'})
        
        latest_file = max(files, key=os.path.getctime)
        df = pd.read_csv(latest_file)

        # Full master column order as provided by the user
        master_columns = [
            'Ticker','Company','Market Cap','Overall Rating','Sector','Industry','Country','Valuation Grade','Profitability Grade','Growth Grade','Performance Grade','Fwd P/E','PEG','P/S','P/B','P/C','P/FCF','Dividend','Payout Ratio','EPS this Y','EPS next Y','EPS past 5Y','EPS next 5Y','Sales past 5Y','EPS Q/Q','Sales Q/Q','Insider Own','Insider Trans','Inst Own','Inst Trans','Short Ratio','ROA','ROE','ROI','Curr R','Quick R','LTDebt/Eq','Debt/Eq','Gross M','Oper M','Profit M','Perf Month','Perf Quart','Perf Half','Perf Year','Perf YTD','Volatility M','SMA20','SMA50','SMA200','52W High','52W Low','RSI','Earnings','Price','Target Price','Percent Diff'
        ]
        # Add missing columns as N/A
        for col in master_columns:
            if col not in df.columns:
                df[col] = 'N/A'
        # Reorder columns
        df = df[master_columns]
        # Convert all NaN to 'N/A' for valid JSON
        data = df.where(pd.notnull(df), 'N/A').to_dict('records')
        return jsonify({'status': 'success', 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/analyze_stock/<ticker>')
def analyze_stock(ticker):
    try:
        latest_file = get_latest_csv_file()
        df = pd.read_csv(latest_file) if latest_file else pd.DataFrame()
        row = df[df['Ticker'] == ticker]
        # Spreadsheet fields
        price = row['Price'].iloc[0] if not row.empty and 'Price' in row else None
        market_cap = row['Market Cap'].iloc[0] if not row.empty and 'Market Cap' in row else None
        pe_ratio = row['Fwd P/E'].iloc[0] if not row.empty and 'Fwd P/E' in row else None
        target_est = row['Target Price'].iloc[0] if not row.empty and 'Target Price' in row else None
        eps = row['EPS this Y'].iloc[0] if not row.empty and 'EPS this Y' in row else None
        range_52w = f"{row['52W Low'].iloc[0]} - {row['52W High'].iloc[0]}" if not row.empty and '52W Low' in row and '52W High' in row else None
        sector = row['Sector'].iloc[0] if not row.empty and 'Sector' in row else None
        industry = row['Industry'].iloc[0] if not row.empty and 'Industry' in row else None
        employees = row['Employees'].iloc[0] if not row.empty and 'Employees' in row else None
        fiscal_year = row['Fiscal Year'].iloc[0] if not row.empty and 'Fiscal Year' in row else None
        company_description = None
        # Try yfinance for richer info
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info
            if not price: price = info.get('regularMarketPrice')
            if not market_cap: market_cap = info.get('marketCap')
            if not pe_ratio: pe_ratio = info.get('trailingPE')
            if not target_est: target_est = info.get('targetMeanPrice')
            if not eps: eps = info.get('trailingEps')
            if not sector: sector = info.get('sector')
            if not industry: industry = info.get('industry')
            if not employees: employees = info.get('fullTimeEmployees')
            if not company_description: company_description = info.get('longBusinessSummary')
            if not range_52w:
                low = info.get('fiftyTwoWeekLow')
                high = info.get('fiftyTwoWeekHigh')
                if low and high:
                    range_52w = f"{low} - {high}"
        except Exception as e:
            print(f"[DEBUG] yfinance error: {e}")
        # News
        news_articles = get_news_articles(info.get('longName', ticker) if 'info' in locals() and info else ticker, num_results=5, ticker=ticker)
        # Analyst targets
        analyst_targets = get_analyst_price_targets(ticker)
        # Performance (placeholder, you can add real logic)
        perf_ytd = row['Perf YTD'].iloc[0] if not row.empty and 'Perf YTD' in row else None
        perf_1y = row['Perf Year'].iloc[0] if not row.empty and 'Perf Year' in row else None
        perf_3y = None
        perf_5y = None
        # AI summary and prediction (placeholder logic)
        ai_summary = f"Our AI expects {ticker} to perform in line with its sector based on current fundamentals and news."
        prediction = "Neutral"
        # Always return all fields
        return jsonify({
            'status': 'success',
            'data': {
                'prediction': prediction,
                'ai_summary': ai_summary,
                'price': price or 'N/A',
                'market_cap': market_cap or 'N/A',
                'pe_ratio': pe_ratio or 'N/A',
                'target_est': target_est or 'N/A',
                'eps': eps or 'N/A',
                'range_52w': range_52w or 'N/A',
                'company_description': company_description or 'No description available.',
                'sector': sector or 'N/A',
                'industry': industry or 'N/A',
                'employees': employees or 'N/A',
                'fiscal_year': fiscal_year or 'N/A',
                'news_articles': news_articles or [],
                'perf_ytd': perf_ytd or 'N/A',
                'perf_1y': perf_1y or 'N/A',
                'perf_3y': perf_3y or 'N/A',
                'perf_5y': perf_5y or 'N/A',
                'analyst_targets': analyst_targets or {'bearish': 'N/A', 'neutral': 'N/A', 'bullish': 'N/A', 'note': 'No data.'}
            }
        })
    except Exception as e:
        print(f"[DEBUG] analyze_stock error: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
