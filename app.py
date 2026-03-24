import os
import pandas as pd
import akshare as ak
import yfinance as yf
from datetime import datetime, timedelta
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ============ 页面基础配置 (移动端适配) ============
st.set_page_config(page_title="移动量化终端", page_icon="📈", layout="centered")

# 清除代理干扰
for k in ["http_proxy", "https_proxy", "all_proxy", "no_proxy"]:
    os.environ.pop(k, None)
    os.environ.pop(k.upper(), None)

# ============ 数据获取核心逻辑 ============
@st.cache_data(ttl=3600)
def get_yahoo(code):
    try:
        df = yf.download(code, start="2000-01-01", progress=False).reset_index()
        if df.empty: return pd.DataFrame()
        def get_col(c): return df[c].iloc[:,0].values if isinstance(df[c], pd.DataFrame) else df[c].values
        res = pd.DataFrame({
            "日期": pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d"),
            "开盘": get_col("Open"), "最高": get_col("High"), 
            "最低": get_col("Low"), "收盘": get_col("Close"), "成交量": get_col("Volume")
        })
        return res
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_sina(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
        df = df.rename(columns={"date":"日期", "open":"开盘", "high":"最高", "low":"最低", "close":"收盘", "volume":"成交量"})
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fund(code):
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
        df = df.rename(columns={"净值日期":"日期", "累计净值":"收盘"})
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        df["开盘"] = df["最高"] = df["最低"] = df["收盘"]
        df["成交量"] = 0
        return df
    except: return pd.DataFrame()

def get_ref_close(source_func, code, name):
    df = source_func(code)
    if df.empty: return pd.DataFrame()
    return df[['日期', '收盘']].rename(columns={'收盘': name})

def resample_kline(df, freq_str):
    if "D" in freq_str: return df
    rule = "W-FRI" if "W" in freq_str else "ME" if "M" in freq_str else "YE"
    df_temp = df.copy()
    df_temp['日期'] = pd.to_datetime(df_temp['日期'])
    df_temp.set_index('日期', inplace=True)
    agg_dict = {}
    if '开盘' in df_temp.columns: agg_dict['开盘'] = 'first'
    if '最高' in df_temp.columns: agg_dict['最高'] = 'max'
    if '最低' in df_temp.columns: agg_dict['最低'] = 'min'
    if '收盘' in df_temp.columns: agg_dict['收盘'] = 'last'
    if '成交量' in df_temp.columns: agg_dict['成交量'] = 'sum'
    for col in df_temp.columns:
        if col not in agg_dict: agg_dict[col] = 'last'
    df_res = df_temp.resample(rule).agg(agg_dict).dropna(subset=['收盘'])
    df_res.reset_index(inplace=True)
    df_res['日期'] = df_res['日期'].dt.strftime('%Y-%m-%d')
    return df_res

# ============ 移动端专属 UI 界面 ============
st.markdown("<h2 style='text-align: center;'>📱 移动端量化终端 Pro</h2>", unsafe_allow_html=True)

# 使用折叠面板代替侧边栏，对手机更友好
with st.expander("⚙️ 展开参数设置", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        source = st.selectbox("主数据源", ["东方财富 (公募基金)", "Yahoo Finance (股票)", "新浪财经 (A股)"])
        start_date = st.date_input("起始日期", value=datetime.today() - timedelta(days=730))
    with col2:
        code = st.text_input("代码 (智能补全)", value="513100")
        end_date = st.date_input("结束日期", value=datetime.today())
    
    freq_var = st.selectbox("时间周期", ["日线 (D)", "周线 (W)", "月线 (M)", "年线 (Y)"])
    
    # 指数定义
    ref_options = {
        "上证指数": lambda: get_ref_close(get_yahoo, "000001.SS", "上证指数"),
        "深证成指": lambda: get_ref_close(get_yahoo, "399001.SZ", "深证成指"),
        "创业板指": lambda: get_ref_close(get_sina, "sz399006", "创业板指"),
        "纳斯达克": lambda: get_ref_close(get_yahoo, "^IXIC", "纳斯达克"),
        "标普500": lambda: get_ref_close(get_yahoo, "^GSPC", "标普500")
    }
    selected_refs = st.multiselect("附加对比指数:", list(ref_options.keys()), default=["上证指数"])
    
    btn_fetch = st.button("🚀 生成深度分析", type="primary", use_container_width=True)

# ============ 核心计算与可视化 ============
if btn_fetch:
    if not code:
        st.warning("请输入代码！")
        st.stop()
        
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # 智能补全
    yahoo_code, sina_code = code, code
    if len(code) == 6 and code.isdigit():
        if code.startswith(('5', '6')): 
            yahoo_code, sina_code = f"{code}.SS", f"sh{code}"
        elif code.startswith(('0', '1', '3')): 
            yahoo_code, sina_code = f"{code}.SZ", f"sz{code}"

    with st.spinner("数据极速抓取中..."):
        if "Yahoo" in source: df_main = get_yahoo(yahoo_code)
        elif "新浪" in source: df_main = get_sina(sina_code)
        else: df_main = get_fund(code)

        if df_main.empty:
            st.error("获取失败，请检查代码。")
            st.stop()

        df_main = df_main[(df_main['日期'] >= start_str) & (df_main['日期'] <= end_str)]
        df_main = df_main.rename(columns={"收盘": "主标的"})
        plot_targets = ["主标的"]
        
        for ref_name in selected_refs:
            df_ref = ref_options[ref_name]()
            if not df_ref.empty:
                df_main = pd.merge(df_main, df_ref, on="日期", how="left")
                df_main[ref_name] = df_main[ref_name].ffill()
                plot_targets.append(ref_name)

        # 恢复重采样功能
        df_main = resample_kline(df_main, freq_var)

        # 归一化累计收益率计算
        df_plot = df_main[['日期'] + plot_targets].copy().dropna(subset=['主标的'])
        df_plot.set_index('日期', inplace=True)
        for col in plot_targets:
            valid = df_plot[col].dropna()
            if not valid.empty:
                base_val = valid.iloc[0]
                df_plot[col] = ((df_plot[col] / base_val) - 1) * 100

        # ====== 移动端优化的 Plotly 图表 (更新配色方案) ======
        st.markdown("### 📈 累计收益率走势对比")
        
        # 🌟 核心更新：构建专属配色地图
        # 1. 默认色序：主标的用深蓝 (RoyalBlue)
        color_discrete_sequence = ['RoyalBlue'] 
        
        # 2. 动态生成红色的指数色序 (如果选了多个指数，自动生成红色的渐变色序)
        reds = px.colors.sequential.Reds_r # 使用反向红色系，让颜色深一点
        index_colors = [reds[i * (len(reds)//(len(selected_refs)+2))] for i in range(1, len(selected_refs)+1)]
        
        # 3. 合并色序
        color_discrete_sequence.extend(index_colors)

        # 绘图时应用色序
        fig = px.line(df_plot, x=df_plot.index, y=plot_targets, 
                      labels={"value": "收益率 (%)", "variable": "指标"},
                      color_discrete_sequence=color_discrete_sequence) # 应用自定义色序
        
        # 针对手机屏幕的神级优化排版
        fig.update_layout(
            hovermode="x unified",
            margin=dict(l=10, r=10, t=20, b=10), # 极大地压缩边缘留白
            legend=dict(
                orientation="h", 
                yanchor="top", y=-0.15, # 把图例放到图表正下方，不再遮挡线条
                xanchor="center", x=0.5
            ),
            dragmode="pan" # 默认改为平移，适合手机触摸滑动
        )
        
        # 隐藏碍眼的 ModeBar，允许原生双指缩放
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})

        # ====== 丰富的数据表格展示 ======
        st.markdown("### 🗄️ 深度数据面板")
        # 将最新的日期排在最前
        df_display = df_main.sort_values('日期', ascending=False)
        st.dataframe(df_display, use_container_width=True)
