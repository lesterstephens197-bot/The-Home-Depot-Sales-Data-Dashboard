
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="多维电商业务数据看板",
    page_icon="📊",
    layout="wide"
)
st.title("📊 多维电商业务智能分析看板")


# =========================================================
# 通用函数
# =========================================================

@st.cache_data
def load_excel(file):
    df = pd.read_excel(file)
    df.columns = df.columns.astype(str).str.strip()
    return df


def find_col(df, names):
    def norm(x):
        return "".join(str(x).lower().split()).replace("_", "").replace("-", "")
    lookup = {norm(c): c for c in df.columns}
    for name in names:
        if norm(name) in lookup:
            return lookup[norm(name)]
    return None


def to_num(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip(),
        errors="coerce"
    )


def pct(n, d):
    a = np.asarray(n, dtype=float)
    b = np.asarray(d, dtype=float)
    return np.divide(
        a * 100,
        b,
        out=np.full(np.broadcast_shapes(a.shape, b.shape), np.nan),
        where=b != 0
    )


def show_table(df):
    config = {}
    for c in df.columns:
        if "(%)" in str(c):
            config[c] = st.column_config.NumberColumn(
                c.replace("(%)", ""),
                format="%.2f%%"
            )
        elif "率" in str(c) and pd.api.types.is_numeric_dtype(df[c]):
            config[c] = st.column_config.NumberColumn(
                c, format="%.2f%%"
            )
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=config
    )


def bar(df, x, y, title, color=None):
    if df.empty:
        st.info("暂无数据")
        return
    fig = px.bar(
        df, x=x, y=y, color=color,
        barmode="group", title=title
    )
    fig.update_layout(
        xaxis_type="category",
        xaxis_title="",
        yaxis_title=y
    )
    st.plotly_chart(fig, use_container_width=True)


def safe_month(series):
    return pd.to_datetime(
        series, errors="coerce"
    ).dt.strftime("%Y-%m")


def monthly_return_table(sales_df, return_df, date_col):
    s = (
        sales_df.groupby(["Month", "产品SKU"], dropna=False)
        .agg(
            销售件数=("Quantity", "sum"),
            销售金额=("Total Cost", "sum")
        )
        .reset_index()
        .rename(columns={"Month": "月份"})
    )

    r = (
        return_df.groupby([date_col, "产品SKU"], dropna=False)
        .agg(
            退货件数=("QTY", "sum"),
            退货金额=("Total Cost", "sum"),
            扣款金额=("总扣款", "sum")
        )
        .reset_index()
        .rename(columns={date_col: "月份"})
    )

    result = s.merge(
        r, on=["月份", "产品SKU"], how="outer"
    )

    cols = [
        "销售件数", "销售金额",
        "退货件数", "退货金额", "扣款金额"
    ]
    result[cols] = result[cols].fillna(0)

    result["数量退货率(%)"] = pct(
        result["退货件数"], result["销售件数"]
    )
    result["金额退货率(%)"] = pct(
        result["退货金额"], result["销售金额"]
    )
    return result.sort_values(["月份", "产品SKU"])


# =========================================================
# 数据上传
# =========================================================

st.sidebar.header("📁 数据源上传")

sf = st.sidebar.file_uploader(
    "1. 销售数据", type=["xlsx", "xls"]
)
rf = st.sidebar.file_uploader(
    "2. RTV退货数据", type=["xlsx", "xls"]
)
cf = st.sidebar.file_uploader(
    "3. 产品成本表", type=["xlsx", "xls"]
)
af = st.sidebar.file_uploader(
    "4. 广告数据", type=["xlsx", "xls"]
)

if not all([sf, rf, cf, af]):
    st.info("请上传四份 Excel 文件。")
    st.stop()

sales, rtv, cost, ads = [
    load_excel(f) for f in [sf, rf, cf, af]
]

required = {
    "销售表": (
        sales,
        ["产品SKU", "Order Date", "Quantity", "Total Cost"]
    ),
    "RTV表": (
        rtv,
        ["产品SKU", "Order Date", "RTV Date",
         "QTY", "Total Cost", "总扣款"]
    )
}

for name, (df, cols) in required.items():
    missing = [c for c in cols if c not in df.columns]
    if missing:
        st.error(f"{name}缺少字段：{missing}")
        st.write("实际字段：", list(df.columns))
        st.stop()

for df in [sales, rtv]:
    df["产品SKU"] = (
        df["产品SKU"].astype("string").str.strip()
    )

for c in ["Quantity", "Total Cost"]:
    sales[c] = to_num(sales[c]).fillna(0)

for c in ["QTY", "Total Cost", "总扣款"]:
    rtv[c] = to_num(rtv[c]).fillna(0)

sales["Order Date"] = pd.to_datetime(
    sales["Order Date"], errors="coerce"
)
rtv["Order Date"] = pd.to_datetime(
    rtv["Order Date"], errors="coerce"
)
rtv["RTV Date"] = pd.to_datetime(
    rtv["RTV Date"], errors="coerce"
)

sales["Month"] = safe_month(sales["Order Date"])
rtv["Order_Month"] = safe_month(rtv["Order Date"])
rtv["RTV_Month"] = safe_month(rtv["RTV Date"])

for c in ["产品名称", "品牌", "运营"]:
    if c not in sales:
        sales[c] = "未填写"

if "Customer Order Number" not in sales:
    sales["Customer Order Number"] = sales.index.astype(str)

for c in ["Spend", "SPA Revenue", "Clicks", "Impressions"]:
    if c not in ads:
        ads[c] = 0
    ads[c] = to_num(ads[c]).fillna(0)

all_skus = sorted(
    set(sales["产品SKU"].dropna().tolist())
    | set(rtv["产品SKU"].dropna().tolist())
)

tabs = st.tabs([
    "1. 销售总看板",
    "2. 产品SKU看板",
    "3. 运营维度看板",
    "4. 退货与扣款看板",
    "5. 广告数据分析看板",
    "6. 利润率与成本率看板"
])


# =========================================================
# 看板一：销售总览
# =========================================================

with tabs[0]:
    st.header("📈 整体销售数据")

    revenue = sales["Total Cost"].sum()
    qty = sales["Quantity"].sum()
    orders = sales["Customer Order Number"].nunique()

    valid_dates = sales["Order Date"].dropna()
    days = (
        (valid_dates.max() - valid_dates.min()).days + 1
        if len(valid_dates) else 0
    )

    values = [
        f"${revenue:,.2f}",
        f"{qty:,.0f}",
        f"{orders:,}",
        f"${revenue/orders:,.2f}" if orders else "—",
        f"{qty/days:,.2f}" if days else "—"
    ]

    labels = [
        "总销售额", "总销量", "总订单数",
        "平均客单价", "日均销量"
    ]

    for c, label, value in zip(
        st.columns(5), labels, values
    ):
        c.metric(label, value)

    monthly = (
        sales.groupby("Month")
        .agg(
            总销售额=("Total Cost", "sum"),
            总销量=("Quantity", "sum"),
            总订单数=("Customer Order Number", "nunique")
        )
        .reset_index()
    )

    monthly["平均客单价"] = np.where(
        monthly["总订单数"] > 0,
        monthly["总销售额"] / monthly["总订单数"],
        np.nan
    )

    monthly["日均销量"] = [
        q / pd.Period(m).days_in_month
        for q, m in zip(monthly["总销量"], monthly["Month"])
    ]

    metric = st.selectbox(
        "选择月度指标",
        ["总销售额", "总销量", "总订单数",
         "平均客单价", "日均销量"]
    )

    bar(monthly, "Month", metric, f"月度{metric}")
    show_table(monthly)


# =========================================================
# 看板二：SKU销售分析
# =========================================================

with tabs[1]:
    st.header("📦 SKU销售分析")

    sm = (
        sales.groupby(["Month", "产品SKU"])
        .agg(
            销售额=("Total Cost", "sum"),
            销量=("Quantity", "sum"),
            订单数=("Customer Order Number", "nunique"),
            有销售天数=("Order Date", "nunique")
        )
        .reset_index()
    )

    sm["日均销量"] = np.where(
        sm["有销售天数"] > 0,
        sm["销量"] / sm["有销售天数"],
        np.nan
    )

    sm["销售额占比(%)"] = pct(
        sm["销售额"],
        sm.groupby("Month")["销售额"].transform("sum")
    )

    sm["月度排名"] = (
        sm.groupby("Month")["销售额"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    sm["SKU等级"] = pd.cut(
        sm.groupby("Month")["销售额"]
        .rank(ascending=False, pct=True),
        [0, .2, .5, .8, 1],
        labels=["A", "B", "C", "D"],
        include_lowest=True
    )

    show_table(sm.sort_values(["Month", "月度排名"]))

    sku_options = sorted(sales["产品SKU"].dropna().unique())
    selected = st.selectbox(
        "搜索单个SKU", sku_options, key="sales_sku"
    )

    sd = sm[sm["产品SKU"] == selected]
    a, b = st.columns(2)

    with a:
        bar(sd, "Month", "销量", "SKU月度销量")
    with b:
        bar(sd, "Month", "销售额", "SKU月度销售额")


# =========================================================
# 看板三：运营分析
# =========================================================

with tabs[2]:
    st.header("👥 运营人员月度销售")

    op = (
        sales.groupby(["Month", "运营"])
        .agg(
            销售额=("Total Cost", "sum"),
            销量=("Quantity", "sum"),
            订单数=("Customer Order Number", "nunique")
        )
        .reset_index()
    )

    show_table(op)
    bar(op, "Month", "销售额", "运营月度销售额", "运营")


# =========================================================
# 看板四：退货与扣款
# =========================================================

with tabs[3]:
    st.header("🔄 退货与扣款分析")

    chosen = st.multiselect(
        "筛选产品SKU（留空代表全部）",
        all_skus,
        key="rtv_filter"
    )

    ss = (
        sales[sales["产品SKU"].isin(chosen)].copy()
        if chosen else sales.copy()
    )
    rr = (
        rtv[rtv["产品SKU"].isin(chosen)].copy()
        if chosen else rtv.copy()
    )

    sq = ss["Quantity"].sum()
    sa = ss["Total Cost"].sum()
    rq = rr["QTY"].sum()
    ra = rr["Total Cost"].sum()
    ded = rr["总扣款"].sum()

    values = [
        f"{rq:,.0f}",
        f"${ra:,.2f}",
        f"${ded:,.2f}",
        f"{rq/sq*100:.2f}%" if sq else "—",
        f"{ra/sa*100:.2f}%" if sa else "—"
    ]

    for c, label, value in zip(
        st.columns(5),
        ["退货件数", "退货金额", "总扣款",
         "数量退货率", "金额退货率"],
        values
    ):
        c.metric(label, value)

    sub = st.tabs([
        "1. SKU退货率排行榜",
        "2. 退货原因占比",
        "3. Order Date视角",
        "4. RTV Date视角"
    ])

    with sub[0]:
        s = (
            ss.groupby("产品SKU")
            .agg(
                销售件数=("Quantity", "sum"),
                销售金额=("Total Cost", "sum")
            )
            .reset_index()
        )

        r = (
            rr.groupby("产品SKU")
            .agg(
                退货件数=("QTY", "sum"),
                退货金额=("Total Cost", "sum"),
                扣款金额=("总扣款", "sum")
            )
            .reset_index()
        )

        ranking = s.merge(
            r, on="产品SKU", how="outer"
        )

        for c in [
            "销售件数", "销售金额",
            "退货件数", "退货金额", "扣款金额"
        ]:
            ranking[c] = ranking[c].fillna(0)

        ranking["数量退货率(%)"] = pct(
            ranking["退货件数"], ranking["销售件数"]
        )
        ranking["金额退货率(%)"] = pct(
            ranking["退货金额"], ranking["销售金额"]
        )

        rank_by = st.selectbox(
            "排名依据",
            ["数量退货率(%)", "金额退货率(%)",
             "退货件数", "扣款金额"]
        )

        minimum = st.number_input(
            "最少销售件数",
            min_value=0, value=10, step=1
        )

        ranking = (
            ranking[ranking["销售件数"] >= minimum]
            .sort_values(rank_by, ascending=False)
        )

        show_table(ranking)
        bar(
            ranking.head(15),
            "产品SKU", rank_by, "SKU退货Top 15"
        )

    with sub[1]:
        reason = find_col(
            rr,
            ["Reason", "Return Reason", "RTV Reason",
             "Reason Description", "退货原因", "退货理由"]
        )

        if reason is None:
            st.warning("RTV表未识别到退货原因字段。")
            st.write("实际字段：", list(rr.columns))
        else:
            x = rr.copy()
            x[reason] = x[reason].fillna("未填写").astype(str)

            reasons = (
                x.groupby(reason)
                .agg(
                    退货件数=("QTY", "sum"),
                    退货金额=("Total Cost", "sum"),
                    扣款金额=("总扣款", "sum")
                )
                .reset_index()
            )

            measure = st.radio(
                "占比依据",
                ["退货件数", "退货金额", "扣款金额"],
                horizontal=True
            )

            reasons["占比(%)"] = pct(
                reasons[measure], reasons[measure].sum()
            )

            show_table(reasons)

            if reasons[measure].sum() > 0:
                fig = px.pie(
                    reasons, names=reason,
                    values=measure, hole=.4,
                    title="退货原因占比"
                )
                st.plotly_chart(
                    fig, use_container_width=True
                )

    views = [
        (sub[2], "Order_Month", "Order Date"),
        (sub[3], "RTV_Month", "RTV Date")
    ]

    for tab, month_col, title in views:
        with tab:
            st.subheader(f"{title} 月度退货分析")

            if month_col == "RTV_Month":
                st.info(
                    "RTV Date口径：当月退货 ÷ 当月销售。"
                    "由于退货可能来自历史订单，"
                    "该比率可能超过100%。"
                )
            else:
                st.info(
                    "Order Date口径：退货归属原订单月份。"
                    "近期月份可能受退货滞后影响。"
                )

            detail = monthly_return_table(
                ss, rr, month_col
            )

            monthly = (
                detail.groupby("月份", dropna=False)
                [["销售件数", "销售金额", "退货件数",
                  "退货金额", "扣款金额"]]
                .sum()
                .reset_index()
            )

            monthly["数量退货率(%)"] = pct(
                monthly["退货件数"], monthly["销售件数"]
            )
            monthly["金额退货率(%)"] = pct(
                monthly["退货金额"], monthly["销售金额"]
            )

            st.subheader("月度汇总")
            show_table(monthly)

            a, b = st.columns(2)
            with a:
                bar(
                    monthly, "月份", "数量退货率(%)",
                    "月度数量退货率"
                )
            with b:
                bar(
                    monthly, "月份", "金额退货率(%)",
                    "月度金额退货率"
                )

            st.subheader("SKU × 月份明细")
            show_table(detail)


# =========================================================
# 看板五：广告数据
# =========================================================

with tabs[4]:
    st.header("🎯 广告数据分析")

    spend = ads["Spend"].sum()
    rev = ads["SPA Revenue"].sum()

    a, b, c = st.columns(3)
    a.metric("广告花费", f"${spend:,.2f}")
    b.metric("广告销售额", f"${rev:,.2f}")
    c.metric(
        "ROAS", f"{rev/spend:.2f}" if spend else "—"
    )

    if "Campaign Name" in ads:
        camp = (
            ads.groupby("Campaign Name")
            .agg(
                广告花费=("Spend", "sum"),
                广告销售额=("SPA Revenue", "sum"),
                点击量=("Clicks", "sum")
            )
            .reset_index()
        )

        camp["ROAS"] = np.where(
            camp["广告花费"] > 0,
            camp["广告销售额"] / camp["广告花费"],
            np.nan
        )

        show_table(camp)
        bar(
            camp.nlargest(10, "广告花费"),
            "Campaign Name", "广告花费",
            "广告花费Top 10"
        )


# =========================================================
# 看板六：利润率与成本率
# 核心：先统一计算全部SKU，再筛选
# =========================================================

with tabs[5]:
    st.header("💰 利润率与成本率深度分析")
    st.markdown("**利润率目标：不低于 13%**")

    st.caption(
        "所有SKU和月份采用同一套利润计算公式。"
        "先计算全量利润底表，再根据SKU筛选汇总。"
    )

    # -----------------------------------------------------
    # 1. 成本字段识别
    # -----------------------------------------------------

    sku_guess = find_col(
        cost,
        ["SKU", "产品SKU", "Vendor Part #",
         "Vendor Part", "产品型号", "型号"]
    )

    unit_guess = find_col(
        cost,
        ["产品成本价", "采购成本价", "单位成本",
         "成本价", "Product Cost", "Unit Cost",
         "采购价", "产品成本"]
    )

    freight_guess = find_col(
        cost,
        ["头程运费", "头程成本", "单位头程",
         "单位头程运费", "Freight Cost", "头程"]
    )

    options = ["--请选择--"] + list(cost.columns)

    def field_select(label, guess, key):
        index = options.index(guess) if guess in options else 0
        value = st.selectbox(
            label, options, index=index, key=key
        )
        return None if value == "--请选择--" else value

    with st.expander("成本表字段设置", expanded=False):
        a, b, c = st.columns(3)
        with a:
            sku_col = field_select(
                "SKU列", sku_guess, "cost_sku"
            )
        with b:
            unit_col = field_select(
                "单位采购成本列", unit_guess, "cost_unit"
            )
        with c:
            freight_col = field_select(
                "单位头程列", freight_guess, "cost_freight"
            )

        st.dataframe(
            cost.head(5), use_container_width=True
        )

    if not sku_col or not unit_col:
        st.warning(
            "请在成本表字段设置中选择SKU列和单位采购成本列。"
        )
        st.stop()

    # -----------------------------------------------------
    # 2. 规范成本表
    # -----------------------------------------------------

    cc = pd.DataFrame({
        "产品SKU": cost[sku_col].astype("string").str.strip(),
        "单位采购成本": to_num(cost[unit_col])
    })

    if freight_col:
        cc["单位头程"] = to_num(cost[freight_col])
    else:
        cc["单位头程"] = 0.0

    cc = cc.dropna(subset=["产品SKU"])
    cc = cc[cc["产品SKU"] != ""]

    duplicate_skus = cc.loc[
        cc["产品SKU"].duplicated(keep=False),
        "产品SKU"
    ].unique().tolist()

    if duplicate_skus:
        st.warning(
            f"成本表存在 {len(duplicate_skus)} 个重复SKU，"
            "当前按第一条记录匹配，请核对成本。"
        )

    cc = cc.drop_duplicates(
        subset=["产品SKU"], keep="first"
    )

    # -----------------------------------------------------
    # 3. 全量销售与成本关联
    # -----------------------------------------------------

    full = sales.merge(
        cc,
        on="产品SKU",
        how="left",
        validate="many_to_one"
    )

    full["成本是否完整"] = (
        full["单位采购成本"].notna()
        & full["单位头程"].notna()
    )

    full["采购成本"] = (
        full["Quantity"] * full["单位采购成本"]
    )
    full["头程成本"] = (
        full["Quantity"] * full["单位头程"]
    )

    # -----------------------------------------------------
    # 4. 统一全量广告费率
    # 注意：不能用筛选后SKU的销售额做分母
    # -----------------------------------------------------

    all_revenue = sales["Total Cost"].sum()
    all_ad_spend = ads["Spend"].sum()

    global_ad_rate = (
        all_ad_spend / all_revenue
        if all_revenue > 0 else 0
    )

    st.sidebar.header("利润模型参数")

    platform_rate = st.sidebar.number_input(
        "平台费率(%)",
        min_value=0.0,
        value=3.25,
        step=0.25,
        key="platform_rate"
    ) / 100

    other_rate = st.sidebar.number_input(
        "其他费用率(%)",
        min_value=0.0,
        value=2.0,
        step=0.25,
        key="other_rate"
    ) / 100

    # -----------------------------------------------------
    # 5. 全量SKU × 月份销售底表
    # -----------------------------------------------------

    base = (
        full.groupby(
            ["Month", "产品SKU"], dropna=False
        )
        .agg(
            销售额=("Total Cost", "sum"),
            销量=("Quantity", "sum"),
            采购成本=("采购成本", "sum"),
            头程成本=("头程成本", "sum"),
            成本完整=("成本是否完整", "all")
        )
        .reset_index()
    )

    # -----------------------------------------------------
    # 6. 退货按原订单月份 + SKU关联
    # 不再引用退货看板筛选后的rtv_rate_amt
    # -----------------------------------------------------

    ret = (
        rtv.groupby(
            ["Order_Month", "产品SKU"], dropna=False
        )
        .agg(
            退货商品金额=("Total Cost", "sum"),
            退货件数=("QTY", "sum"),
            RTV扣款金额=("总扣款", "sum")
        )
        .reset_index()
        .rename(columns={"Order_Month": "Month"})
    )

    base = base.merge(
        ret,
        on=["Month", "产品SKU"],
        how="left",
        validate="one_to_one"
    )

    for col in [
        "退货商品金额", "退货件数", "RTV扣款金额"
    ]:
        base[col] = base[col].fillna(0)

    # 退货商品金额作为估算退货成本项
    # 不与总扣款重复扣除
    base["退货成本"] = base["退货商品金额"]

    # -----------------------------------------------------
    # 7. 统一费用分摊
    # -----------------------------------------------------

    base["广告成本"] = (
        base["销售额"] * global_ad_rate
    )

    base["平台扣点"] = (
        base["销售额"] * platform_rate
    )

    base["其他费用"] = (
        base["销售额"] * other_rate
    )

    cost_cols = [
        "采购成本",
        "头程成本",
        "退货成本",
        "广告成本",
        "平台扣点",
        "其他费用"
    ]

    base["总成本"] = base[cost_cols].sum(axis=1)

    base["利润额"] = (
        base["销售额"] - base["总成本"]
    )

    # 成本缺失的SKU不生成有效利润
    base.loc[
        ~base["成本完整"],
        ["总成本", "利润额"]
    ] = np.nan

    base["利润率(%)"] = pct(
        base["利润额"], base["销售额"]
    )

    base["成本率(%)"] = pct(
        base["总成本"], base["销售额"]
    )

    base["采购成本率(%)"] = pct(
        base["采购成本"], base["销售额"]
    )

    base["预警状态"] = np.select(
        [
            ~base["成本完整"],
            base["销售额"] <= 0,
            base["利润率(%)"] < 10,
            base["利润率(%)"] < 13
        ],
        [
            "成本缺失",
            "无有效销售额",
            "严重预警",
            "低于13%"
        ],
        default="达标"
    )

    # -----------------------------------------------------
    # 8. SKU产品信息
    # -----------------------------------------------------

    product_info = (
        sales[["产品SKU", "产品名称", "品牌"]]
        .drop_duplicates(subset=["产品SKU"])
    )

    base = base.merge(
        product_info,
        on="产品SKU",
        how="left",
        validate="many_to_one"
    )

    # -----------------------------------------------------
    # 9. 先完成全量底表，再筛选
    # -----------------------------------------------------

    sku_options = sorted(
        base["产品SKU"].dropna().unique().tolist()
    )

    selected_skus = st.multiselect(
        "筛选产品SKU（留空=全部SKU）",
        sku_options,
        key="profit_filter"
    )

    filtered = (
        base[base["产品SKU"].isin(selected_skus)].copy()
        if selected_skus else base.copy()
    )

    # -----------------------------------------------------
    # 10. 成本匹配检查
    # -----------------------------------------------------

    missing_cost = (
        filtered.loc[
            ~filtered["成本完整"],
            "产品SKU"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if missing_cost:
        st.error(
            f"发现 {len(missing_cost)} 个SKU成本缺失。"
            "这些SKU不计入有效利润率，"
            "请核实成本表。"
        )
        with st.expander("查看成本缺失SKU"):
            st.write(missing_cost)

    valid = filtered[
        filtered["成本完整"]
        & (filtered["销售额"] > 0)
    ].copy()

    # -----------------------------------------------------
    # 11. 整体利润指标
    # -----------------------------------------------------

    revenue = valid["销售额"].sum()
    profit = valid["利润额"].sum()
    total_cost = valid["总成本"].sum()

    margin = (
        profit / revenue * 100
        if revenue > 0 else np.nan
    )

    cost_rate = (
        total_cost / revenue * 100
        if revenue > 0 else np.nan
    )

    a, b, c, d = st.columns(4)

    a.metric("有效销售额", f"${revenue:,.2f}")
    b.metric("估算利润额", f"${profit:,.2f}")
    c.metric(
        "综合利润率",
        f"{margin:.2f}%" if pd.notna(margin) else "—"
    )
    d.metric(
        "综合成本率",
        f"{cost_rate:.2f}%" if pd.notna(cost_rate) else "—"
    )

    if pd.notna(margin):
        if margin < 10:
            st.error(
                f"严重预警：利润率 {margin:.2f}%，"
                "低于13%目标。"
            )
        elif margin < 13:
            st.warning(
                f"利润率 {margin:.2f}%，未达到13%目标。"
            )
        else:
            st.success(
                f"利润率 {margin:.2f}%，达到13%目标。"
            )

    st.caption(
        f"固定广告分摊率：{global_ad_rate*100:.2f}%；"
        f"当前有效SKU：{valid['产品SKU'].nunique()}；"
        f"成本缺失SKU：{len(missing_cost)}。"
    )

    # -----------------------------------------------------
    # 12. 月度利润汇总
    # -----------------------------------------------------

    st.subheader("📅 每月利润率与成本率")

    monthly = (
        valid.groupby("Month")
        .agg(
            月销售额=("销售额", "sum"),
            月销量=("销量", "sum"),
            月采购成本=("采购成本", "sum"),
            月头程运费=("头程成本", "sum"),
            退货成本=("退货成本", "sum"),
            广告成本=("广告成本", "sum"),
            平台扣点=("平台扣点", "sum"),
            其他费用=("其他费用", "sum"),
            月总成本=("总成本", "sum"),
            月利润额=("利润额", "sum")
        )
        .reset_index()
        .sort_values("Month")
    )

    monthly["利润率(%)"] = pct(
        monthly["月利润额"], monthly["月销售额"]
    )
    monthly["成本率(%)"] = pct(
        monthly["月总成本"], monthly["月销售额"]
    )
    monthly["采购成本率(%)"] = pct(
        monthly["月采购成本"], monthly["月销售额"]
    )

    monthly["目标差距(百分点)"] = (
        monthly["利润率(%)"] - 13
    )

    monthly["状态评估"] = np.where(
        monthly["利润率(%)"] >= 13,
        "达标",
        "低于13%"
    )

    show_table(monthly)

    # -----------------------------------------------------
    # 13. 月度利润率趋势
    # -----------------------------------------------------

    st.subheader("月度利润率趋势（目标13%）")

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=monthly["Month"],
            y=monthly["利润率(%)"],
            name="利润率",
            marker_color=[
                "#198754" if v >= 13 else "#dc3545"
                for v in monthly["利润率(%)"]
            ],
            text=[
                f"{v:.2f}%"
                for v in monthly["利润率(%)"]
            ],
            textposition="outside"
        )
    )

    fig.add_hline(
        y=13,
        line_color="red",
        line_dash="dash",
        annotation_text="目标13%"
    )

    fig.update_layout(
        xaxis_type="category",
        yaxis_title="利润率 (%)"
    )

    st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------------------------
    # 14. 月度成本率与利润额
    # -----------------------------------------------------

    a, b = st.columns(2)

    with a:
        bar(
            monthly, "Month", "成本率(%)",
            "每月总成本率"
        )

    with b:
        bar(
            monthly, "Month", "采购成本率(%)",
            "每月采购成本率"
        )

    bar(
        monthly, "Month", "月利润额",
        "每月利润额"
    )

    # -----------------------------------------------------
    # 15. 月度成本结构
    # -----------------------------------------------------

    st.subheader("月度成本结构")

    structure = monthly.melt(
        id_vars="Month",
        value_vars=[
            "月采购成本",
            "月头程运费",
            "退货成本",
            "广告成本",
            "平台扣点",
            "其他费用"
        ],
        var_name="成本类别",
        value_name="金额"
    )

    fig = px.bar(
        structure,
        x="Month",
        y="金额",
        color="成本类别",
        barmode="stack",
        title="月度各项成本构成"
    )

    st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------------------------
    # 16. SKU利润明细
    # -----------------------------------------------------

    st.subheader("📦 SKU利润率排行榜")

    sku_profit = (
        valid.groupby(
            ["产品SKU", "产品名称", "品牌"],
            dropna=False
        )
        .agg(
            销售额=("销售额", "sum"),
            总销量=("销量", "sum"),
            采购成本=("采购成本", "sum"),
            头程运费=("头程成本", "sum"),
            退货成本=("退货成本", "sum"),
            广告成本=("广告成本", "sum"),
            平台扣点=("平台扣点", "sum"),
            其他费用=("其他费用", "sum"),
            总成本=("总成本", "sum"),
            利润额=("利润额", "sum")
        )
        .reset_index()
    )

    sku_profit["利润率(%)"] = pct(
        sku_profit["利润额"], sku_profit["销售额"]
    )

    sku_profit["成本率(%)"] = pct(
        sku_profit["总成本"], sku_profit["销售额"]
    )

    sku_profit["预警状态"] = np.select(
        [
            sku_profit["利润率(%)"] < 10,
            sku_profit["利润率(%)"] < 13
        ],
        ["严重预警", "低于13%"],
        default="达标"
    )

    show_table(
        sku_profit.sort_values(
            "利润率(%)", ascending=True
        )
    )

    # -----------------------------------------------------
    # 17. SKU × 月份利润明细
    # -----------------------------------------------------

    st.subheader("SKU × 月份利润明细")

    detail_cols = [
        "Month", "产品SKU", "产品名称", "品牌",
        "销售额", "销量",
        "采购成本", "头程成本",
        "退货成本", "广告成本",
        "平台扣点", "其他费用",
        "总成本", "利润额",
        "利润率(%)", "成本率(%)",
        "预警状态"
    ]

    show_table(
        filtered[detail_cols].sort_values(
            ["Month", "产品SKU"]
        )
    )

    # -----------------------------------------------------
    # 18. 13%利润率预警
    # -----------------------------------------------------

    alerts = valid[
        valid["利润率(%)"] < 13
    ].sort_values(
        ["Month", "利润率(%)"]
    )

    st.subheader(
        f"利润率低于13%的SKU月度预警（{len(alerts)}条）"
    )

    show_table(
        alerts[
            [
                "Month", "产品SKU",
                "销售额", "利润额",
                "利润率(%)", "成本率(%)",
                "预警状态"
            ]
        ]
    )

    # -----------------------------------------------------
    # 19. 数据一致性核对
    # -----------------------------------------------------

    st.subheader("数据一致性检查")

    check_revenue = (
        valid["销售额"].sum()
        - sku_profit["销售额"].sum()
    )

    check_profit = (
        valid["利润额"].sum()
        - sku_profit["利润额"].sum()
    )

    check_month_revenue = (
        valid["销售额"].sum()
        - monthly["月销售额"].sum()
    )

    check_month_profit = (
        valid["利润额"].sum()
        - monthly["月利润额"].sum()
    )

    checks = pd.DataFrame({
        "检查项目": [
            "底表与SKU汇总销售额差异",
            "底表与SKU汇总利润额差异",
            "底表与月度汇总销售额差异",
            "底表与月度汇总利润额差异"
        ],
        "差异金额": [
            check_revenue,
            check_profit,
            check_month_revenue,
            check_month_profit
        ]
    })

    checks["结果"] = np.where(
        checks["差异金额"].abs() < 0.01,
        "通过",
        "异常"
    )

    show_table(checks)

    if (checks["结果"] == "通过").all():
        st.success(
            "数据核对通过：SKU明细、月度汇总"
            "与统一利润底表一致。"
        )
    else:
        st.error(
            "数据核对存在差异，请检查计算明细。"
        )

    st.caption(
        "利润为估算口径：采购和头程来自SKU成本表；"
        "广告按全量销售额比例分摊；"
        "退货按原订单月份及SKU归属。"
        "缺失成本的SKU不参与有效利润汇总。"
        "退货商品金额与RTV总扣款不重复扣减。"
    )
