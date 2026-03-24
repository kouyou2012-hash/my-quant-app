import os
import pandas as pd
import akshare as ak
import yfinance as yf
from datetime import datetime, timedelta
import streamlit as st
import plotly.express as px

# ============ 页面基础配置 ============
st.set_page_config(page_title="万能量化终端", page_icon="??", layout="wide")

for k in ["http_proxy", "https_proxy", "all_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]:
    os.environ.pop(k, None)

# ============ 数据获取核心逻辑 (融合V4.0修复) ============
@st.cache_data(ttl=3600)
def get_yahoo(code):
    try:
        df = yf.download(code, start="2000-01-01", progress=False).reset_index()
        if df.empty: return pd.DataFrame()
        def get_col(c): return df[c].iloc[:,0].values if isinstance(df[c], pd.DataFrame) else df[c].values
        res = pd.DataFrame({
            "日期": pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d"),
            "开盘": get_col("Open"), "收盘": get_col("Close")
        })
        return res
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_sina(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
        df = df.rename(columns={"date":"日期", "open":"开盘", "close":"收盘"})
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fund(code):
    try:
        # V4.0 修复：使用累计净值防暴跌失真
        df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
        df = df.rename(columns={"净值日期":"日期", "累计净值":"收盘"})
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        return df
    except: return pd.DataFrame()

def get_ref_close(source_func, code, name):
    df = source_func(code)
    if df.empty: return pd.DataFrame()
    return df[['日期', '收盘']].rename(columns={'收盘': name})

# ============ 手机自适应 UI 界面 ============
st.title("?? 移动端万能量化终端")

with st.sidebar:
    st.header("?? 参数配置")
    source = st.selectbox("主数据源", ["东方财富 (公募基金)", "Yahoo Finance (股票)", "新浪财经 (A股)"])
    code = st.text_input("代码 (无需后缀，系统智能补全)", value="513100")
    
    start_date = st.date_input("起始日期", value=datetime.today() - timedelta(days=730))
    end_date = st.date_input("结束日期", value=datetime.today())
    
    st.markdown("---")
    st.subheader("?? 附加对比指数")
    
    ref_options = {
        "上证指数": lambda: get_ref_close(get_yahoo, "000001.SS", "上证指数"),
        "深证成指": lambda: get_ref_close(get_yahoo, "399001.SZ", "深证成指"),
        "创业板指": lambda: get_ref_close(get_sina, "sz399006", "创业板指"),
        "纳斯达克": lambda: get_ref_close(get_yahoo, "^IXIC", "纳斯达克"),
        "标普500": lambda: get_ref_close(get_yahoo, "^GSPC", "标普500")
    }
    selected_refs = st.multiselect("选择需要对比的指数:", list(ref_options.keys()), default=["上证指数", "纳斯达克"])
    
    btn_fetch = st.button("? 获取数据并生成交互图表", type="primary", use_container_width=True)

# ============ 触发计算与画图 ============
if btn_fetch:
    if not code:
        st.warning("?? 请先输入代码！")
        st.stop()
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # 智能补齐后缀前缀逻辑
    yahoo_code, sina_code = code, code
    if len(code) == 6 and code.isdigit():
        if code.startswith(('5', '6')): 
            yahoo_code, sina_code = f"{code}.SS", f"sh{code}"
        elif code.startswith(('0', '1', '3')): 
            yahoo_code, sina_code = f"{code}.SZ", f"sz{code}"

    with st.spinner("?? 正在云端极速抓取数据..."):
        if "Yahoo" in source: df_main = get_yahoo(yahoo_code)
        elif "新浪" in source: df_main = get_sina(sina_code)
        else: df_main = get_fund(code)

        if df_main.empty:
            st.error("? 未找到该代码的数据，请检查代码或数据源。")
            st.stop()

        df_main = df_main[(df_main['日期'] >= start_str) & (df_main['日期'] <= end_str)]
        plot_targets = ["主标的"]
        df_main = df_main.rename(columns={"收盘": "主标的"})
        
        for ref_name in selected_refs:
            df_ref = ref_options[ref_name]()
            if not df_ref.empty:
                df_main = pd.merge(df_main, df_ref, on="日期", how="left")
                df_main[ref_name] = df_main[ref_name].ffill()
                plot_targets.append(ref_name)

        # 解决“对比有问题”的终极方案：归一化累计收益率
        # 将所有指标起点统一设为 0%，完美解决 8块钱 和 3000点 放在一起比例失调的问题
        st.subheader("?? 累计收益率走势对比 (完美解决比例失调)")
        
        df_plot = df_main[['日期'] + plot_targets].copy().dropna(subset=['主标的'])
        df_plot.set_index('日期', inplace=True)
        
        for col in plot_targets:
            valid = df_plot[col].dropna()
            if not valid.empty:
                base_val = valid.iloc[0]
                df_plot[col] = ((df_plot[col] / base_val) - 1) * 100

        # Plotly 交互式图表
        fig = px.line(df_plot, x=df_plot.index, y=plot_targets, 
                      labels={"value": "累计收益率 (%)", "variable": "指标名称"})
        fig.update_layout(hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("??? 详细对齐数据")
        df_display = df_main.rename(columns={"主标的": f"{code} 收盘"}).sort_values('日期', ascending=False)
        st.dataframe(df_display, use_container_width=True)