import streamlit as st
import yfinance as yf
import pandas as pd

# ページの設定
st.set_page_config(page_title="企業価値計算アプリ", layout="wide")

st.title("📊 企業価値計算アプリ (DCF法)")
st.markdown("ご提示の数式 $\sum \\frac{CF_t}{(1+r)^t}$ に基づき、理論株価を試算します。")

# --- キャッシュ機能付きデータ取得関数 ---
# この関数を使うことで、同じ銘柄なら何度もYahooにアクセスせず、
# メモリに保存されたデータを使うようになります（アクセス制限対策）
@st.cache_data(ttl=86400) # 24時間(86400秒)キャッシュを保持
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    
    # データの存在確認のためにinfoを取得
    # yfinanceはinfo取得時に通信が発生するため、ここでエラーチェック
    try:
        _ = stock.info
    except Exception:
        return None, None, None, "銘柄が見つからないか、通信エラーが発生しました。"

    # 直近の株価取得
    history = stock.history(period="5d") # 念のため5日分とって最新を使う
    if history.empty:
        return None, None, None, "株価データが取得できませんでした。"
    current_price = history['Close'].iloc[-1]
    
    # 発行済株式数
    shares_outstanding = stock.info.get('sharesOutstanding')
    if not shares_outstanding:
        return None, None, None, "発行済株式数のデータがありません。"

    # 財務データ（キャッシュフロー）
    cash_flow = stock.cashflow
    if cash_flow.empty:
        return None, None, None, "財務データが取得できませんでした。"

    # FCFの取得
    try:
        if 'Free Cash Flow' in cash_flow.index:
            latest_fcf = cash_flow.loc['Free Cash Flow'].iloc[0]
        else:
            op_cf = cash_flow.loc['Operating Cash Flow'].iloc[0]
            inv_cf = cash_flow.loc['Investing Cash Flow'].iloc[0] 
            latest_fcf = op_cf + inv_cf
    except Exception as e:
        return None, None, None, f"FCFの計算に失敗しました: {e}"
        
    return current_price, shares_outstanding, latest_fcf, None

# --- サイドバー：入力パラメータ ---
st.sidebar.header("パラメータ設定")

ticker_input = st.sidebar.text_input("銘柄コード (例: 7203.T, AAPL)", value="7203.T")
discount_rate = st.sidebar.slider("割引率 (r)", 0.01, 0.20, 0.08, 0.01, help="期待収益率。通常7%〜10%")
growth_rate = st.sidebar.slider("今後5年の成長率予測", -0.10, 0.20, 0.03, 0.01)
terminal_growth = st.sidebar.number_input("永久成長率", value=0.01, step=0.01)

# 計算ボタン
if st.sidebar.button("計算実行"):
    with st.spinner('データを取得・計算中...'):
        
        # 関数呼び出し（キャッシュが効く）
        current_price, shares_outstanding, latest_fcf, error_msg = get_stock_data(ticker_input)
        
        if error_msg:
            st.error(error_msg)
            st.warning("Yahoo Financeへのアクセスが制限されている可能性があります。時間を置いて再度お試しください。")
        else:
            # --- ここから計算ロジック（データ取得なし） ---
            projection_years = 5
            future_fcfs = []
            pv_fcfs = [] 
            current_fcf_val = latest_fcf
            
            df_process = pd.DataFrame(columns=["年数", "予測FCF", "現在価値(PV)"])

            for t in range(1, projection_years + 1):
                pred_fcf = current_fcf_val * (1 + growth_rate)
                disc_factor = (1 + discount_rate) ** t
                pv = pred_fcf / disc_factor
                
                future_fcfs.append(pred_fcf)
                pv_fcfs.append(pv)
                current_fcf_val = pred_fcf

                new_row = pd.DataFrame({
                    "年数": [f"{t}年後"],
                    "予測FCF": [pred_fcf],
                    "現在価値(PV)": [pv]
                })
                df_process = pd.concat([df_process, new_row], ignore_index=True)

            if discount_rate <= terminal_growth:
                 st.error("割引率は永久成長率より高く設定する必要があります。")
            else:
                terminal_value = (future_fcfs[-1] * (1 + terminal_growth)) / (discount_rate - terminal_growth)
                pv_terminal_value = terminal_value / ((1 + discount_rate) ** projection_years)
                enterprise_value = sum(pv_fcfs) + pv_terminal_value
                intrinsic_value = enterprise_value / shares_outstanding

                # --- 結果表示 ---
                st.success("計算完了！")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("現在の株価", f"{current_price:,.0f} 円" if ".T" in ticker_input else f"${current_price:,.2f}")
                with col2:
                    st.metric("理論株価", 
                            f"{intrinsic_value:,.0f} 円" if ".T" in ticker_input else f"${intrinsic_value:,.2f}",
                            delta=f"{((intrinsic_value - current_price)/current_price)*100:.1f}%")
                
                st.subheader("詳細")
                st.dataframe(df_process.style.format("{:,.0f}"))
                st.write(f"ターミナルバリュー現在価値: {pv_terminal_value:,.0f}")
