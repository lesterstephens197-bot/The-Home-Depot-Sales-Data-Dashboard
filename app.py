import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# 页面基础配置
st.set_page_config(
    page_title="多维电商业务数据看板", page_icon="📊", layout="wide"
)

st.title("📊 多维电商业务智能分析看板")
st.markdown(
    "请在下方侧边栏依次上传 **4个核心数据Excel表格**，系统将自动进行列名清洗、容错关联与多维度看板渲染。"
)

# ==================== 1. 文件上传区 ====================
st.sidebar.header("📁 数据源上传")
sales_file = st.sidebar.file_uploader(
    "1. 上传销售数据表 (Excel)", type=["xlsx", "xls"]
)
rtv_file = st.sidebar.file_uploader(
    "2. 上传RTV数据表 (Excel)", type=["xlsx", "xls"]
)
cost_file = st.sidebar.file_uploader(
    "3. 上传产品成本表 (Excel)", type=["xlsx", "xls"]
)
ad_file = st.sidebar.file_uploader(
    "4. 上传广告数据表 (Excel)", type=["xlsx", "xls"]
)


@st.cache_data
def load_data(sales_f, rtv_f, cost_f, ad_f):
  if not (sales_f and rtv_f and cost_f and ad_f):
    return None, None, None, None

  df_sales = pd.read_excel(sales_f)
  df_rtv = pd.read_excel(rtv_f)
  df_cost = pd.read_excel(cost_f)
  df_ad = pd.read_excel(ad_f)

  # 清洗所有表的列名空格，避免 KeyError
  for df in [df_sales, df_rtv, df_cost, df_ad]:
    df.columns = df.columns.astype(str).str.strip()

  # 成本表列名适配容错处理
  cost_col_map = {}
  for col in df_cost.columns:
    if "SKU" in col.upper():
      cost_col_map[col] = "SKU"
    elif "成本" in col:
      cost_col_map[col] = "产品成本价"
    elif "头程" in col:
      cost_col_map[col] = "头程运费"
  df_cost = df_cost.rename(columns=cost_col_map)

  # 数据预处理：统一日期格式
  df_sales["Order Date"] = pd.to_datetime(
      df_sales["Order Date"], errors="coerce"
  )
  df_sales["Month"] = df_sales["Order Date"].dt.to_period("M").astype(str)

  df_rtv["Order Date"] = pd.to_datetime(df_rtv["Order Date"], errors="coerce")
  df_rtv["RTV Date"] = pd.to_datetime(df_rtv["RTV Date"], errors="coerce")
  df_rtv["Order_Month"] = df_rtv["Order Date"].dt.to_period("M").astype(str)
  df_rtv["RTV_Month"] = df_rtv["RTV Date"].dt.to_period("M").astype(str)

  return df_sales, df_rtv, df_cost, df_ad


df_sales, df_rtv, df_cost, df_ad = load_data(
    sales_file, rtv_file, cost_file, ad_file
)

if df_sales is None:
  st.warning("⚠️ 请先在左侧边栏完整上传所有 4 个 Excel 表格以加载所有业务看板。")
else:
  tabs = st.tabs(
      [
          "1. 销售总看板",
          "2. 产品SKU看板",
          "3. 运营维度看板",
          "4. 退货与扣款看板",
          "5. 广告数据分析看板",
          "6. 利润率与成本率看板",
      ]
  )

  # ==================== 看板一：销售数据看板 ====================
  with tabs[0]:
    st.header("📈 整体销售数据分析看板")

    total_sales = df_sales["Total Cost"].sum()
    total_qty = df_sales["Quantity"].sum()
    total_orders = df_sales["Customer Order Number"].nunique()
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0

    min_date = df_sales["Order Date"].min()
    max_date = df_sales["Order Date"].max()
    date_diff = (
        (max_date - min_date).days + 1 if pd.notnull(min_date) else 1
    )
    daily_avg_qty = total_qty / date_diff if date_diff > 0 else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("总销售额 ($)", f"{total_sales:,.2f}")
    col2.metric("总销量 (件)", f"{total_qty:,}")
    col3.metric("总单量 (单)", f"{total_orders:,}")
    col4.metric("平均客单价 ($)", f"{avg_order_value:,.2f}")
    col5.metric("日均销量 (件/天)", f"{daily_avg_qty:,.1f}")

    st.markdown("---")
    st.subheader("月度销售趋势分析")

    monthly_sales = (
        df_sales.groupby("Month")
        .agg(
            总销售额=("Total Cost", "sum"),
            总销量=("Quantity", "sum"),
            总单量=("Customer Order Number", "nunique"),
        )
        .reset_index()
    )
    monthly_sales["平均客单价"] = (
        monthly_sales["总销售额"] / monthly_sales["总单量"]
    )

    days_in_month = (
        df_sales.groupby("Month")["Order Date"]
        .apply(lambda x: (x.max() - x.min()).days + 1)
        .reset_index(name="Days")
    )
    monthly_sales = pd.merge(monthly_sales, days_in_month, on="Month")
    monthly_sales["日均销量"] = monthly_sales["总销量"] / monthly_sales["Days"]

    metric_choice = st.selectbox(
        "选择展示指标图表",
        ["总销售额", "总销量", "总单量", "平均客单价", "日均销量"],
        key="sales_metric",
    )
    fig = px.bar(
        monthly_sales,
        x="Month",
        y=metric_choice,
        text=metric_choice,
        title=f"按月统计 - {metric_choice}柱状趋势图",
        color=metric_choice,
        color_continuous_scale="Blues",
    )
    fig.update_traces(texttemplate="%{text:.2s}", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

  # ==================== 看板二：以产品SKU为维度 ====================
  with tabs[1]:
    st.header("📦 产品 SKU 维度多维分析看板")

    all_skus = sorted(df_sales["产品SKU"].dropna().unique().tolist())
    search_sku = st.selectbox(
        "🔍 请选择或搜索单个产品SKU（查看该SKU详细月度变化趋势）",
        options=all_skus,
    )

    sku_summary = (
        df_sales.groupby(["产品SKU", "产品名称", "品牌", "运营"])
        .agg(
            总销售额=("Total Cost", "sum"),
            总销量=("Quantity", "sum"),
            总订单数=("Customer Order Number", "nunique"),
            有销售天数=("Order Date", "nunique"),
        )
        .reset_index()
    )

    sku_summary["日均销量(件/天)"] = (
        sku_summary["总销量"] / sku_summary["有销售天数"]
    ).fillna(0)
    total_all_sales = sku_summary["总销售额"].sum()
    sku_summary["销售额占比"] = (
        sku_summary["总销售额"] / total_all_sales * 100
        if total_all_sales > 0
        else 0
    )

    sku_summary = sku_summary.sort_values(
        by="总销售额", ascending=False
    ).reset_index(drop=True)
    sku_summary["每月排名"] = sku_summary.index + 1


    def assign_grade(row, total_rows):
      pct = row["每月排名"] / total_rows
      if pct <= 0.2:
        return "A"
      elif pct <= 0.5:
        return "B"
      elif pct <= 0.8:
        return "C"
      else:
        return "D"


    sku_summary["SKU 等级"] = sku_summary.apply(
        lambda r: assign_grade(r, len(sku_summary)), axis=1
    )

    st.dataframe(sku_summary, use_container_width=True)

    st.markdown("---")
    st.subheader(f"📅 单个 SKU [{search_sku}] 的月度变化趋势")

    sku_filtered = df_sales[df_sales["产品SKU"] == search_sku]
    sku_monthly = (
        sku_filtered.groupby("Month")
        .agg(
            月总销售额=("Total Cost", "sum"),
            月总销量=("Quantity", "sum"),
            月总单量=("Customer Order Number", "nunique"),
        )
        .reset_index()
    )

    col_m1, col_m2 = st.columns(2)
    with col_m1:
      fig_sku_qty = px.bar(
          sku_monthly,
          x="Month",
          y="月总销量",
          text="月总销量",
          title=f"SKU: {search_sku} - 逐月销量变化柱状图",
          color_discrete_sequence=["#2b5c8f"],
      )
      fig_sku_qty.update_traces(textposition="outside")
      st.plotly_chart(fig_sku_qty, use_container_width=True)

    with col_m2:
      fig_sku_amt = px.bar(
          sku_monthly,
          x="Month",
          y="月总销售额",
          text="月总销售额",
          title=f"SKU: {search_sku} - 逐月销售额变化柱状图",
          color_discrete_sequence=["#2ca02c"],
      )
      fig_sku_amt.update_traces(
          texttemplate="%{text:.2s}", textposition="outside"
      )
      st.plotly_chart(fig_sku_amt, use_container_width=True)

  # ==================== 看板三：以运营为维度 ====================
  with tabs[2]:
    st.header("👥 运营人员维度销售月度看板")

    operator_monthly = (
        df_sales.groupby(["Month", "运营"])
        .agg(
            总销售额=("Total Cost", "sum"),
            总销量=("Quantity", "sum"),
            总订单数=("Customer Order Number", "nunique"),
        )
        .reset_index()
    )

    st.dataframe(operator_monthly, use_container_width=True)

    fig_op = px.bar(
        operator_monthly,
        x="Month",
        y="总销售额",
        color="运营",
        barmode="group",
        title="各运营人员每月总销售额对比柱状图",
    )
    st.plotly_chart(fig_op, use_container_width=True)

  # ==================== 看板四：退货和扣款数据 ====================
  with tabs[3]:
    st.header("🔄 退货与扣款多维智能看板")

    all_rtv_skus = sorted(df_rtv["产品SKU"].dropna().unique().tolist())
    selected_rtv_sku = st.selectbox(
        "🔍 【退货看板筛选】选择单个产品SKU（选“全部”查看整体退货情况）",
        options=["全部"] + all_rtv_skus,
        key="rtv_sku_filter",
    )

    df_rtv_f = df_rtv.copy()
    df_sales_f = df_sales.copy()
    if selected_rtv_sku != "全部":
      df_rtv_f = df_rtv_f[df_rtv_f["产品SKU"] == selected_rtv_sku]
      df_sales_f = df_sales_f[df_sales_f["产品SKU"] == selected_rtv_sku]

    total_rtv_qty = df_rtv_f["QTY"].sum()
    total_deduction = df_rtv_f["总扣款"].sum()
    total_sales_qty_all = df_sales_f["Quantity"].sum()
    total_sales_amt_all = df_sales_f["Total Cost"].sum()

    rtv_rate_qty = (
        total_rtv_qty / total_sales_qty_all * 100
        if total_sales_qty_all > 0
        else 0
    )
    rtv_total_cost = df_rtv_f["Total Cost"].sum()
    rtv_rate_amt = (
        rtv_total_cost / total_sales_amt_all * 100
        if total_sales_amt_all > 0
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总退货件数", f"{total_rtv_qty:,}")
    c2.metric("总扣款金额 ($)", f"{total_deduction:,.2f}")
    c3.metric("整体数量退货率 (%)", f"{rtv_rate_qty:.2f}%")
    c4.metric("整体金额退货率 (%)", f"{rtv_rate_amt:.2f}%")

    st.markdown("---")

    # 1. SKU退货率排行榜
    st.subheader("1. 🏆 SKU 退货率排行榜")
    rtv_sku_grp = (
        df_rtv.groupby("产品SKU")
        .agg(退货件数=("QTY", "sum"), 退货成本=("Total Cost", "sum"))
        .reset_index()
    )
    sales_sku_grp = (
        df_sales.groupby("产品SKU")
        .agg(销售件数=("Quantity", "sum"), 销售金额=("Total Cost", "sum"))
        .reset_index()
    )
    sku_rank_df = pd.merge(sales_sku_grp, rtv_sku_grp, on="产品SKU", how="left").fillna(
        {"退货件数": 0, "退货成本": 0}
    )
    sku_rank_df["数量退货率(%)"] = (
        sku_rank_df["退货件数"] / sku_rank_df["销售件数"] * 100
    ).fillna(0)
    sku_rank_df["金额退货率(%)"] = (
        sku_rank_df["退货成本"] / sku_rank_df["销售金额"] * 100
    ).fillna(0)
    sku_rank_df = sku_rank_df.sort_values(
        by="数量退货率(%)", ascending=False
    ).reset_index(drop=True)

    if selected_rtv_sku != "全部":
      st.dataframe(
          sku_rank_df[sku_rank_df["产品SKU"] == selected_rtv_sku],
          use_container_width=True,
      )
    else:
      st.dataframe(sku_rank_df.head(15), use_container_width=True)

    st.markdown("---")

    # 2. 退货原因/理由占比分析
    st.subheader("2. 📊 退货原因 / 理由占比分析 (Reason)")
    reason_grp = (
        df_rtv_f.groupby("Reason")
        .agg(退货频次=("RTV Number", "count"), 退货件数=("QTY", "sum"))
        .reset_index()
    )
    col_r1, col_r2 = st.columns(2)
    with col_r1:
      st.dataframe(reason_grp, use_container_width=True)
    with col_r2:
      fig_reason = px.pie(
          reason_grp,
          names="Reason",
          values="退货件数",
          title="退货原因件数占比饼图",
          hole=0.4,
      )
      st.plotly_chart(fig_reason, use_container_width=True)

    st.markdown("---")

    # 3 & 4. 按订单日期与退货日期明细（双算法退货率）
    col_date1, col_date2 = st.columns(2)

    with col_date1:
      st.subheader("3. 📅 按订单日期明细 (Order Date 视角)")
      rtv_o_m = (
          df_rtv_f.groupby("Order_Month")
          .agg(退货件数=("QTY", "sum"), 退货成本=("Total Cost", "sum"))
          .reset_index()
      )
      sales_o_m = (
          df_sales_f.groupby("Month")
          .agg(销售件数=("Quantity", "sum"), 销售金额=("Total Cost", "sum"))
          .reset_index()
      )
      order_merged = pd.merge(
          sales_o_m,
          rtv_o_m,
          left_on="Month",
          right_on="Order_Month",
          how="left",
      ).fillna({"退货件数": 0, "退货成本": 0})
      order_merged["数量退货率(%)"] = (
          order_merged["退货件数"] / order_merged["销售件数"] * 100
      ).fillna(0)
      order_merged["金额退货率(%)"] = (
          order_merged["退货成本"] / order_merged["销售金额"] * 100
      ).fillna(0)

      st.dataframe(
          order_merged[
              [
                  "Month",
                  "销售件数",
                  "退货件数",
                  "数量退货率(%)",
                  "销售金额",
                  "退货成本",
                  "金额退货率(%)",
              ]
          ].rename(columns={"Month": "订单月份"}),
          use_container_width=True,
      )

    with col_date2:
      st.subheader("4. 📦 按退货日期明细 (RTV Date 视角)")
      rtv_r_m = (
          df_rtv_f.groupby("RTV_Month")
          .agg(退货件数=("QTY", "sum"), 退货成本=("Total Cost", "sum"))
          .reset_index()
      )
      rtv_r_m["数量退货率(%)"] = (
          rtv_r_m["退货件数"] / total_sales_qty_all * 100
          if total_sales_qty_all > 0
          else 0
      )
      rtv_r_m["金额退货率(%)"] = (
          rtv_r_m["退货成本"] / total_sales_amt_all * 100
          if total_sales_amt_all > 0
          else 0
      )

      st.dataframe(
          rtv_r_m.rename(
              columns={"RTV_Month": "退货月份", "Total Cost": "退货成本"}
          ),
          use_container_width=True,
      )

  # ==================== 看板五：广告数据分析 ====================
  with tabs[4]:
    st.header("🎯 广告数据分析看板")

    total_spend = df_ad["Spend"].sum()
    total_spa_rev = df_ad["SPA Revenue"].sum()
    total_clicks = df_ad["Clicks"].sum()
    total_impressions = df_ad["Impressions"].sum()
    avg_roas = (
        total_spa_rev / total_spend
        if total_spend > 0
        else df_ad["Return on Ad Spend (ROAS) SPA"].mean()
    )

    ac1, ac2, ac3, ac4 = st.columns(4)
    ac1.metric("总广告花费 (Spend)", f"${total_spend:,.2f}")
    ac2.metric("广告销售额 (SPA Revenue)", f"${total_spa_rev:,.2f}")
    ac3.metric("平均 ROAS", f"{avg_roas:.2f}")
    ac4.metric("总点击量 (Clicks)", f"{total_clicks:,}")

    st.markdown("---")
    st.subheader("按活动名称 (Campaign Name) 的广告表现")
    camp_summary = (
        df_ad.groupby("Campaign Name")
        .agg(
            总花费=("Spend", "sum"),
            广告销售额=("SPA Revenue", "sum"),
            总点击量=("Clicks", "sum"),
            总曝光量=("Impressions", "sum"),
        )
        .reset_index()
    )
    camp_summary["综合ROAS"] = (
        camp_summary["广告销售额"] / camp_summary["总花费"]
    ).fillna(0)
    st.dataframe(camp_summary, use_container_width=True)

    fig_ad = px.bar(
        camp_summary.sort_values(by="总花费", ascending=False).head(10),
        x="Campaign Name",
        y=["总花费", "广告销售额"],
        barmode="group",
        title="Top 10 广告活动花费与产出对比",
    )
    st.plotly_chart(fig_ad, use_container_width=True)

  # ==================== 看板六：利润率和成本率分析 ====================
  with tabs[5]:
    st.header("💰 利润率与成本率深度分析看板 (目标线: >=13%)")
    st.markdown(
        """
        **公式说明：**
        * 利润率 = $\\text{Cost(销售额)} - \\text{采购} - \\text{头程} - (\\text{cost} \\times \\text{退货率} + \\text{cost} \\times \\text{广告花费率} + \\text{cost} \\times 3.25\\% + \\text{cost} \\times 2\\%)$
        * 💡 **目标控制线**：综合利润率不得低于 **13%**，低于目标将触发红色预警提示。
        """
    )

    all_profit_skus = sorted(df_sales["产品SKU"].dropna().unique().tolist())
    selected_profit_sku = st.selectbox(
        "🔍 【利润看板筛选】选择单个产品SKU（选“全部”查看整体与各月度明细）",
        options=["全部"] + all_profit_skus,
        key="profit_sku_filter",
    )

    merged_sales_cost = pd.merge(
        df_sales,
        df_cost,
        left_on="产品SKU",
        right_on="SKU",
        how="left",
    ).fillna({"产品成本价": 0, "头程运费": 0})

    if selected_profit_sku != "全部":
      merged_sales_cost = merged_sales_cost[
          merged_sales_cost["产品SKU"] == selected_profit_sku
      ]

    overall_revenue = merged_sales_cost["Total Cost"].sum()
    overall_ad_spend = df_ad["Spend"].sum()
    global_ad_rate = (
        overall_ad_spend / overall_revenue if overall_revenue > 0 else 0
    )
    global_rtv_rate = rtv_rate_amt / 100
    platform_fee_rate = 0.0325
    other_fee_rate = 0.02

    # 1. 按月份拆解利润率与成本率
    st.subheader("📅 按月份的利润率与成本率趋势")
    monthly_profit_df = (
        merged_sales_cost.groupby("Month")
        .agg(
            月销售额=("Total Cost", "sum"),
            月采购成本=(
                "产品成本价",
                lambda x: (x * merged_sales_cost.loc[x.index, "Quantity"]).sum(),
            ),
            月头程运费=(
                "头程运费",
                lambda x: (x * merged_sales_cost.loc[x.index, "Quantity"]).sum(),
            ),
        )
        .reset_index()
    )

    monthly_profit_df["退货成本"] = (
        monthly_profit_df["月销售额"] * global_rtv_rate
    )
    monthly_profit_df["广告成本"] = (
        monthly_profit_df["月销售额"] * global_ad_rate
    )
    monthly_profit_df["平台扣点"] = (
        monthly_profit_df["月销售额"] * platform_fee_rate
    )
    monthly_profit_df["其他费用"] = (
        monthly_profit_df["月销售额"] * other_fee_rate
    )

    monthly_profit_df["月毛利额"] = (
        monthly_profit_df["月销售额"]
        - monthly_profit_df["月采购成本"]
        - monthly_profit_df["月头程运费"]
        - (
            monthly_profit_df["退货成本"]
            + monthly_profit_df["广告成本"]
            + monthly_profit_df["平台扣点"]
            + monthly_profit_df["其他费用"]
        )
    )

    monthly_profit_df["利润率(%)"] = (
        monthly_profit_df["月毛利额"] / monthly_profit_df["月销售额"] * 100
    ).fillna(0)
    monthly_profit_df["成本率(%)"] = (
        100 - monthly_profit_df["利润率(%)"]
    )
    monthly_profit_df["状态评估"] = monthly_profit_df["利润率(%)"].apply(
        lambda x: "🟢 达标 (>=13%)" if x >= 13.0 else "🚨 预警 (<13%)"
    )

    st.dataframe(monthly_profit_df, use_container_width=True)

    fig_profit_m = px.bar(
        monthly_profit_df,
        x="Month",
        y="利润率(%)",
        color="利润率(%)",
        color_continuous_scale="RdYlGn",
        text="利润率(%)",
        title="各月份利润率趋势柱状图（参考线: 13%）",
    )
    fig_profit_m.add_hline(
        y=13, line_dash="dash", line_color="red", annotation_text="目标线 13%"
    )
    fig_profit_m.update_traces(
        texttemplate="%{text:.1f}%", textposition="outside"
    )
    st.plotly_chart(fig_profit_m, use_container_width=True)

    st.markdown("---")

    # 2. 单个产品SKU利润率明细
    st.subheader("📦 单个产品 SKU 利润率明细与预警")
    sku_profit = (
        merged_sales_cost.groupby(["产品SKU", "产品名称", "品牌"])
        .agg(
            销售额=("Total Cost", "sum"),
            总销量=("Quantity", "sum"),
            采购成本=(
                "产品成本价",
                lambda x: (x * merged_sales_cost.loc[x.index, "Quantity"]).sum(),
            ),
            头程运费=(
                "头程运费",
                lambda x: (x * merged_sales_cost.loc[x.index, "Quantity"]).sum(),
            ),
        )
        .reset_index()
    )

    sku_profit["退货成本项"] = sku_profit["销售额"] * global_rtv_rate
    sku_profit["广告成本项"] = sku_profit["销售额"] * global_ad_rate
    sku_profit["平台扣点项"] = sku_profit["销售额"] * platform_fee_rate
    sku_profit["其他费用项"] = sku_profit["销售额"] * other_fee_rate

    sku_profit["毛利额"] = (
        sku_profit["销售额"]
        - sku_profit["采购成本"]
        - sku_profit["头程运费"]
        - (
            sku_profit["退货成本项"]
            + sku_profit["广告成本项"]
            + sku_profit["平台扣点项"]
            + sku_profit["其他费用项"]
        )
    )

    sku_profit["利润率(%)"] = (
        sku_profit["毛利额"] / sku_profit["销售额"] * 100
    ).fillna(0)
    sku_profit["预警状态"] = sku_profit["利润率(%)"].apply(
        lambda x: "🟢 正常" if x >= 13.0 else "⚠️ 低于13%预警"
    )

    st.dataframe(
        sku_profit[
            [
                "产品SKU",
                "产品名称",
                "品牌",
                "销售额",
                "采购成本",
                "头程运费",
                "毛利额",
                "利润率(%)",
                "预警状态",
            ]
        ],
        use_container_width=True,
    )

    total_gross_profit = sku_profit["毛利额"].sum()
    overall_margin = (
        total_gross_profit / overall_revenue * 100 if overall_revenue > 0 else 0
    )

    st.markdown("---")
    p1, p2, p3 = st.columns(3)
    p1.metric("整体总销售额 ($)", f"{overall_revenue:,.2f}")
    p2.metric("整体总毛利额 ($)", f"{total_gross_profit:,.2f}")
    p3.metric(
        "整体综合利润率 (%)",
        f"{overall_margin:.2f}%",
        delta=f"{overall_margin - 13:.2f}% vs 目标13%",
        delta_color="normal" if overall_margin >= 13 else "inverse",
    )

    if overall_margin < 13.0:
      st.error(
          "🚨 **【利润预警】** 当前整体综合利润率低于 13% 的目标线，请重点审查广告花费率、退货率或产品头程成本！"
      )
    else:
      st.success(
          "🟢 **【状态健康】** 当前整体综合利润率已达到或超过 13% 的目标线。"
      )
