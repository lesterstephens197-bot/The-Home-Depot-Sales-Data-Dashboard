
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import calendar

st.set_page_config(
    page_title="Home Depot 销售经营分析",
    page_icon="📊",
    layout="wide"
)

st.title("Home Depot 销售经营分析系统")
st.caption("销售 | SKU | 运营 | RTV | 广告 | 利润")

# ===================== 基础函数 =====================

def num(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(
                df[c].astype(str).str.replace(",", "", regex=False)
                .str.replace("$", "", regex=False)
                .str.replace("%", "", regex=False),
                errors="coerce"
            ).fillna(0)
    return df

def clean_sku(s):
    return s.fillna("").astype(str).str.strip().str.upper().str.replace(
        r"\.0$", "", regex=True
    )

def read_excel(file):
    df = pd.read_excel(file)
    df.columns = [
        str(c).strip().replace("\n", " ")
        for c in df.columns
    ]
    return df

def money(v):
    return f"${v:,.2f}"

def integer(v):
    return f"{v:,.0f}"

def percent(v):
    return f"{v:.2%}"

def safe_div(a, b):
    if isinstance(b, pd.Series):
        return a.div(b.replace(0, np.nan)).fillna(0)
    return a / b if b else 0

def kpis(items):
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)

def bar(df, x, y, title, color=None, barmode="group"):
    if df.empty:
        st.info("当前没有可展示的数据")
        return
    fig = px.bar(
        df, x=x, y=y, color=color,
        barmode=barmode, title=title,
        text_auto=".2s"
    )
    fig.update_layout(
        height=420,
        hovermode="x unified",
        margin=dict(t=65, b=35),
        xaxis_title=None,
        yaxis_title=None
    )
    st.plotly_chart(fig, use_container_width=True)

def line(df, x, y, title, color=None):
    if df.empty:
        return
    fig = px.line(
        df, x=x, y=y, color=color,
        markers=True, title=title
    )
    fig.update_layout(
        height=400,
        hovermode="x unified",
        xaxis_title=None,
        yaxis_title=None
    )
    st.plotly_chart(fig, use_container_width=True)

def download(df, filename, key):
    st.download_button(
        "下载当前明细 CSV",
        data=df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key
    )

def monthly_sales(df, group_cols=["月份"]):
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(group_cols, dropna=False).agg(
        总销售额=("销售额", "sum"),
        总销量=("销量", "sum"),
        总订单数=("订单标识", "nunique"),
        有销售天数=("订单日", lambda s: s.nunique())
    ).reset_index()
    g["平均客单价"] = safe_div(g["总销售额"], g["总订单数"])
    g["日均销量"] = safe_div(g["总销量"], g["有销售天数"])
    return g

# ===================== 上传文件 =====================

with st.sidebar:
    st.header("上传 Excel 数据")
    sales_file = st.file_uploader(
        "1. 销售数据表", type=["xlsx", "xls"], key="sales"
    )
    rtv_file = st.file_uploader(
        "2. RTV 数据表", type=["xlsx", "xls"], key="rtv"
    )
    cost_file = st.file_uploader(
        "3. 产品成本表", type=["xlsx", "xls"], key="cost"
    )
    ads_file = st.file_uploader(
        "4. 广告数据表", type=["xlsx", "xls"], key="ads"
    )

    st.divider()
    st.subheader("利润模型参数")
    fixed_fee = st.number_input(
        "固定费率 (%)", value=3.25, step=0.25
    ) / 100
    extra_fee = st.number_input(
        "其他费率 (%)", value=2.00, step=0.25
    ) / 100
    target_margin = st.number_input(
        "目标利润率 (%)", value=13.00, step=1.0
    ) / 100

if sales_file is None:
    st.info("请先上传销售数据 Excel，其他三张表可随后上传。")
    st.stop()

# ===================== 销售清洗 =====================

sales = read_excel(sales_file)

required_sales = [
    "Order Date", "产品SKU", "Quantity", "Total Cost"
]
missing = [c for c in required_sales if c not in sales.columns]
if missing:
    st.error(f"销售表缺少字段：{missing}")
    st.stop()

sales["Order Date"] = pd.to_datetime(
    sales["Order Date"], errors="coerce"
)
sales = sales.dropna(subset=["Order Date"]).copy()
sales["月份"] = sales["Order Date"].dt.strftime("%Y-%m")
sales["订单日"] = sales["Order Date"].dt.normalize()
sales["产品SKU"] = clean_sku(sales["产品SKU"])

sales = num(sales, ["Quantity", "Total Cost", "Unit Cost"])
sales["销售额"] = sales["Total Cost"]
sales["销量"] = sales["Quantity"]

for c in ["产品名称", "品牌", "运营", "Line Status"]:
    if c not in sales.columns:
        sales[c] = "未填写"
    sales[c] = sales[c].fillna("未填写").astype(str).str.strip()

# 优先使用 Customer Order Number 识别客户订单
# 缺失时回退到 PO Number
if "Customer Order Number" not in sales.columns:
    sales["Customer Order Number"] = ""
if "PO Number" not in sales.columns:
    sales["PO Number"] = ""

def order_id(row):
    customer = str(row["Customer Order Number"]).strip()
    po = str(row["PO Number"]).strip()
    if customer and customer.lower() not in ["nan", "none"]:
        return "C:" + customer
    if po and po.lower() not in ["nan", "none"]:
        return "P:" + po
    return "ROW:" + str(row.name)

sales["订单标识"] = sales.apply(order_id, axis=1)

# ===================== RTV 清洗 =====================

rtv = pd.DataFrame()
if rtv_file:
    rtv = read_excel(rtv_file)
    rtv["产品SKU"] = clean_sku(rtv["产品SKU"])
    rtv["RTV Date"] = pd.to_datetime(
        rtv["RTV Date"], errors="coerce"
    )
    rtv["Order Date"] = pd.to_datetime(
        rtv["Order Date"], errors="coerce"
    )
    rtv = num(
        rtv, ["QTY", "UNIT COST", "Total Cost", "10%运费", "总扣款"]
    )
    rtv["退货件数"] = rtv["QTY"].abs()
    rtv["退货金额"] = rtv["Total Cost"].abs()
    rtv["扣款金额"] = rtv["总扣款"].abs()
    rtv["订单月份"] = rtv["Order Date"].dt.strftime("%Y-%m")
    rtv["退货月份"] = rtv["RTV Date"].dt.strftime("%Y-%m")

# ===================== 成本清洗 =====================

cost = pd.DataFrame(columns=["产品SKU", "产品成本价", "头程运费"])
if cost_file:
    cost = read_excel(cost_file)
    cost = cost.rename(columns={"SKU": "产品SKU"})
    cost["产品SKU"] = clean_sku(cost["产品SKU"])
    cost = num(cost, ["产品成本价", "头程运费"])
    cost = cost.drop_duplicates("产品SKU", keep="last")

# ===================== 广告清洗 =====================

ads = pd.DataFrame()
if ads_file:
    ads = read_excel(ads_file)
    ads["SKU"] = clean_sku(ads["SKU"])
    ads = num(
        ads,
        ["Clicks", "Impressions", "SPA Revenue", "Spend"]
    )

    # 使用 Year + Month Name 生成月份
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

    def parse_month(v):
        if pd.isna(v):
            return np.nan
        t = str(v).strip()
        if t.isdigit():
            return int(t)
        return month_map.get(t.lower(), np.nan)

    ads["月数字"] = ads["Month Name"].apply(parse_month)
    ads["Year"] = pd.to_numeric(ads["Year"], errors="coerce")
    ads["广告日期"] = pd.to_datetime(
        dict(
            year=ads["Year"],
            month=ads["月数字"],
            day=1
        ),
        errors="coerce"
    )
    ads["月份"] = ads["广告日期"].dt.strftime("%Y-%m")

# ===================== 全局筛选 =====================

with st.sidebar:
    st.divider()
    st.header("全局筛选")

    months = sorted(sales["月份"].dropna().unique().tolist())
    selected_months = st.multiselect(
        "月份", months, default=months
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
        "产品 SKU（留空表示全部）", sku_options
    )

filtered = sales[
    sales["月份"].isin(selected_months)
    & sales["品牌"].isin(selected_brands)
    & sales["运营"].isin(selected_ops)
].copy()

if selected_skus:
    filtered = filtered[filtered["产品SKU"].isin(selected_skus)]

if filtered.empty:
    st.warning("当前筛选条件下没有销售数据。")
    st.stop()

active_skus = filtered["产品SKU"].unique().tolist()

# RTV / 广告按所选产品范围过滤
if not rtv.empty:
    rtv_filtered = rtv[rtv["产品SKU"].isin(active_skus)].copy()
else:
    rtv_filtered = rtv.copy()

if not ads.empty:
    ads_filtered = ads[ads["SKU"].isin(active_skus)].copy()
else:
    ads_filtered = ads.copy()

tabs = st.tabs([
    "① 销售总览",
    "② SKU 分析",
    "③ 运营分析",
    "④ RTV 退货",
    "⑤ 广告分析",
    "⑥ 利润分析"
])

# ====================================================
# 看板一：销售总览
# ====================================================

with tabs[0]:
    st.header("销售数据总览")

    total_revenue = filtered["销售额"].sum()
    total_units = filtered["销量"].sum()
    total_orders = filtered["订单标识"].nunique()
    active_days = filtered["订单日"].nunique()

    kpis([
        ("总销售额", money(total_revenue)),
        ("总销量", integer(total_units)),
        ("总订单数", integer(total_orders)),
        ("平均客单价", money(safe_div(total_revenue, total_orders))),
        ("日均销量", f"{safe_div(total_units, active_days):,.2f}")
    ])

    st.caption("日均销量 = 总销量 ÷ 实际有销售的天数")

    monthly = monthly_sales(filtered).sort_values("月份")

    st.subheader("各月销售指标对比")
    metrics = [
        "总销售额", "总销量", "总订单数",
        "平均客单价", "日均销量"
    ]

    for i in range(0, len(metrics), 2):
        cols = st.columns(2)
        for j, metric in enumerate(metrics[i:i+2]):
            with cols[j]:
                bar(monthly, "月份", metric, f"月度{metric}")

    st.subheader("月度销售明细")
    st.dataframe(monthly, use_container_width=True, hide_index=True)
    download(monthly, "monthly_sales.csv", "download_sales")

# ====================================================
# 看板二：SKU 分析
# ====================================================

with tabs[1]:
    st.header("SKU 月度动销及排名分析")

    sku = monthly_sales(
        filtered, ["月份", "产品SKU", "产品名称", "品牌", "运营"]
    )

    sku["销售额占比"] = safe_div(
        sku["总销售额"],
        sku.groupby("月份")["总销售额"].transform("sum")
    )

    sku["月度排名"] = sku.groupby("月份")[
        "总销售额"
    ].rank(method="dense", ascending=False).astype(int)

    # 按月度销售额累计贡献计算 ABC 等级
    sku = sku.sort_values(
        ["月份", "总销售额"], ascending=[True, False]
    )
    sku["累计销售额占比"] = sku.groupby("月份")[
        "销售额占比"
    ].cumsum()

    sku["SKU等级"] = np.select(
        [
            sku["累计销售额占比"] - sku["销售额占比"] < 0.8,
            sku["累计销售额占比"] - sku["销售额占比"] < 0.95
        ],
        ["A", "B"],
        default="C"
    )

    sku = sku.sort_values(["月份", "月度排名"])

    search = st.text_input(
        "搜索单个产品 SKU / 产品名称", placeholder="输入 SKU 或名称"
    )

    display_sku = sku.copy()
    if search:
        display_sku = display_sku[
            display_sku["产品SKU"].str.contains(
                search, case=False, na=False, regex=False
            )
            | display_sku["产品名称"].str.contains(
                search, case=False, na=False, regex=False
            )
        ]

    st.subheader("SKU 月度排名明细")
    columns = [
        "月份", "月度排名", "产品SKU", "产品名称",
        "品牌", "运营", "总销售额", "总销量",
        "总订单数", "有销售天数", "日均销量",
        "销售额占比", "SKU等级"
    ]

    st.dataframe(
        display_sku[columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "销售额占比": st.column_config.NumberColumn(
                format="%.2f%%"
            )
        }
    )
    st.caption("销售额占比原始数值为小数，例如 0.25 表示 25%。")

    st.subheader("单个 SKU 月度变化趋势")

    sku_list = sorted(sku["产品SKU"].unique())
    selected = st.selectbox("选择产品 SKU", sku_list)

    single = sku[sku["产品SKU"] == selected].sort_values("月份")

    if not single.empty:
        latest = single.iloc[-1]
        kpis([
            ("最新月份排名", str(latest["月度排名"])),
            ("最新月份销售额", money(latest["总销售额"])),
            ("最新月份销量", integer(latest["总销量"])),
            ("最新月份日均销量", f'{latest["日均销量"]:.2f}'),
            ("SKU 等级", latest["SKU等级"])
        ])

        for metric in [
            "总销售额", "总销量", "总订单数",
            "日均销量", "月度排名"
        ]:
            bar(single, "月份", metric, f"{selected} - {metric}")

        single = single.copy()
        single["销售额环比"] = single["总销售额"].pct_change()
        single["销量环比"] = single["总销量"].pct_change()
        st.dataframe(single, use_container_width=True, hide_index=True)

    st.subheader("每月 Top 10 SKU")
    top10 = sku[sku["月度排名"] <= 10]
    bar(
        top10, "月份", "总销售额",
        "每月 Top 10 SKU 销售额", color="产品SKU"
    )

    download(sku, "sku_monthly_analysis.csv", "download_sku")

# ====================================================
# 看板三：运营分析
# ====================================================

with tabs[2]:
    st.header("运营月度销售分析")

    op = monthly_sales(filtered, ["月份", "运营"])

    sku_counts = filtered.groupby(
        ["月份", "运营"]
    )["产品SKU"].nunique().reset_index(name="动销SKU数")

    op = op.merge(sku_counts, on=["月份", "运营"], how="left")

    op["销售额占比"] = safe_div(
        op["总销售额"],
        op.groupby("月份")["总销售额"].transform("sum")
    )

    op["运营排名"] = op.groupby("月份")[
        "总销售额"
    ].rank(method="dense", ascending=False).astype(int)

    for metric in [
        "总销售额", "总销量", "总订单数",
        "日均销量", "动销SKU数"
    ]:
        bar(
            op, "月份", metric,
            f"各运营月度{metric}对比",
            color="运营"
        )

    st.subheader("运营月度明细")
    st.dataframe(
        op.sort_values(["月份", "运营排名"]),
        use_container_width=True, hide_index=True
    )

    download(op, "operator_monthly.csv", "download_op")

# ====================================================
# 看板四：RTV 退货分析
# ====================================================

with tabs[3]:
    st.header("RTV 退货及扣款分析")

    if rtv.empty:
        st.info("请上传 RTV 数据表。")
    else:
        view = st.radio(
            "选择退货分析视角",
            ["按订单日期（Order Date）", "按退货日期（RTV Date）"],
            horizontal=True
        )

        month_col = (
            "订单月份" if "Order Date" in view else "退货月份"
        )

        r = rtv_filtered[
            rtv_filtered[month_col].isin(selected_months)
        ].copy()

        kpis([
            ("退货件数", integer(r["退货件数"].sum())),
            ("退货商品金额", money(r["退货金额"].sum())),
            ("总扣款", money(r["扣款金额"].sum())),
            ("RTV记录数", integer(len(r)))
        ])

        # 退货率使用对应月份销售额及销量作为分母
        ret_month = r.groupby(month_col).agg(
            退货件数=("退货件数", "sum"),
            退货金额=("退货金额", "sum"),
            总扣款=("扣款金额", "sum"),
            RTV记录数=("RTV Number", "nunique")
        ).reset_index().rename(columns={month_col: "月份"})

        base_month = monthly_sales(filtered)[
            ["月份", "总销售额", "总销量"]
        ]

        ret_month = base_month.merge(
            ret_month, on="月份", how="outer"
        ).fillna(0).sort_values("月份")

        ret_month["数量退货率"] = safe_div(
            ret_month["退货件数"], ret_month["总销量"]
        )
        ret_month["金额退货率"] = safe_div(
            ret_month["退货金额"], ret_month["总销售额"]
        )
        ret_month["扣款费率"] = safe_div(
            ret_month["总扣款"], ret_month["总销售额"]
        )

        for metric in ["退货件数", "退货金额", "总扣款"]:
            bar(ret_month, "月份", metric, f"月度{metric}")

        rate_long = ret_month.melt(
            id_vars="月份",
            value_vars=["数量退货率", "金额退货率", "扣款费率"],
            var_name="指标", value_name="比率"
        )
        rate_long["比率(%)"] = rate_long["比率"] * 100

        bar(
            rate_long, "月份", "比率(%)",
            "月度退货率及扣款费率",
            color="指标"
        )

        st.subheader("SKU 退货明细")
        sku_rtv = r.groupby("产品SKU").agg(
            退货件数=("退货件数", "sum"),
            退货金额=("退货金额", "sum"),
            总扣款=("扣款金额", "sum")
        ).reset_index()

        sku_base = filtered.groupby("产品SKU").agg(
            销售额=("销售额", "sum"),
            销量=("销量", "sum")
        ).reset_index()

        sku_rtv = sku_base.merge(
            sku_rtv, on="产品SKU", how="outer"
        ).fillna(0)

        sku_rtv["数量退货率"] = safe_div(
            sku_rtv["退货件数"], sku_rtv["销量"]
        )
        sku_rtv["金额退货率"] = safe_div(
            sku_rtv["退货金额"], sku_rtv["销售额"]
        )

        st.dataframe(
            sku_rtv, use_container_width=True, hide_index=True
        )
        st.subheader("RTV 月度明细")
        st.dataframe(
            ret_month, use_container_width=True, hide_index=True
        )
        download(ret_month, "rtv_monthly.csv", "download_rtv")

        st.warning(
            "RTV Date 视角的退货率是当月退货量与当月销售量之比，"
            "并非严格订单队列退货率；退货可能来自以前月份。"
        )

# ====================================================
# 看板五：广告分析
# ====================================================

with tabs[4]:
    st.header("广告投放及 ROAS 分析")

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

        ad_month["ROAS"] = safe_div(
            ad_month["广告归因销售额"], ad_month["广告花费"]
        )
        ad_month["ACOS"] = safe_div(
            ad_month["广告花费"], ad_month["广告归因销售额"]
        )
        ad_month["CTR"] = safe_div(
            ad_month["点击量"], ad_month["曝光量"]
        )
        ad_month["CPC"] = safe_div(
            ad_month["广告花费"], ad_month["点击量"]
        )

        ad_month = ad_month.merge(
            monthly_sales(filtered)[["月份", "总销售额"]],
            on="月份", how="left"
        )
        ad_month["广告花费率"] = safe_div(
            ad_month["广告花费"], ad_month["总销售额"]
        )

        spend = a["Spend"].sum()
        revenue = a["SPA Revenue"].sum()
        clicks = a["Clicks"].sum()
        impressions = a["Impressions"].sum()

        kpis([
            ("广告花费", money(spend)),
            ("广告归因销售额", money(revenue)),
            ("ROAS", f"{safe_div(revenue, spend):.2f}"),
            ("ACOS", percent(safe_div(spend, revenue))),
            ("CTR", percent(safe_div(clicks, impressions)))
        ])

        for metric in [
            "广告花费", "广告归因销售额",
            "ROAS", "ACOS", "广告花费率", "CPC"
        ]:
            bar(ad_month, "月份", metric, f"月度{metric}")

        st.subheader("SKU 广告分析")
        ad_sku = a.groupby(["月份", "SKU"]).agg(
            广告花费=("Spend", "sum"),
            广告归因销售额=("SPA Revenue", "sum"),
            点击量=("Clicks", "sum"),
            曝光量=("Impressions", "sum")
        ).reset_index()

        ad_sku["ROAS"] = safe_div(
            ad_sku["广告归因销售额"], ad_sku["广告花费"]
        )
        ad_sku["ACOS"] = safe_div(
            ad_sku["广告花费"], ad_sku["广告归因销售额"]
        )

        st.dataframe(
            ad_sku, use_container_width=True, hide_index=True
        )

        st.subheader("广告活动分析")
        campaign = a.groupby(
            ["月份", "Campaign Name"]
        ).agg(
            广告花费=("Spend", "sum"),
            广告归因销售额=("SPA Revenue", "sum"),
            点击量=("Clicks", "sum")
        ).reset_index()

        campaign["ROAS"] = safe_div(
            campaign["广告归因销售额"], campaign["广告花费"]
        )
        st.dataframe(
            campaign, use_container_width=True, hide_index=True
        )
        download(ad_sku, "ads_sku_monthly.csv", "download_ads")

# ====================================================
# 看板六：利润及成本分析
# ====================================================

with tabs[5]:
    st.header("利润率及成本率分析")

    if cost_file is None:
        st.info("请上传产品成本表后计算利润。")
    else:
        profit = filtered.groupby(
            ["月份", "产品SKU"]
        ).agg(
            销售额=("销售额", "sum"),
            销量=("销量", "sum")
        ).reset_index()

        profit = profit.merge(
            cost, on="产品SKU", how="left"
        )

        missing_cost = profit[
            profit["产品成本价"].isna()
            | profit["头程运费"].isna()
        ]["产品SKU"].unique().tolist()

        if missing_cost:
            st.error(
                "以下 SKU 缺少成本或头程数据，利润结果不能完整计算："
                + "、".join(missing_cost[:30])
            )

        profit["采购成本"] = (
            profit["销量"] * profit["产品成本价"]
        )
        profit["头程总额"] = (
            profit["销量"] * profit["头程运费"]
        )

        if not rtv.empty:
            rp = rtv_filtered[
                rtv_filtered["订单月份"].isin(selected_months)
            ].groupby(
                ["订单月份", "产品SKU"]
            )["退货金额"].sum().reset_index().rename(
                columns={"订单月份": "月份"}
            )
            profit = profit.merge(
                rp, on=["月份", "产品SKU"], how="left"
            )
        else:
            profit["退货金额"] = 0

        profit["退货金额"] = profit["退货金额"].fillna(0)

        if not ads.empty:
            ap = ads_filtered[
                ads_filtered["月份"].isin(selected_months)
            ].groupby(
                ["月份", "SKU"]
            )["Spend"].sum().reset_index().rename(
                columns={"SKU": "产品SKU", "Spend": "广告花费"}
            )
            profit = profit.merge(
                ap, on=["月份", "产品SKU"], how="left"
            )
        else:
            profit["广告花费"] = 0

        profit["广告花费"] = profit["广告花费"].fillna(0)

        profit["退货率"] = safe_div(
            profit["退货金额"], profit["销售额"]
        )
        profit["广告花费率"] = safe_div(
            profit["广告花费"], profit["销售额"]
        )

        profit["固定费用"] = profit["销售额"] * fixed_fee
        profit["其他费用"] = profit["销售额"] * extra_fee

        profit["利润额"] = (
            profit["销售额"]
            - profit["采购成本"]
            - profit["头程总额"]
            - profit["销售额"] * profit["退货率"]
            - profit["销售额"] * profit["广告花费率"]
            - profit["固定费用"]
            - profit["其他费用"]
        )

        profit["利润率"] = safe_div(
            profit["利润额"], profit["销售额"]
        )
        profit["采购成本率"] = safe_div(
            profit["采购成本"], profit["销售额"]
        )
        profit["头程费率"] = safe_div(
            profit["头程总额"], profit["销售额"]
        )
        profit["总成本率"] = 1 - profit["利润率"]

        profit["考核结果"] = np.where(
            profit["利润率"] >= target_margin,
            "达标", "未达标"
        )

        # 汇总必须先合计金额，再计算比率
        valid = profit.dropna(
            subset=["采购成本", "头程总额", "利润额"]
        ).copy()

        total_sales = valid["销售额"].sum()
        total_profit = valid["利润额"].sum()
        total_purchase = valid["采购成本"].sum()
        total_freight = valid["头程总额"].sum()

        kpis([
            ("销售额", money(total_sales)),
            ("利润额", money(total_profit)),
            ("整体利润率", percent(safe_div(total_profit, total_sales))),
            ("采购成本率", percent(safe_div(total_purchase, total_sales))),
            ("头程费率", percent(safe_div(total_freight, total_sales)))
        ])

        monthly_profit = valid.groupby("月份").agg(
            销售额=("销售额", "sum"),
            利润额=("利润额", "sum"),
            采购成本=("采购成本", "sum"),
            头程总额=("头程总额", "sum"),
            退货金额=("退货金额", "sum"),
            广告花费=("广告花费", "sum"),
            固定费用=("固定费用", "sum"),
            其他费用=("其他费用", "sum")
        ).reset_index()

        monthly_profit["利润率"] = safe_div(
            monthly_profit["利润额"], monthly_profit["销售额"]
        )
        monthly_profit["采购成本率"] = safe_div(
            monthly_profit["采购成本"], monthly_profit["销售额"]
        )
        monthly_profit["头程费率"] = safe_div(
            monthly_profit["头程总额"], monthly_profit["销售额"]
        )
        monthly_profit["广告费率"] = safe_div(
            monthly_profit["广告花费"], monthly_profit["销售额"]
        )
        monthly_profit["退货费率"] = safe_div(
            monthly_profit["退货金额"], monthly_profit["销售额"]
        )

        for metric in [
            "销售额", "利润额", "利润率",
            "采购成本率", "头程费率", "广告费率", "退货费率"
        ]:
            bar(
                monthly_profit, "月份", metric,
                f"月度{metric}趋势"
            )

        st.subheader("SKU 利润率明细")
        st.dataframe(
            profit.sort_values(["月份", "利润率"]),
            use_container_width=True,
            hide_index=True
        )

        st.subheader("单个 SKU 利润变化")
        profit_skus = sorted(profit["产品SKU"].unique())
        selected_profit_sku = st.selectbox(
            "搜索 SKU 利润", profit_skus
        )
        one = profit[
            profit["产品SKU"] == selected_profit_sku
        ].sort_values("月份")

        bar(one, "月份", "利润额", "SKU 月度利润额")
        bar(one, "月份", "利润率", "SKU 月度利润率")

        st.subheader("利润率考核")
        status = profit.groupby("考核结果")[
            "产品SKU"
        ].count().reset_index(name="SKU月份记录数")

        fig = px.pie(
            status,
            names="考核结果",
            values="SKU月份记录数",
            title="利润率达标情况（按 SKU-月份记录）"
        )
        st.plotly_chart(fig, use_container_width=True)

        download(profit, "sku_profit.csv", "download_profit")

st.divider()
st.caption(
    "数据来源：销售、RTV、产品成本、广告四张 Excel。"
    "本系统为经营分析模型，正式财务结算请以实际 Remittance 为准。"
)
