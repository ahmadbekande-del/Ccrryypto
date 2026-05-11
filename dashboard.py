# dashboard.py
import streamlit as st
import pandas as pd
from scanner import KuCoinSuperScanner
from datetime import datetime

st.set_page_config(page_title="Crypto AI Scanner", layout="wide")
st.title("🔥 KuCoin AI Scanner - Live Dashboard 🔥")

if st.button("🔄 Run Analysis Now"):
    with st.spinner("Scanning 150+ coins..."):
        scanner = KuCoinSuperScanner()
        results = scanner.scan_all(limit=150)
        st.session_state['results'] = results
        st.success(f"Completed! {len(results)} coins analyzed.")

if 'results' in st.session_state:
    results = st.session_state['results']
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Coins", len(results))
    col2.metric("Strong Buy", sum(1 for r in results if r['final_signal'] == 'STRONG_BUY'))
    col3.metric("Strong Sell", sum(1 for r in results if r['final_signal'] == 'STRONG_SELL'))
    
    data = []
    for r in results:
        data.append({
            "Symbol": r['symbol'],
            "Signal": r['final_signal'],
            "Score": r['final_score'],
            "Price": round(r.get('price', 0), 4),
            "RSI (1h)": r['timeframes'].get('1h', {}).get('RSI', '-'),
            "Trend 1h": r['timeframes'].get('1h', {}).get('Trend', '-')
        })
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
    st.bar_chart(df.set_index('Symbol')['Score'])
else:
    st.info("Press the button above to start analysis.")
