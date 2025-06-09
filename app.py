from flask import Flask, render_template, jsonify
from datetime import datetime
import pandas as pd
import glob
import os
from stock_data_loader import load_and_save
from InvestorGPT import get_stock_numeric_rating, get_book_value, why_stock_fell

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
    """Get detailed analysis for a specific stock."""
    try:
        latest_file = get_latest_csv_file()
        if not latest_file:
            return jsonify({'status': 'error', 'message': 'No stock data available'})
        # Pass the latest CSV file to get_stock_numeric_rating
        rating = get_stock_numeric_rating(ticker, latest_file)
        book_value = get_book_value(ticker)
        why_fell = why_stock_fell(ticker)
        if rating >= 80:
            recovery_potential = "High - Strong financial health indicators"
        elif rating >= 60:
            recovery_potential = "Moderate - Good financial health with some concerns"
        else:
            recovery_potential = "Low - Significant financial health concerns"
        if book_value and book_value > 0:
            valuation_status = "Potentially Undervalued"
        else:
            valuation_status = "Valuation Unclear"
        df = pd.read_csv(latest_file)
        company_name = df[df['Ticker'] == ticker]['Company'].iloc[0] if ticker in df['Ticker'].values else ticker
        return jsonify({
            'status': 'success',
            'data': {
                'company_name': company_name,
                'rating': rating,
                'net_value': book_value,
                'recovery_potential': recovery_potential,
                'valuation_status': valuation_status,
                'why_fell': why_fell
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
