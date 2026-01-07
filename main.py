import streamlit as st
import yfinance as yf
import pandas as pd

# ページの設定
st.set_page_config(page_title="企業価値計算アプリ", layout="wide")

st.title("📊 企業価値計算アプリ (DCF法)")
st.markdown("ご提示の数式 $\sum \\frac{CF_t}{(1+r)^t}$ に基づき、理論株価を試算します。")

# --- サイドバー：入力パラメータ ---
st.sidebar.header("パラメータ設定")

# 1. 銘柄コード入力
ticker_input = st.sidebar.text_input("銘柄コード (例: 7203.T, AAPL)", value="7203.T")

# 2. 割引率 (r)
discount_rate = st.sidebar.slider("割引率 (r)", 0.01, 0.20, 0.08, 0.01, help="期待収益率やWACC。通常7%〜10%程度")

# 3. 成長率 (Growth Rate)
growth_rate = st.sidebar.slider("今後5年の成長率予測", -0.10, 0.20, 0.03, 0.01, help="FCFが毎年どれくらい伸びるか")

# 4. 永久成長率 (Terminal Growth)
terminal_growth = st.sidebar.number_input("永久成長率 (5年後以降)", value=0.01, step=0.01, help="インフレ率相当。通常0%〜2%")

# 計算ボタン
if st.sidebar.button("計算実行"):
    with st.spinner('データを取得・計算中...'):
        try:
            # データ取得
            stock = yf.Ticker(ticker_input)
            
            # 直近の株価取得
            history = stock.history(period="1d")
            if history.empty:
                st.error("株価データが取得できませんでした。コードを確認してください。")
                st.stop()
            current_price = history['Close'].iloc[-1]
            
            # 発行済株式数
            shares_outstanding = stock.info.get('sharesOutstanding')
            if not shares_outstanding:
                st.error("発行済株式数のデータがありません。")
                st.stop()

            # 財務データ（キャッシュフロー）
            cash_flow = stock.cashflow
            if cash_flow.empty:
                st.error("財務データが取得できませんでした。")
                st.stop()

            # FCFの取得（簡易ロジック）
            try:
                # Yahoo Financeの項目名は変動するため、複数のパターンを試行
                if 'Free Cash Flow' in cash_flow.index:
                    latest_fcf = cash_flow.loc['Free Cash Flow'].iloc[0]
                else:
                    # 簡易計算: 営業CF + 投資CF
                    op_cf = cash_flow.loc['Operating Cash Flow'].iloc[0]
                    inv_cf = cash_flow.loc['Investing Cash Flow'].iloc[0] 
                    latest_fcf = op_cf + inv_cf
            except Exception as e:
                st.error(f"FCFの計算に失敗しました: {e}")
                st.stop()

            # --- DCF計算ロジック ---
            projection_years = 5
            future_fcfs = []
            discount_factors = []
            pv_fcfs = [] # 現在価値

            current_fcf_val = latest_fcf
            
            # デバッグ用データの作成
            df_process = pd.DataFrame(columns=["年数", "予測FCF", "割引係数", "現在価値(PV)"])

            for t in range(1, projection_years + 1):
                # FCF予測
                pred_fcf = current_fcf_val * (1 + growth_rate)
                # 割引
                disc_factor = (1 + discount_rate) ** t
                pv = pred_fcf / disc_factor
                
                future_fcfs.append(pred_fcf)
                pv_fcfs.append(pv)
                
                # 次年度のために更新
                current_fcf_val = pred_fcf

                # 表に追加
                new_row = pd.DataFrame({
                    "年数": [f"{t}年後"],
                    "予測FCF": [pred_fcf],
                    "割引係数": [f"1 / (1+{discount_rate})^ {t}"],
                    "現在価値(PV)": [pv]
                })
                df_process = pd.concat([df_process, new_row], ignore_index=True)

            # ターミナルバリュー（永続価値）
            last_fcf = future_fcfs[-1]
            # TV = (5年目のFCF * (1+永久成長率)) / (割引率 - 永久成長率)
            if discount_rate <= terminal_growth:
                 st.error("割引率は永久成長率より高く設定する必要があります。")
                 st.stop()
                 
            terminal_value = (last_fcf * (1 + terminal_growth)) / (discount_rate - terminal_growth)
            pv_terminal_value = terminal_value / ((1 + discount_rate) ** projection_years)

            # 合計企業価値
            enterprise_value = sum(pv_fcfs) + pv_terminal_value
            
            # 理論株価
            intrinsic_value = enterprise_value / shares_outstanding

            # --- 結果表示 ---
            st.success("計算完了！")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("現在の株価", f"{current_price:,.0f} 円" if ".T" in ticker_input else f"${current_price:,.2f}")
            with col2:
                delta_color = "normal"
                if intrinsic_value > current_price:
                    delta_color = "normal" # 緑色にしたければoffにするなど調整可
                
                st.metric("理論株価 (Intrinsic Value)", 
                          f"{intrinsic_value:,.0f} 円" if ".T" in ticker_input else f"${intrinsic_value:,.2f}",
                          delta=f"{((intrinsic_value - current_price)/current_price)*100:.1f}% (割安度)" if intrinsic_value > current_price else f"{((intrinsic_value - current_price)/current_price)*100:.1f}% (割高)",
                          delta_color="inverse" if intrinsic_value < current_price else "normal"
                          )
            with col3:
                st.info(f"使用した直近FCF: {latest_fcf:,.0f}")

            st.markdown("---")
            st.subheader("計算プロセスの詳細")
            
            # 数値フォーマットを整えて表示
            st.dataframe(df_process.style.format({"予測FCF": "{:,.0f}", "現在価値(PV)": "{:,.0f}"}))
            
            st.write(f"**+ ターミナルバリューの現在価値:** {pv_terminal_value:,.0f}")
            st.write(f"**= 合計企業価値:** {enterprise_value:,.0f}")
            st.write(f"**÷ 発行済株式数:** {shares_outstanding:,.0f} 株")

        except Exception as e:
            st.error(f"予期せぬエラーが発生しました: {e}")
