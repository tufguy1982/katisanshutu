import streamlit as st
import yfinance as yf
import pandas as pd

# ページ設定
st.set_page_config(page_title="企業価値計算アプリ", layout="wide")

st.title("📊 企業価値計算アプリ (DCF法)")
st.markdown(r"ご提示の数式 $\sum \frac{CF_t}{(1+r)^t}$ に基づき、理論株価を試算します。")

# --- データ取得関数 ---
@st.cache_data(ttl=3600)
def get_stock_data_safe(ticker):
    """
    Yahoo Financeからデータを取得するが、失敗した場合はNoneを返す安全設計
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. 接続テスト (info取得)
        # タイムアウトを短めに設定して無限待機を防ぐ工夫などはyfinanceの仕様上難しいが、
        # ここで例外が出れば即手動モードへ移行させる
        info = stock.info
        if not info:
            return None, None, None, "基本情報の取得に失敗"

        # 2. 株価
        history = stock.history(period="5d")
        if history.empty:
            return None, None, None, "株価データの取得に失敗"
        current_price = history['Close'].iloc[-1]
        
        # 3. 株式数
        shares_outstanding = info.get('sharesOutstanding')
        if not shares_outstanding:
            return None, None, None, "発行済株式数の取得に失敗"

        # 4. FCF
        cash_flow = stock.cashflow
        if cash_flow.empty:
            return None, None, None, "キャッシュフロー計算書の取得に失敗"

        if 'Free Cash Flow' in cash_flow.index:
            latest_fcf = cash_flow.loc['Free Cash Flow'].iloc[0]
        else:
            op_cf = cash_flow.loc['Operating Cash Flow'].iloc[0]
            inv_cf = cash_flow.loc['Investing Cash Flow'].iloc[0]
            latest_fcf = op_cf + inv_cf
            
        return current_price, shares_outstanding, latest_fcf, None

    except Exception as e:
        # エラー内容を返す
        return None, None, None, str(e)


# --- サイドバー設定 ---
st.sidebar.header("Step 1: データの入力")

input_method = st.sidebar.radio(
    "データ入力方法",
    ("自動取得 (Yahoo Finance)", "手動入力 (エラー回避用)"),
    index=0
)

# 変数の初期化
current_price = 0.0
shares_outstanding = 0.0
latest_fcf = 0.0
data_fetched = False
ticker_display = "Manual Input"

if input_method == "自動取得 (Yahoo Finance)":
    ticker_input = st.sidebar.text_input("銘柄コード (例: 7203.T, AAPL)", value="7203.T")
    fetch_btn = st.sidebar.button("データを取得")
    
    if fetch_btn:
        with st.spinner('Yahoo Financeにアクセス中...'):
            p, s, f, err = get_stock_data_safe(ticker_input)
            if err:
                st.error(f"データ取得エラー: {err}")
                st.warning("⚠️ Yahoo Financeのアクセス制限により自動取得できませんでした。「手動入力」タブに切り替えて数値を入力してください。")
            else:
                st.session_state['fetched_price'] = p
                st.session_state['fetched_shares'] = s
                st.session_state['fetched_fcf'] = f
                st.session_state['ticker'] = ticker_input
                st.success("データ取得成功！")

    # 取得済みデータがあればそれを使用
    if 'fetched_price' in st.session_state:
        current_price = st.session_state['fetched_price']
        shares_outstanding = st.session_state['fetched_shares']
        latest_fcf = st.session_state['fetched_fcf']
        ticker_display = st.session_state.get('ticker', ticker_input)
        data_fetched = True

else: # 手動入力モード
    st.sidebar.markdown("---")
    st.sidebar.info("決算短信などを見て数値を入力してください")
    ticker_display = st.sidebar.text_input("銘柄名（表示用）", value="My Stock")
    current_price = st.sidebar.number_input("現在の株価", value=1000.0)
    shares_outstanding = st.sidebar.number_input("発行済株式数", value=100000000.0, step=100000.0, format="%.0f")
    latest_fcf = st.sidebar.number_input("直近のフリーキャッシュフロー(FCF)", value=5000000000.0, step=1000000.0, format="%.0f")
    data_fetched = True

st.sidebar.markdown("---")
st.sidebar.header("Step 2: 評価パラメータ")
discount_rate = st.sidebar.slider("割引率 (r)", 0.01, 0.20, 0.08, 0.01)
growth_rate = st.sidebar.slider("今後5年の成長率予測", -0.10, 0.20, 0.03, 0.01)
terminal_growth = st.sidebar.number_input("永久成長率", value=0.01, step=0.01)

# --- 計算実行 ---
if st.button("計算実行 (Intrinsic Value)"):
    if not data_fetched and input_method == "自動取得 (Yahoo Finance)":
        st.error("先に「データを取得」ボタンを押してください。")
    elif shares_outstanding == 0:
        st.error("発行済株式数が0です。")
    else:
        # DCF計算
        projection_years = 5
        future_fcfs = []
        pv_fcfs = []
        current_fcf_val = latest_fcf
        
        # エラー回避のためデータフレーム用のリストを作成
        rows = []

        for t in range(1, projection_years + 1):
            pred_fcf = current_fcf_val * (1 + growth_rate)
            disc_factor = (1 + discount_rate) ** t
            pv = pred_fcf / disc_factor
            
            future_fcfs.append(pred_fcf)
            pv_fcfs.append(pv)
            current_fcf_val = pred_fcf

            rows.append({
                "年数": f"{t}年後",
                "予測FCF": pred_fcf,
                "現在価値(PV)": pv
            })

        # データフレーム作成（stylerを使わずシンプルに表示する形に変更してエラー回避）
        df_process = pd.DataFrame(rows)

        if discount_rate <= terminal_growth:
             st.error("割引率は永久成長率より高く設定する必要があります。")
        else:
            terminal_value = (future_fcfs[-1] * (1 + terminal_growth)) / (discount_rate - terminal_growth)
            pv_terminal_value = terminal_value / ((1 + discount_rate) ** projection_years)
            
            enterprise_value = sum(pv_fcfs) + pv_terminal_value
            intrinsic_value = enterprise_value / shares_outstanding

            # --- 結果表示 ---
            st.divider()
            st.subheader(f"分析結果: {ticker_display}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("現在の株価", f"{current_price:,.0f}")
            with col2:
                diff = intrinsic_value - current_price
                diff_pct = (diff / current_price) * 100
                st.metric(
                    "理論株価 (Intrinsic Value)", 
                    f"{intrinsic_value:,.0f}",
                    delta=f"{diff_pct:.1f}%"
                )

            st.write("---")
            st.write("#### 計算詳細")
            # 2枚目のエラー原因だった style.format をやめて、シンプルな表示にする
            st.table(df_process) 
            
            st.write(f"**+ ターミナルバリューの現在価値:** {pv_terminal_value:,.0f}")
            st.write(f"**= 企業価値合計:** {enterprise_value:,.0f}")
            st.write(f"**÷ 発行済株式数:** {shares_outstanding:,.0f}")
