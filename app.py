import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import calendar
import re

# ==========================================================
# 页面配置
# ==========================================================

st.set_page_config(
    page_title="Home Depot 销售经营分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}
[data-testid="stMetric"] {
    background: #f5f7fa;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 15px;
}
[data-testid="stMetricLabel"] {
    font-size: 14px;
}
[data-testid="stMetricValue"] {
    font-size: 25px;
}
</style>
""", unsafe_allow_html=True)

st.title("Home Depot 销售经营分析系统")
st.caption("销售总览 | SKU 动销 | 运营绩效 | RTV 退货 | 广告分析 | 利润分析")


# ==========================================================
# 通用函数
# ==========================================================

def read_excel(file):
    df = pd.read_excel(file)
    df.columns = [
        re.sub(r"\s+", " ", str(c).replace("\u3000", " ")).strip()
        for c in df.columns
    ]
    return df


def normalize_sku(series):
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


def numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip(),
        errors="coerce"
    )


def div(a, b):
    if isinstance(b, pd.Series):
        return a.div(b.replace(0, np.nan)).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0)
    if pd.isna(b) or b == 0:
        return 0
    return a / b


def usd(v):
    return f"${v:,.2f}"


def pct(v):
    return f"{v:.2%}"


def fmt(v):
    return f"{v:,.0f}"


def ensure_columns(df, columns, label):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        st.error(f"{label}缺少字段：{', '.join(missing)}")
        st.write("实际读取字段：", df.columns.tolist())
        st.stop()


def monthly_group(df, group_cols):
    if df.empty:
        return pd.DataFrame()

    result = df.groupby(group_cols, dropna=False).agg(
        总销售额=("销售额", "sum"),
        总销量=("销量", "sum"),
        总订单数=("订单标识", "nunique"),
        有销售天数=("订单日期", "nunique")
    ).reset_index()

    result["平均客单价"] = div(
        result["总销售额"], result["总订单数"]
    )
    result["日均销量"] = div(
        result["总销量"], result["有销售天数"]
    )
    return result


def metric_row(values):
    cols = st.columns(len(values))
    for col, (label, value) in zip(cols, values):
        col.metric(label, value)


def bar_chart(df, x, y, title, color=None, percent_axis=False):
    if df.empty:
        st.info("暂无数据")
        return

    fig = px.bar(
        df, x=x, y=y, color=color,
        barmode="group", title=title
    )

    fig.update_layout(
        height=390,
        margin=dict(t=55, b=30, l=20, r=20),
        hovermode="x unified",
        xaxis_title="",
        yaxis_title="",
        legend_title=""
    )

    if percent_axis:
        fig.update_yaxes(tickformat=".1%")

    st.plotly_chart(fig, use_container_width=True)


def download_csv(df, name, key):
    st.download_button(
        "下载明细 CSV",
        df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name=name,
        mime="text/csv",
        key=key
    )


def show_table(df, percent_cols=None):
    display = df.copy()
    percent_cols = percent_cols or []

    for c in percent_cols:
        if c in display.columns:
            display[c] = display[c].apply(
                lambda x: f"{x:.2%}" if pd.notna(x) else ""
            )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )


def month_range_days(month):
    try:
        d = pd.to_datetime(month + "-01")
        return calendar.monthrange(d.year, d.month)[1]
    except Exception:
        return 30


# ==========================================================
# 文件上传
# ==========================================================

with st.sidebar:
    st.header("上传 Excel 数据")

    sales_file = st.file_uploader(
        "1. 销售数据表",
        type=["xlsx", "xls"],
        key="sales"
    )

    rtv_file = st.file_uploader(
        "2. RTV 数据表",
        type=["xlsx", "xls"],
        key="rtv"
    )

    cost_file = st.file_uploader(
        "3. 产品成本表",
        type=["xlsx", "xls"],
        key="cost"
    )

    ads_file = st.file_uploader(
        "4. 广告数据表",
        type=["xlsx", "xls"],
        key="ads"
    )

    st.divider()
    st.header("利润模型参数")

    fixed_rate = st.number_input(
        "固定费率 (%)",
        min_value=0.0,
        value=3.25,
        step=0.25
    ) / 100

    other_rate = st.number_input(
        "其他费率 (%)",
        min_value=0.0,
        value=2.0,
        step=0.25
    ) / 100

    target_margin = st.number_input(
        "利润率考核线 (%)",
        value=13.0,
        step=1.0
    ) / 100

    daily_method = st.selectbox(
        "日均销量计算口径",
        ["按有销售天数", "按自然天数"]
    )


if sales_file is None:
    st.info("请先上传销售数据 Excel。")
    st.stop()


# ==========================================================
# 销售数据处理
# ==========================================================

sales = read_excel(sales_file)

ensure_columns(
    sales,
    ["Order Date", "产品SKU", "Quantity", "Total Cost"],
    "销售数据表"
)

sales["Order Date"] = pd.to_datetime(
    sales["Order Date"], errors="coerce"
)

sales = sales.dropna(subset=["Order Date"]).copy()

sales["月份"] = sales["Order Date"].dt.strftime("%Y-%m")
sales["订单日期"] = sales["Order Date"].dt.normalize()
sales["产品SKU"] = normalize_sku(sales["产品SKU"])

for c in ["产品名称", "品牌", "运营", "Line Status"]:
    if c not in sales.columns:
        sales[c] = "未填写"
    sales[c] = sales[c].fillna("未填写").astype(str).str.strip()

sales["Quantity"] = numeric(sales["Quantity"]).fillna(0)
sales["Total Cost"] = numeric(sales["Total Cost"]).fillna(0)

sales["销量"] = sales["Quantity"]
sales["销售额"] = sales["Total Cost"]

for c in ["Customer Order Number", "PO Number"]:
    if c not in sales.columns:
        sales[c] = ""

def build_order_id(row):
    a = str(row["Customer Order Number"]).strip()
    b = str(row["PO Number"]).strip()

    if a and a.lower() not in ["nan", "none"]:
        return "C:" + a
    if b and b.lower() not in ["nan", "none"]:
        return "P:" + b
    return "ROW:" + str(row.name)

sales["订单标识"] = sales.apply(build_order_id, axis=1)

# ==========================================================
# RTV 数据处理
# ==========================================================

rtv = pd.DataFrame()

if rtv_file is not None:
    rtv = read_excel(rtv_file)

    ensure_columns(
        rtv,
        [
            "RTV Date", "Order Date", "产品SKU",
            "QTY", "Total Cost", "总扣款"
        ],
        "RTV 数据表"
    )

    rtv["产品SKU"] = normalize_sku(rtv["产品SKU"])

    for c in ["RTV Date", "Order Date"]:
        rtv[c] = pd.to_datetime(rtv[c], errors="coerce")

    for c in ["QTY", "Total Cost", "总扣款", "10%运费"]:
        if c not in rtv.columns:
            rtv[c] = 0
        rtv[c] = numeric(rtv[c]).fillna(0)

    rtv["退货件数"] = rtv["QTY"].abs()
    rtv["退货金额"] = rtv["Total Cost"].abs()
    rtv["扣款金额"] = rtv["总扣款"].abs()
    rtv["退货运费"] = rtv["10%运费"].abs()

    rtv["订单月份"] = rtv["Order Date"].dt.strftime("%Y-%m")
    rtv["退货月份"] = rtv["RTV Date"].dt.strftime("%Y-%m")

    if "RTV Number" not in rtv.columns:
        rtv["RTV Number"] = rtv.index.astype(str)


# ==========================================================
# 产品成本处理
# ==========================================================

cost = pd.DataFrame(
    columns=["产品SKU", "产品成本价", "头程运费"]
)

if cost_file is not None:
    raw_cost = read_excel(cost_file)

    raw_cost = raw_cost.rename(columns={
        "SKU": "产品SKU",
        "产品成本": "产品成本价",
        "采购成本": "产品成本价",
        "头程": "头程运费",
        "头程费用": "头程运费"
    })

    ensure_columns(
        raw_cost,
        ["产品SKU", "产品成本价", "头程运费"],
        "产品成本表"
    )

    cost = raw_cost[
        ["产品SKU", "产品成本价", "头程运费"]
    ].copy()

    cost["产品SKU"] = normalize_sku(cost["产品SKU"])
    cost["产品成本价"] = numeric(cost["产品成本价"])
    cost["头程运费"] = numeric(cost["头程运费"])

    cost = cost[cost["产品SKU"] != ""].copy()

    duplicates = cost[
        cost.duplicated("产品SKU", keep=False)
    ]

    if not duplicates.empty:
        st.warning(
            f"成本表有 {duplicates['产品SKU'].nunique()} 个重复 SKU，"
            "目前保留最后一条记录。"
        )

    cost = cost.drop_duplicates(
        "产品SKU", keep="last"
    )


# ==========================================================
# 广告数据处理
# ==========================================================

ads = pd.DataFrame()

if ads_file is not None:
    ads = read_excel(ads_file)

    ensure_columns(
        ads,
        [
            "Year", "Month Name", "SKU",
            "Clicks", "Impressions",
            "SPA Revenue", "Spend"
        ],
        "广告数据表"
    )

    ads["SKU"] = normalize_sku(ads["SKU"])

    for c in [
        "Clicks", "Impressions",
        "SPA Revenue", "Spend"
    ]:
        ads[c] = numeric(ads[c]).fillna(0)

    month_map = {
        name.lower(): i
        for i, name in enumerate(calendar.month_name)
        if name
    }

    month_map.update({
        name.lower(): i
        for i, name in enumerate(calendar.month_abbr)
        if name
    })

    def get_month(v):
        if pd.isna(v):
            return np.nan
        s = str(v).strip().lower()
        if s.isdigit():
            return int(s)
        return month_map.get(s, np.nan)

    ads["月数字"] = ads["Month Name"].apply(get_month)
    ads["Year"] = numeric(ads["Year"])

    ads["广告月份日期"] = pd.to_datetime(
        dict(
            year=ads["Year"],
            month=ads["月数字"],
            day=1
        ),
        errors="coerce"
    )

    ads["月份"] = ads["广告月份日期"].dt.strftime("%Y-%m")

    if "Campaign Name" not in ads.columns:
        ads["Campaign Name"] = "未填写"


# ==========================================================
# 全局筛选
# ==========================================================

with st.sidebar:
    st.divider()
    st.header("数据筛选")

    statuses = sorted(sales["Line Status"].unique().tolist())
    selected_status = st.multiselect(
        "订单状态", statuses, default=statuses
    )

    all_months = sorted(sales["月份"].dropna().unique().tolist())
    selected_months = st.multiselect(
        "月份", all_months, default=all_months
    )

    brands = sorted(sales["品牌"].unique().tolist())
    selected_brands = st.multiselect(
        "品牌", brands, default=brands
    )

    operators = sorted(sales["运营"].unique().tolist())
    selected_ops = st.multiselect(
        "运营", operators, default=operators
    )

    sku_options = sorted(sales["产品SKU"].unique().tolist())
    selected_skus = st.multiselect(
        "产品 SKU（留空为全部）", sku_options
    )


filtered = sales[
    sales["Line Status"].isin(selected_status)
    & sales["月份"].isin(selected_months)
    & sales["品牌"].isin(selected_brands)
    & sales["运营"].isin(selected_ops)
].copy()

if selected_skus:
    filtered = filtered[
        filtered["产品SKU"].isin(selected_skus)
    ]

if filtered.empty:
    st.warning("当前筛选条件没有销售数据。")
    st.stop()

active_skus = filtered["产品SKU"].unique().tolist()

rtv_filtered = (
    rtv[rtv["产品SKU"].isin(active_skus)].copy()
    if not rtv.empty else pd.DataFrame()
)

ads_filtered = (
    ads[ads["SKU"].isin(active_skus)].copy()
    if not ads.empty else pd.DataFrame()
)


# ==========================================================
# 数据质量检查
# ==========================================================

with st.expander("数据质量检查 / SKU 匹配情况", expanded=False):

    st.write("销售记录数：", len(filtered))
    st.write("销售 SKU 数：", filtered["产品SKU"].nunique())

    if cost_file is not None:
        missing_cost = sorted(
            set(active_skus) - set(cost["产品SKU"])
        )
        st.write("未匹配成本 SKU 数：", len(missing_cost))

        if missing_cost:
            st.warning("未匹配成本的 SKU：")
            st.dataframe(
                pd.DataFrame({"产品SKU": missing_cost}),
                hide_index=True
            )

        invalid_cost = cost[
            cost["产品成本价"].isna()
            | cost["头程运费"].isna()
        ]

        if not invalid_cost.empty:
            st.warning("部分成本字段为空或非数字：")
            st.dataframe(invalid_cost, hide_index=True)

    if not ads.empty:
        unmatched_ads = sorted(
            set(ads_filtered["SKU"]) - set(active_skus)
        )
        st.write("当前广告 SKU 数：", ads_filtered["SKU"].nunique())
        st.caption(
            "广告 SKU 必须与销售表产品SKU一致，"
            "否则无法准确归属 SKU 广告花费。"
        )

    if not rtv.empty:
        st.write("RTV 记录数：", len(rtv_filtered))


# ==========================================================
# 主看板
# ==========================================================

tabs = st.tabs([
    "① 销售总览",
    "② SKU 动销",
    "③ 运营分析",
    "④ RTV 退货",
    "⑤ 广告分析",
    "⑥ 利润分析"
])


# ==========================================================
# 看板一：销售总览
# ==========================================================

with tabs[0]:

    st.header("销售数据总览")

    revenue = filtered["销售额"].sum()
    units = filtered["销量"].sum()
    orders = filtered["订单标识"].nunique()

    if daily_method == "按有销售天数":
        days = filtered["订单日期"].nunique()
    else:
        days = sum(month_range_days(m) for m in selected_months)

    metric_row([
        ("总销售额", usd(revenue)),
        ("总销量", fmt(units)),
        ("总订单数", fmt(orders)),
        ("平均客单价", usd(div(revenue, orders))),
        ("日均销量", f"{div(units, days):,.2f}")
    ])

    monthly = monthly_group(filtered, ["月份"]).sort_values("月份")

    if daily_method == "按自然天数":
        monthly["日均销量"] = monthly.apply(
            lambda r: div(
                r["总销量"],
                month_range_days(r["月份"])
            ),
            axis=1
        )

    monthly["销售额环比"] = monthly["总销售额"].pct_change()
    monthly["销量环比"] = monthly["总销量"].pct_change()

    st.subheader("月度销售趋势")

    metrics = [
        "总销售额", "总销量", "总订单数",
        "平均客单价", "日均销量"
    ]

    for i in range(0, len(metrics), 2):
        cols = st.columns(2)
        for j, metric in enumerate(metrics[i:i+2]):
            with cols[j]:
                bar_chart(
                    monthly, "月份", metric,
                    f"每月{metric}"
                )

    st.subheader("月度销售明细")
    show_table(
        monthly,
        ["销售额环比", "销量环比"]
    )

    download_csv(
        monthly, "sales_monthly.csv", "dl_sales"
    )


# ==========================================================
# 看板二：SKU 动销
# ==========================================================

with tabs[1]:

    st.header("SKU 月度动销分析")

    sku_month = monthly_group(
        filtered,
        ["月份", "产品SKU", "产品名称", "品牌", "运营"]
    )

    if daily_method == "按自然天数":
        sku_month["日均销量"] = sku_month.apply(
            lambda r: div(
                r["总销量"],
                month_range_days(r["月份"])
            ),
            axis=1
        )

    sku_month["销售额占比"] = div(
        sku_month["总销售额"],
        sku_month.groupby("月份")["总销售额"].transform("sum")
    )

    sku_month["月度排名"] = (
        sku_month.groupby("月份")["总销售额"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )

    sku_month = sku_month.sort_values(
        ["月份", "总销售额"],
        ascending=[True, False]
    )

    sku_month["累计占比"] = (
        sku_month.groupby("月份")["销售额占比"].cumsum()
    )

    previous_share = (
        sku_month["累计占比"] - sku_month["销售额占比"]
    )

    sku_month["SKU等级"] = np.select(
        [
            previous_share < 0.80,
            previous_share < 0.95
        ],
        ["A", "B"],
        default="C"
    )

    # 按 SKU 计算环比
    sku_month = sku_month.sort_values(
        ["产品SKU", "月份"]
    )

    sku_month["销售额环比"] = (
        sku_month.groupby("产品SKU")["总销售额"].pct_change()
    )

    sku_month["销量环比"] = (
        sku_month.groupby("产品SKU")["总销量"].pct_change()
    )

    sku_month["上月排名"] = (
        sku_month.groupby("产品SKU")["月度排名"].shift(1)
    )

    sku_month["排名变化"] = (
        sku_month["上月排名"] - sku_month["月度排名"]
    )

    st.subheader("SKU 月度排名表")

    keyword = st.text_input(
        "搜索产品 SKU / 产品名称",
        placeholder="输入 SKU 或产品名称",
        key="sku_keyword"
    )

    display_sku = sku_month.copy()

    if keyword:
        display_sku = display_sku[
            display_sku["产品SKU"].str.contains(
                keyword, case=False, regex=False, na=False
            )
            | display_sku["产品名称"].str.contains(
                keyword, case=False, regex=False, na=False
            )
        ]

    display_sku = display_sku.sort_values(
        ["月份", "月度排名"]
    )

    sku_cols = [
        "月份", "月度排名", "排名变化",
        "产品SKU", "产品名称", "品牌", "运营",
        "总销售额", "总销量", "总订单数",
        "有销售天数", "日均销量",
        "销售额占比", "销售额环比",
        "销量环比", "SKU等级"
    ]

    show_table(
        display_sku[sku_cols],
        ["销售额占比", "销售额环比", "销量环比"]
    )

    st.caption(
        "A/B/C 等级按每月销售额累计贡献划分："
        "A 为前约 80%，B 为接下来约 15%，C 为其余。"
    )

    st.subheader("单个 SKU 月度趋势")

    selected_sku = st.selectbox(
        "选择 SKU",
        sorted(sku_month["产品SKU"].unique()),
        key="single_sku"
    )

    one_sku = sku_month[
        sku_month["产品SKU"] == selected_sku
    ].sort_values("月份")

    latest = one_sku.iloc[-1]

    metric_row([
        ("最新月份排名", str(latest["月度排名"])),
        ("最新月份销售额", usd(latest["总销售额"])),
        ("最新月份销量", fmt(latest["总销量"])),
        ("日均销量", f'{latest["日均销量"]:.2f}'),
        ("SKU等级", latest["SKU等级"])
    ])

    for metric in [
        "总销售额", "总销量",
        "总订单数", "日均销量", "月度排名"
    ]:
        bar_chart(
            one_sku, "月份", metric,
            f"{selected_sku} - {metric}"
        )

    st.subheader("各月 Top 10 SKU")

    top10 = sku_month[
        sku_month["月度排名"] <= 10
    ]

    bar_chart(
        top10,
        "月份",
        "总销售额",
        "每月 Top 10 SKU 销售额",
        color="产品SKU"
    )

    download_csv(
        sku_month,
        "sku_monthly_analysis.csv",
        "dl_sku"
    )


# ==========================================================
# 看板三：运营分析
# ==========================================================

with tabs[2]:

    st.header("运营人员月度销售分析")

    operator_month = monthly_group(
        filtered, ["月份", "运营"]
    )

    sku_count = filtered.groupby(
        ["月份", "运营"]
    )["产品SKU"].nunique().reset_index(
        name="动销SKU数"
    )

    operator_month = operator_month.merge(
        sku_count,
        on=["月份", "运营"],
        how="left"
    )

    operator_month["销售额占比"] = div(
        operator_month["总销售额"],
        operator_month.groupby("月份")[
            "总销售额"
        ].transform("sum")
    )

    operator_month["运营排名"] = (
        operator_month.groupby("月份")["总销售额"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )

    if daily_method == "按自然天数":
        operator_month["日均销量"] = operator_month.apply(
            lambda r: div(
                r["总销量"],
                month_range_days(r["月份"])
            ),
            axis=1
        )

    for metric in [
        "总销售额", "总销量", "总订单数",
        "日均销量", "动销SKU数"
    ]:
        bar_chart(
            operator_month,
            "月份",
            metric,
            f"运营月度{metric}对比",
            color="运营"
        )

    st.subheader("运营月度明细")

    show_table(
        operator_month.sort_values(
            ["月份", "运营排名"]
        ),
        ["销售额占比"]
    )

    download_csv(
        operator_month,
        "operator_monthly.csv",
        "dl_operator"
    )


# ==========================================================
# 看板四：RTV 退货
# ==========================================================

with tabs[3]:

    st.header("RTV 退货及扣款分析")

    if rtv.empty:
        st.info("请上传 RTV 数据表。")

    else:
        view = st.radio(
            "选择日期视角",
            [
                "Order Date（订单日期）",
                "RTV Date（退货日期）"
            ],
            horizontal=True
        )

        month_col = (
            "订单月份"
            if view.startswith("Order")
            else "退货月份"
        )

        r = rtv_filtered[
            rtv_filtered[month_col].isin(selected_months)
        ].copy()

        sales_base = filtered.groupby("月份").agg(
            销售额=("销售额", "sum"),
            销量=("销量", "sum")
        ).reset_index()

        ret_month = r.groupby(month_col).agg(
            退货件数=("退货件数", "sum"),
            退货金额=("退货金额", "sum"),
            总扣款=("扣款金额", "sum"),
            退货运费=("退货运费", "sum"),
            RTV单数=("RTV Number", "nunique")
        ).reset_index().rename(
            columns={month_col: "月份"}
        )

        ret_month = sales_base.merge(
            ret_month,
            on="月份",
            how="outer"
        ).fillna(0).sort_values("月份")

        ret_month["数量退货率"] = div(
            ret_month["退货件数"],
            ret_month["销量"]
        )

        ret_month["金额退货率"] = div(
            ret_month["退货金额"],
            ret_month["销售额"]
        )

        ret_month["扣款费率"] = div(
            ret_month["总扣款"],
            ret_month["销售额"]
        )

        total_returns = r["退货件数"].sum()
        total_return_value = r["退货金额"].sum()
        total_deduction = r["扣款金额"].sum()

        metric_row([
            ("退货件数", fmt(total_returns)),
            ("退货金额", usd(total_return_value)),
            ("总扣款", usd(total_deduction)),
            (
                "数量退货率",
                pct(div(total_returns, ret_month["销量"].sum()))
            ),
            (
                "金额退货率",
                pct(div(total_return_value, ret_month["销售额"].sum()))
            )
        ])

        for metric in [
            "退货件数", "退货金额", "总扣款"
        ]:
            bar_chart(
                ret_month,
                "月份",
                metric,
                f"月度{metric}"
            )

        for metric in [
            "数量退货率",
            "金额退货率",
            "扣款费率"
        ]:
            bar_chart(
                ret_month,
                "月份",
                metric,
                f"月度{metric}",
                percent_axis=True
            )

        st.subheader("SKU 退货分析")

        sku_ret = r.groupby("产品SKU").agg(
            退货件数=("退货件数", "sum"),
            退货金额=("退货金额", "sum"),
            总扣款=("扣款金额", "sum")
        ).reset_index()

        sku_sales = filtered.groupby("产品SKU").agg(
            销售额=("销售额", "sum"),
            销量=("销量", "sum")
        ).reset_index()

        sku_ret = sku_sales.merge(
            sku_ret,
            on="产品SKU",
            how="outer"
        ).fillna(0)

        sku_ret["数量退货率"] = div(
            sku_ret["退货件数"], sku_ret["销量"]
        )

        sku_ret["金额退货率"] = div(
            sku_ret["退货金额"], sku_ret["销售额"]
        )

        show_table(
            sku_ret,
            ["数量退货率", "金额退货率"]
        )

        st.subheader("RTV 月度明细")
        show_table(
            ret_month,
            ["数量退货率", "金额退货率", "扣款费率"]
        )

        st.caption(
            "RTV Date 视角使用退货发生月份；"
            "Order Date 视角使用原订单月份。"
            "跨月退货可能使 RTV Date 退货率高于 100%。"
        )

        download_csv(
            ret_month,
            "rtv_monthly.csv",
            "dl_rtv"
        )


# ==========================================================
# 看板五：广告分析
# ==========================================================

with tabs[4]:

    st.header("广告数据分析")

    if ads.empty:
        st.info("请上传广告数据表。")

    else:
        a = ads_filtered[
            ads_filtered["月份"].isin(selected_months)
        ].copy()

        ad_month = a.groupby("月份").agg(
            广告花费=("Spend", "sum"),
            广告归因销售额=("SPA Revenue", "sum"),
            点击量=("Clicks", "sum"),
            曝光量=("Impressions", "sum")
        ).reset_index()

        ad_month["ROAS"] = div(
            ad_month["广告归因销售额"],
            ad_month["广告花费"]
        )

        ad_month["ACOS"] = div(
            ad_month["广告花费"],
            ad_month["广告归因销售额"]
        )

        ad_month["CTR"] = div(
            ad_month["点击量"],
            ad_month["曝光量"]
        )

        ad_month["CPC"] = div(
            ad_month["广告花费"],
            ad_month["点击量"]
        )

        monthly_sales_base = filtered.groupby("月份")[
            "销售额"
        ].sum().reset_index()

        ad_month = ad_month.merge(
            monthly_sales_base,
            on="月份",
            how="left"
        )

        ad_month["广告花费率"] = div(
            ad_month["广告花费"],
            ad_month["销售额"]
        )

        spend = a["Spend"].sum()
        attributed = a["SPA Revenue"].sum()
        clicks = a["Clicks"].sum()
        impressions = a["Impressions"].sum()

        metric_row([
            ("广告花费", usd(spend)),
            ("广告归因销售额", usd(attributed)),
            ("ROAS", f"{div(attributed, spend):.2f}"),
            ("ACOS", pct(div(spend, attributed))),
            ("CTR", pct(div(clicks, impressions)))
        ])

        for metric in [
            "广告花费", "广告归因销售额",
            "ROAS", "ACOS", "CTR",
            "CPC", "广告花费率"
        ]:
            bar_chart(
                ad_month,
                "月份",
                metric,
                f"月度{metric}",
                percent_axis=metric in [
                    "ACOS", "CTR", "广告花费率"
                ]
            )

        st.subheader("SKU 广告数据")

        ad_sku = a.groupby(["月份", "SKU"]).agg(
            广告花费=("Spend", "sum"),
            广告归因销售额=("SPA Revenue", "sum"),
            点击量=("Clicks", "sum"),
            曝光量=("Impressions", "sum")
        ).reset_index()

        ad_sku["ROAS"] = div(
            ad_sku["广告归因销售额"],
            ad_sku["广告花费"]
        )

        ad_sku["ACOS"] = div(
            ad_sku["广告花费"],
            ad_sku["广告归因销售额"]
        )

        show_table(ad_sku, ["ACOS"])

        st.subheader("广告 Campaign 分析")

        campaign = a.groupby(
            ["月份", "Campaign Name"]
        ).agg(
            广告花费=("Spend", "sum"),
            广告归因销售额=("SPA Revenue", "sum"),
            点击量=("Clicks", "sum")
        ).reset_index()

        campaign["ROAS"] = div(
            campaign["广告归因销售额"],
            campaign["广告花费"]
        )

        show_table(campaign)

        download_csv(
            ad_sku,
            "ads_sku_monthly.csv",
            "dl_ads"
        )


# ==========================================================
# 看板六：利润分析
# ==========================================================

with tabs[5]:

    st.header("利润率与成本率分析")

    if cost_file is None:
        st.info("请上传产品成本表。")

    else:

        # 只从销售数据生成基础利润表
        # 避免 merge 后出现产品成本价_x / _y
        profit = filtered.groupby(
            ["月份", "产品SKU"]
        ).agg(
            销售额=("销售额", "sum"),
            销量=("销量", "sum")
        ).reset_index()

        profit = profit.merge(
            cost[["产品SKU", "产品成本价", "头程运费"]],
            on="产品SKU",
            how="left",
            validate="many_to_one"
        )

        # 检查成本匹配
        profit["成本完整"] = (
            profit["产品成本价"].notna()
            & profit["头程运费"].notna()
        )

        missing_profit_skus = profit.loc[
            ~profit["成本完整"], "产品SKU"
        ].unique().tolist()

        if missing_profit_skus:
            st.error(
                f"有 {len(missing_profit_skus)} 个 SKU 缺少成本，"
                "这些 SKU 不参与利润率计算。"
            )
            st.dataframe(
                pd.DataFrame({"未匹配SKU": missing_profit_skus}),
                hide_index=True
            )

        # 只对完整成本的 SKU 计算利润
        valid_profit = profit[
            profit["成本完整"]
        ].copy()

        if valid_profit.empty:
            st.warning("没有任何 SKU 成功匹配成本。")
            st.stop()

        valid_profit["采购成本"] = (
            valid_profit["销量"]
            * valid_profit["产品成本价"]
        )

        valid_profit["头程总额"] = (
            valid_profit["销量"]
            * valid_profit["头程运费"]
        )

        # RTV 按原订单月份归属
        if not rtv.empty:
            rtv_profit = rtv_filtered.groupby(
                ["订单月份", "产品SKU"]
            )["退货金额"].sum().reset_index().rename(
                columns={"订单月份": "月份"}
            )

            valid_profit = valid_profit.merge(
                rtv_profit,
                on=["月份", "产品SKU"],
                how="left"
            )
        else:
            valid_profit["退货金额"] = 0.0

        valid_profit["退货金额"] = (
            valid_profit["退货金额"].fillna(0)
        )

        # 广告按 SKU + 月份归属
        if not ads.empty:
            ad_profit = ads_filtered.groupby(
                ["月份", "SKU"]
            )["Spend"].sum().reset_index().rename(
                columns={
                    "SKU": "产品SKU",
                    "Spend": "广告花费"
                }
            )

            valid_profit = valid_profit.merge(
                ad_profit,
                on=["月份", "产品SKU"],
                how="left"
            )
        else:
            valid_profit["广告花费"] = 0.0

        valid_profit["广告花费"] = (
            valid_profit["广告花费"].fillna(0)
        )

        # 利润公式
        valid_profit["退货率"] = div(
            valid_profit["退货金额"],
            valid_profit["销售额"]
        )

        valid_profit["广告花费率"] = div(
            valid_profit["广告花费"],
            valid_profit["销售额"]
        )

        valid_profit["固定费用"] = (
            valid_profit["销售额"] * fixed_rate
        )

        valid_profit["其他费用"] = (
            valid_profit["销售额"] * other_rate
        )

        valid_profit["利润额"] = (
            valid_profit["销售额"]
            - valid_profit["采购成本"]
            - valid_profit["头程总额"]
            - valid_profit["退货金额"]
            - valid_profit["广告花费"]
            - valid_profit["固定费用"]
            - valid_profit["其他费用"]
        )

        valid_profit["利润率"] = div(
            valid_profit["利润额"],
            valid_profit["销售额"]
        )

        valid_profit["采购成本率"] = div(
            valid_profit["采购成本"],
            valid_profit["销售额"]
        )

        valid_profit["头程费率"] = div(
            valid_profit["头程总额"],
            valid_profit["销售额"]
        )

        valid_profit["总成本率"] = (
            1 - valid_profit["利润率"]
        )

        valid_profit["考核结果"] = np.where(
            valid_profit["利润率"] >= target_margin,
            "达标",
            "未达标"
        )

        total_sales = valid_profit["销售额"].sum()
        total_profit = valid_profit["利润额"].sum()
        total_purchase = valid_profit["采购成本"].sum()
        total_freight = valid_profit["头程总额"].sum()

        metric_row([
            ("销售额", usd(total_sales)),
            ("利润额", usd(total_profit)),
            ("整体利润率", pct(div(total_profit, total_sales))),
            ("采购成本率", pct(div(total_purchase, total_sales))),
            ("头程费率", pct(div(total_freight, total_sales)))
        ])

        st.caption(
            "整体利润率按利润总额 ÷ 销售总额计算，"
            "不使用 SKU 利润率的简单平均值。"
        )

        # 月度利润
        profit_month = valid_profit.groupby("月份").agg(
            销售额=("销售额", "sum"),
            利润额=("利润额", "sum"),
            采购成本=("采购成本", "sum"),
            头程总额=("头程总额", "sum"),
            退货金额=("退货金额", "sum"),
            广告花费=("广告花费", "sum"),
            固定费用=("固定费用", "sum"),
            其他费用=("其他费用", "sum")
        ).reset_index().sort_values("月份")

        for numerator, result in [
            ("利润额", "利润率"),
            ("采购成本", "采购成本率"),
            ("头程总额", "头程费率"),
            ("退货金额", "退货费率"),
            ("广告花费", "广告费率")
        ]:
            profit_month[result] = div(
                profit_month[numerator],
                profit_month["销售额"]
            )

        st.subheader("月度利润趋势")

        for metric in [
            "销售额", "利润额", "利润率",
            "采购成本率", "头程费率",
            "退货费率", "广告费率"
        ]:
            bar_chart(
                profit_month,
                "月份",
                metric,
                f"月度{metric}",
                percent_axis="率" in metric
            )

        # SKU 利润表
        st.subheader("SKU 月度利润明细")

        sku_profit_cols = [
            "月份", "产品SKU", "销售额", "销量",
            "产品成本价", "头程运费",
            "采购成本", "头程总额",
            "退货金额", "广告花费",
            "固定费用", "其他费用",
            "利润额", "利润率",
            "采购成本率", "头程费率",
            "退货率", "广告花费率",
            "考核结果"
        ]

        show_table(
            valid_profit[sku_profit_cols].sort_values(
                ["月份", "利润率"]
            ),
            [
                "利润率", "采购成本率",
                "头程费率", "退货率", "广告花费率"
            ]
        )

        # 单 SKU 趋势
        st.subheader("单个 SKU 利润变化")

        selected_profit_sku = st.selectbox(
            "选择产品 SKU",
            sorted(valid_profit["产品SKU"].unique()),
            key="profit_sku"
        )

        single_profit = valid_profit[
            valid_profit["产品SKU"] == selected_profit_sku
        ].sort_values("月份")

        for metric in [
            "销售额", "利润额", "利润率",
            "采购成本率", "头程费率",
            "广告花费率", "退货率"
        ]:
            bar_chart(
                single_profit,
                "月份",
                metric,
                f"{selected_profit_sku} - {metric}",
                percent_axis="率" in metric
            )

        st.subheader("利润率考核分析")

        fail = valid_profit[
            valid_profit["利润率"] < target_margin
        ].copy()

        metric_row([
            ("SKU-月份记录数", fmt(len(valid_profit))),
            ("达标记录数", fmt(len(valid_profit) - len(fail))),
            ("未达标记录数", fmt(len(fail))),
            (
                "达标率",
                pct(div(len(valid_profit) - len(fail), len(valid_profit)))
            )
        ])

        if not fail.empty:
            st.warning("以下 SKU 月度利润率低于考核线")
            show_table(
                fail[
                    ["月份", "产品SKU", "销售额", "利润额", "利润率"]
                ].sort_values("利润率"),
                ["利润率"]
            )
        else:
            st.success("所有有效 SKU-月份记录均达到利润率考核线。")

        st.subheader("利润月度明细")

        show_table(
            profit_month,
            [
                "利润率", "采购成本率",
                "头程费率", "退货费率", "广告费率"
            ]
        )

        download_csv(
            valid_profit,
            "sku_profit_analysis.csv",
            "dl_profit"
        )


st.divider()

st.caption(
    "经营分析模型 | 数据来自销售、RTV、成本、广告 Excel。"
    "广告归因销售额不等于实际销售额。"
    "利润结果仅供经营分析，最终以实际结算数据为准。"
)
