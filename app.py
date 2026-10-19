import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='多维电商业务智能分析看板', page_icon='📊', layout='wide')
st.title('📊 多维电商业务智能分析看板')

@st.cache_data
def read_excel(file):
    df = pd.read_excel(file)
    df.columns = df.columns.astype(str).str.strip()
    return df

def number(series):
    return pd.to_numeric(series.astype(str).str.replace(',', '', regex=False).str.replace('$', '', regex=False).str.strip(), errors='coerce')

def percent(a, b):
    return np.where(np.asarray(b, dtype=float) != 0, np.asarray(a, dtype=float) / np.asarray(b, dtype=float) * 100, np.nan)

def table(df):
    config = {c: st.column_config.NumberColumn(c, format='%.2f%%') for c in df.columns if '(%)' in c}
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=config)

def chart(df, x, y, title, color=None):
    if df.empty:
        st.info('当前筛选条件下暂无数据。')
    else:
        fig = px.bar(df, x=x, y=y, color=color, title=title, barmode='group')
        fig.update_layout(xaxis_type='category', xaxis_title='')
        st.plotly_chart(fig, use_container_width=True)

def month(date):
    return pd.to_datetime(date, errors='coerce').dt.strftime('%Y-%m')

st.sidebar.header('📁 数据源上传')
sf = st.sidebar.file_uploader('1. 销售数据表', type=['xlsx', 'xls'])
rf = st.sidebar.file_uploader('2. RTV退货数据表', type=['xlsx', 'xls'])
cf = st.sidebar.file_uploader('3. 产品成本表', type=['xlsx', 'xls'])
af = st.sidebar.file_uploader('4. 广告数据表', type=['xlsx', 'xls'])
remittance_file = st.sidebar.file_uploader('5. Remittance结算表（第七看板）', type=['xlsx', 'xls'])
if not all([sf, rf, cf, af]):
    st.info('请在左侧上传销售、RTV、成本和广告四份Excel文件。')
    st.stop()

sales, rtv, costs, ads = [read_excel(f) for f in (sf, rf, cf, af)]
required = {
    '销售表': (sales, ['产品SKU', 'Order Date', 'Quantity', 'Total Cost']),
    'RTV表': (rtv, ['产品SKU', 'Order Date', 'RTV Date', 'QTY', 'Total Cost', '总扣款']),
    '成本表': (costs, ['SKU', '产品成本价', '头程运费']),
    '广告表': (ads, ['Spend', 'SPA Revenue'])
}
for name, (frame, fields) in required.items():
    missing = [f for f in fields if f not in frame.columns]
    if missing:
        st.error(f'{name}缺少字段：{missing}。当前表头：{list(frame.columns)}')
        st.stop()
for frame, key in [(sales, '产品SKU'), (rtv, '产品SKU'), (costs, 'SKU')]:
    frame[key] = frame[key].astype('string').str.strip().str.upper()
for frame, fields in [(sales, ['Quantity', 'Total Cost']), (rtv, ['QTY', 'Total Cost', '总扣款']), (costs, ['产品成本价', '头程运费'])]:
    for field in fields:
        frame[field] = number(frame[field])
for field in ['Spend', 'SPA Revenue', 'Clicks', 'Impressions']:
    if field not in ads:
        ads[field] = 0
    ads[field] = number(ads[field]).fillna(0)
sales[['Quantity', 'Total Cost']] = sales[['Quantity', 'Total Cost']].fillna(0)
rtv[['QTY', 'Total Cost', '总扣款']] = rtv[['QTY', 'Total Cost', '总扣款']].fillna(0)
sales['Order Date'] = pd.to_datetime(sales['Order Date'], errors='coerce')
rtv['Order Date'] = pd.to_datetime(rtv['Order Date'], errors='coerce')
rtv['RTV Date'] = pd.to_datetime(rtv['RTV Date'], errors='coerce')
sales['Month'] = month(sales['Order Date'])
rtv['Order_Month'] = month(rtv['Order Date'])
rtv['RTV_Month'] = month(rtv['RTV Date'])
for field in ['产品名称', '品牌', '运营']:
    if field not in sales:
        sales[field] = '未填写'
    sales[field] = sales[field].fillna('未填写').astype(str)
if 'Customer Order Number' not in sales:
    sales['Customer Order Number'] = sales.index.astype(str)
all_skus = sorted(set(sales['产品SKU'].dropna()) | set(rtv['产品SKU'].dropna()))

tabs = st.tabs(['1. 销售总看板', '2. 产品SKU看板', '3. 运营维度看板', '4. 退货与扣款看板', '5. 广告数据分析看板', '6. 利润率与成本率看板', '7. Remittance毛利率核算'])

with tabs[0]:
    st.header('📈 整体销售数据分析')
    revenue, qty = sales['Total Cost'].sum(), sales['Quantity'].sum()
    orders = sales['Customer Order Number'].nunique()
    valid_dates = sales['Order Date'].dropna()
    days = (valid_dates.max() - valid_dates.min()).days + 1 if not valid_dates.empty else 0
    labels = ['总销售额', '总销量', '总订单数', '平均客单价', '日均销量']
    values = [f'${revenue:,.2f}', f'{qty:,.0f}', f'{orders:,}', f'${revenue/orders:,.2f}' if orders else '—', f'{qty/days:,.2f}' if days else '—']
    for c, label, value in zip(st.columns(5), labels, values):
        c.metric(label, value)
    monthly_sales = sales.groupby('Month').agg(总销售额=('Total Cost', 'sum'), 总销量=('Quantity', 'sum'), 总单量=('Customer Order Number', 'nunique'), 有销售天数=('Order Date', 'nunique')).reset_index()
    monthly_sales['平均客单价'] = percent(monthly_sales['总销售额'], monthly_sales['总单量']) / 100
    monthly_sales['日均销量'] = percent(monthly_sales['总销量'], monthly_sales['有销售天数']) / 100
    metric = st.selectbox('月度趋势指标', ['总销售额', '总销量', '总单量', '平均客单价', '日均销量'])
    chart(monthly_sales, 'Month', metric, f'月度{metric}')
    table(monthly_sales)

with tabs[1]:
    st.header('📦 产品SKU销售分析')
    sku_month = sales.groupby(['Month', '产品SKU'], dropna=False).agg(总销售额=('Total Cost', 'sum'), 总销量=('Quantity', 'sum'), 总订单数=('Customer Order Number', 'nunique'), 有销售天数=('Order Date', 'nunique')).reset_index()
    sku_month['日均销量'] = percent(sku_month['总销量'], sku_month['有销售天数']) / 100
    sku_month['销售额占比(%)'] = percent(sku_month['总销售额'], sku_month.groupby('Month')['总销售额'].transform('sum'))
    sku_month['月度排名'] = sku_month.groupby('Month')['总销售额'].rank(method='min', ascending=False)
    sku_month['SKU等级'] = pd.cut(sku_month.groupby('Month')['总销售额'].rank(pct=True, ascending=False), [0, .2, .5, .8, 1], labels=['A', 'B', 'C', 'D'], include_lowest=True)
    product_meta = sales.drop_duplicates('产品SKU')[['产品SKU', '产品名称', '品牌', '运营']]
    sku_month = sku_month.merge(product_meta, on='产品SKU', how='left')
    table(sku_month.sort_values(['Month', '月度排名']))
    chosen = st.selectbox('搜索单个SKU', sorted(sales['产品SKU'].dropna().unique()), key='sales_sku')
    single = sku_month[sku_month['产品SKU'] == chosen]
    a, b = st.columns(2)
    with a:
        chart(single, 'Month', '总销量', f'{chosen}月度销量')
    with b:
        chart(single, 'Month', '总销售额', f'{chosen}月度销售额')

with tabs[2]:
    st.header('👥 运营人员月度销售分析')
    op = sales.groupby(['Month', '运营']).agg(销售额=('Total Cost', 'sum'), 销量=('Quantity', 'sum'), 订单数=('Customer Order Number', 'nunique')).reset_index()
    table(op)
    chart(op, 'Month', '销售额', '各运营月度销售额', '运营')

with tabs[3]:
    st.header('🔄 退货与扣款深度分析')
    chosen = st.multiselect('筛选产品SKU（不选择代表全部）', all_skus, key='rtv_skus')
    ss = sales[sales['产品SKU'].isin(chosen)] if chosen else sales
    rr = rtv[rtv['产品SKU'].isin(chosen)] if chosen else rtv
    sq, sa = ss['Quantity'].sum(), ss['Total Cost'].sum()
    rq, ra, ded = rr['QTY'].sum(), rr['Total Cost'].sum(), rr['总扣款'].sum()
    metrics = [('退货件数', f'{rq:,.0f}'), ('退货金额', f'${ra:,.2f}'), ('总扣款', f'${ded:,.2f}'), ('数量退货率', f'{rq/sq*100:.2f}%' if sq else '—'), ('金额退货率', f'{ra/sa*100:.2f}%' if sa else '—')]
    for c, (label, value) in zip(st.columns(5), metrics):
        c.metric(label, value)
    sub = st.tabs(['1. SKU退货率排行榜', '2. 退货原因占比', '3. Order Date视角', '4. RTV Date视角'])
    with sub[0]:
        sg = ss.groupby('产品SKU').agg(销售件数=('Quantity', 'sum'), 销售金额=('Total Cost', 'sum')).reset_index()
        rg = rr.groupby('产品SKU').agg(退货件数=('QTY', 'sum'), 退货金额=('Total Cost', 'sum'), 扣款金额=('总扣款', 'sum')).reset_index()
        rank = sg.merge(rg, on='产品SKU', how='outer').fillna(0)
        rank['数量退货率(%)'] = percent(rank['退货件数'], rank['销售件数'])
        rank['金额退货率(%)'] = percent(rank['退货金额'], rank['销售金额'])
        rank_by = st.selectbox('排名依据', ['数量退货率(%)', '金额退货率(%)', '退货件数', '扣款金额'])
        minimum = st.number_input('最低销售件数', min_value=0, value=10)
        rank = rank[rank['销售件数'] >= minimum].sort_values(rank_by, ascending=False)
        table(rank)
        chart(rank.head(15), '产品SKU', rank_by, 'SKU退货Top15')
    with sub[1]:
        reason_col = next((c for c in ['Reason', 'Return Reason', 'RTV Reason', '退货原因', '退货理由'] if c in rr.columns), None)
        if reason_col is None:
            st.warning(f'未找到退货原因字段。RTV表字段：{list(rr.columns)}')
        else:
            temp = rr.copy()
            temp[reason_col] = temp[reason_col].fillna('未填写')
            reason = temp.groupby(reason_col).agg(退货件数=('QTY', 'sum'), 退货金额=('Total Cost', 'sum'), 扣款金额=('总扣款', 'sum')).reset_index()
            basis = st.radio('占比依据', ['退货件数', '退货金额', '扣款金额'], horizontal=True)
            reason['占比(%)'] = percent(reason[basis], reason[basis].sum())
            table(reason.sort_values(basis, ascending=False))
            if reason[basis].sum() > 0:
                st.plotly_chart(px.pie(reason, names=reason_col, values=basis, hole=.4, title='退货原因占比'), use_container_width=True)
    for tab, r_month, title in [(sub[2], 'Order_Month', 'Order Date（订单日期）'), (sub[3], 'RTV_Month', 'RTV Date（退货日期）')]:
        with tab:
            st.subheader(title)
            s = ss.groupby(['Month', '产品SKU']).agg(销售件数=('Quantity', 'sum'), 销售金额=('Total Cost', 'sum')).reset_index().rename(columns={'Month': '月份'})
            r = rr.groupby([r_month, '产品SKU']).agg(退货件数=('QTY', 'sum'), 退货金额=('Total Cost', 'sum'), 扣款金额=('总扣款', 'sum')).reset_index().rename(columns={r_month: '月份'})
            detail = s.merge(r, on=['月份', '产品SKU'], how='outer')
            for field in ['销售件数', '销售金额', '退货件数', '退货金额', '扣款金额']:
                detail[field] = detail[field].fillna(0)
            detail['数量退货率(%)'] = percent(detail['退货件数'], detail['销售件数'])
            detail['金额退货率(%)'] = percent(detail['退货金额'], detail['销售金额'])
            monthly = detail.groupby('月份', dropna=False)[['销售件数', '销售金额', '退货件数', '退货金额', '扣款金额']].sum().reset_index()
            monthly['数量退货率(%)'] = percent(monthly['退货件数'], monthly['销售件数'])
            monthly['金额退货率(%)'] = percent(monthly['退货金额'], monthly['销售金额'])
            if r_month == 'RTV_Month':
                st.info('本视角以退货发生月份为分子、同月销售为分母，是当期退货销售比；可能包含历史订单退货。')
            else:
                st.info('本视角按原订单月份归属退货；近期月份可能因为退货尚未发生而偏低。')
            table(monthly)
            a, b = st.columns(2)
            with a:
                chart(monthly, '月份', '数量退货率(%)', '月度数量退货率')
            with b:
                chart(monthly, '月份', '金额退货率(%)', '月度金额退货率')
            st.subheader('SKU × 月份明细')
            table(detail.sort_values(['月份', '产品SKU']))

with tabs[4]:
    st.header('🎯 广告数据分析')
    spend, rev = ads['Spend'].sum(), ads['SPA Revenue'].sum()
    a, b, c, d = st.columns(4)
    a.metric('广告花费', f'${spend:,.2f}')
    b.metric('广告销售额', f'${rev:,.2f}')
    c.metric('ROAS', f'{rev/spend:.2f}' if spend else '—')
    d.metric('总点击量', f'{ads["Clicks"].sum():,.0f}')
    if 'Campaign Name' in ads.columns:
        camp = ads.groupby('Campaign Name').agg(广告花费=('Spend', 'sum'), 广告销售额=('SPA Revenue', 'sum'), 点击量=('Clicks', 'sum'), 曝光量=('Impressions', 'sum')).reset_index()
        camp['ROAS'] = np.where(camp['广告花费'] != 0, camp['广告销售额'] / camp['广告花费'], np.nan)
        table(camp)
        chart(camp.nlargest(10, '广告花费'), 'Campaign Name', '广告花费', '广告活动花费Top10')

with tabs[5]:
    st.header('💰 利润率与成本率深度分析（目标 ≥13%）')
    st.caption('先计算全量SKU×月份利润底表，再筛选SKU。退货采用RTV Date视角的金额退货率；成本表字段：SKU、产品成本价、头程运费。')
    clean_cost = costs[['SKU', '产品成本价', '头程运费']].copy()
    clean_cost = clean_cost.dropna(subset=['SKU'])
    clean_cost = clean_cost[clean_cost['SKU'] != '']
    duplicates = clean_cost[clean_cost.duplicated('SKU', keep=False)]
    if not duplicates.empty:
        conflicts = duplicates.groupby('SKU')[['产品成本价', '头程运费']].nunique(dropna=False)
        conflicting = conflicts[(conflicts > 1).any(axis=1)].index.tolist()
        if conflicting:
            st.error(f'成本表存在同SKU不同成本，无法安全计算：{conflicting[:20]}。请先统一成本表。')
            st.stop()
        clean_cost = clean_cost.drop_duplicates('SKU')
        st.info('成本表存在完全一致的重复SKU记录，已自动去重。')
    full = sales.merge(clean_cost, left_on='产品SKU', right_on='SKU', how='left', validate='many_to_one')
    full['成本完整'] = full['产品成本价'].notna() & full['头程运费'].notna()
    full['零成本待核实'] = full['成本完整'] & (full['产品成本价'] == 0)
    full['采购成本'] = full['Quantity'] * full['产品成本价']
    full['头程成本'] = full['Quantity'] * full['头程运费']
    total_sales_revenue = sales['Total Cost'].sum()
    fixed_ad_rate = ads['Spend'].sum() / total_sales_revenue if total_sales_revenue else 0
    st.sidebar.subheader('利润模型参数')
    platform_rate = st.sidebar.number_input('平台费率(%)', min_value=0.0, value=3.25, step=0.25) / 100
    other_rate = st.sidebar.number_input('其他费用率(%)', min_value=0.0, value=2.0, step=0.25) / 100
    base = full.groupby(['Month', '产品SKU'], dropna=False).agg(销售额=('Total Cost', 'sum'), 销量=('Quantity', 'sum'), 采购成本=('采购成本', 'sum'), 头程成本=('头程成本', 'sum'), 成本完整=('成本完整', 'all'), 零成本待核实=('零成本待核实', 'any')).reset_index()
    # RTV视角：按实际退货日期所属月份与SKU归集，分母是该月同SKU销售额。
    ret = rtv.groupby(['RTV_Month', '产品SKU'], dropna=False).agg(退货金额=('Total Cost', 'sum'), 退货件数=('QTY', 'sum'), RTV扣款=('总扣款', 'sum')).reset_index().rename(columns={'RTV_Month': 'Month'})
    base = base.merge(ret, on=['Month', '产品SKU'], how='left', validate='one_to_one')
    for field in ['退货金额', '退货件数', 'RTV扣款']:
        base[field] = base[field].fillna(0)
    # RTV金额退货率(%) = 当月SKU退货金额 / 当月SKU销售额 × 100。
    # 利润退货成本 = 当月SKU销售额 × RTV金额退货率；在分母有效时等于当月退货金额。
    base['RTV金额退货率(%)'] = percent(base['退货金额'], base['销售额'])
    base['退货成本'] = base['销售额'] * base['RTV金额退货率(%)'].fillna(0) / 100
    # 销售额为零但发生RTV的月份不可计算费率，不能将该笔退货损失静默忽略。
    base['RTV无销售额待核实'] = (base['销售额'] <= 0) & (base['退货金额'] != 0)
    base.loc[base['RTV无销售额待核实'], '退货成本'] = base.loc[base['RTV无销售额待核实'], '退货金额']
    base['广告成本'] = base['销售额'] * fixed_ad_rate
    base['平台扣点'] = base['销售额'] * platform_rate
    base['其他费用'] = base['销售额'] * other_rate
    cost_fields = ['采购成本', '头程成本', '退货成本', '广告成本', '平台扣点', '其他费用']
    base['总成本'] = base[cost_fields].sum(axis=1)
    base['利润额'] = base['销售额'] - base['总成本']
    base.loc[~base['成本完整'], ['总成本', '利润额']] = np.nan
    base['利润率(%)'] = percent(base['利润额'], base['销售额'])
    base['成本率(%)'] = percent(base['总成本'], base['销售额'])
    base['采购成本率(%)'] = percent(base['采购成本'], base['销售额'])
    base['预警状态'] = np.select([~base['成本完整'], base['零成本待核实'], base['销售额'] <= 0, base['利润率(%)'] < 10, base['利润率(%)'] < 13], ['成本缺失', '零成本待核实', '无有效销售额', '严重预警', '低于13%'], default='达标')
    meta = sales.drop_duplicates('产品SKU')[['产品SKU', '产品名称', '品牌']]
    base = base.merge(meta, on='产品SKU', how='left', validate='many_to_one')
    chosen = st.multiselect('筛选产品SKU（留空代表全部）', sorted(base['产品SKU'].dropna().unique()), key='profit_skus')
    filtered = base[base['产品SKU'].isin(chosen)].copy() if chosen else base.copy()
    missing = filtered.loc[~filtered['成本完整'], '产品SKU'].dropna().unique().tolist()
    zeros = filtered.loc[filtered['零成本待核实'], '产品SKU'].dropna().unique().tolist()
    if missing:
        st.error(f'有{len(missing)}个SKU缺少采购成本或头程字段，已排除其利润计算：{missing[:25]}')
    if filtered['RTV无销售额待核实'].any():
        st.warning('部分SKU月份有RTV退货金额但没有正向销售额；该月份无法计算RTV金额退货率，退货金额已单列，不能用零退货率代替。')
    if zeros:
        st.warning(f'有{len(zeros)}个SKU的产品成本价为0，利润可能偏高，请核实：{zeros[:25]}')
    valid = filtered[filtered['成本完整'] & (filtered['销售额'] > 0)].copy()
    revenue = valid['销售额'].sum()
    profit = valid['利润额'].sum()
    expense = valid['总成本'].sum()
    margin = profit / revenue * 100 if revenue else np.nan
    cost_rate = expense / revenue * 100 if revenue else np.nan
    for col, label, value in zip(st.columns(4), ['有效销售额', '估算利润额', '综合利润率', '综合成本率'], [f'${revenue:,.2f}', f'${profit:,.2f}', f'{margin:.2f}%' if revenue else '—', f'{cost_rate:.2f}%' if revenue else '—']):
        col.metric(label, value)
    if revenue:
        if margin < 13:
            st.error(f'利润率{margin:.2f}%，低于13%目标。')
        else:
            st.success(f'利润率{margin:.2f}%，达到13%目标。')
    st.caption(f'广告费率固定为全量广告花费/全量销售额 = {fixed_ad_rate*100:.2f}%；筛选SKU不会改变该费率。')
    monthly = valid.groupby('Month').agg(月销售额=('销售额', 'sum'), 月销量=('销量', 'sum'), 月采购成本=('采购成本', 'sum'), 月头程运费=('头程成本', 'sum'), 退货成本=('退货成本', 'sum'), 广告成本=('广告成本', 'sum'), 平台扣点=('平台扣点', 'sum'), 其他费用=('其他费用', 'sum'), 月总成本=('总成本', 'sum'), 月利润额=('利润额', 'sum')).reset_index().sort_values('Month')
    monthly['利润率(%)'] = percent(monthly['月利润额'], monthly['月销售额'])
    monthly['成本率(%)'] = percent(monthly['月总成本'], monthly['月销售额'])
    monthly['采购成本率(%)'] = percent(monthly['月采购成本'], monthly['月销售额'])
    monthly['距离目标(百分点)'] = monthly['利润率(%)'] - 13
    monthly['状态评估'] = np.where(monthly['利润率(%)'] >= 13, '达标', '低于13%')
    st.subheader('📅 月度利润率与成本率')
    table(monthly)
    fig = go.Figure(go.Bar(x=monthly['Month'], y=monthly['利润率(%)'], marker_color=['#198754' if x >= 13 else '#dc3545' for x in monthly['利润率(%)']], text=[f'{x:.2f}%' for x in monthly['利润率(%)']], textposition='outside'))
    fig.add_hline(y=13, line_dash='dash', line_color='red', annotation_text='目标13%')
    fig.update_layout(title='月度利润率趋势', xaxis_type='category', yaxis_title='利润率(%)')
    st.plotly_chart(fig, use_container_width=True)
    a, b = st.columns(2)
    with a:
        chart(monthly, 'Month', '成本率(%)', '月度总成本率')
    with b:
        chart(monthly, 'Month', '采购成本率(%)', '月度采购成本率')
    chart(monthly, 'Month', '月利润额', '月度利润额')
    if not monthly.empty:
        melted = monthly.melt(id_vars='Month', value_vars=['月采购成本', '月头程运费', '退货成本', '广告成本', '平台扣点', '其他费用'], var_name='成本类别', value_name='金额')
        st.plotly_chart(px.bar(melted, x='Month', y='金额', color='成本类别', barmode='stack', title='月度成本结构'), use_container_width=True)
    st.subheader('📦 SKU利润率排行榜')
    sku_profit = valid.groupby(['产品SKU', '产品名称', '品牌'], dropna=False).agg(销售额=('销售额', 'sum'), 总销量=('销量', 'sum'), 采购成本=('采购成本', 'sum'), 头程运费=('头程成本', 'sum'), 退货成本=('退货成本', 'sum'), 广告成本=('广告成本', 'sum'), 平台扣点=('平台扣点', 'sum'), 其他费用=('其他费用', 'sum'), 总成本=('总成本', 'sum'), 利润额=('利润额', 'sum'), 零成本待核实=('零成本待核实', 'any')).reset_index()
    sku_profit['利润率(%)'] = percent(sku_profit['利润额'], sku_profit['销售额'])
    sku_profit['成本率(%)'] = percent(sku_profit['总成本'], sku_profit['销售额'])
    sku_profit['预警状态'] = np.select([sku_profit['零成本待核实'], sku_profit['利润率(%)'] < 10, sku_profit['利润率(%)'] < 13], ['零成本待核实', '严重预警', '低于13%'], default='达标')
    table(sku_profit.sort_values('利润率(%)'))
    st.subheader('SKU × 月份利润明细')
    table(filtered[['Month', '产品SKU', '产品名称', '品牌', '销售额', '销量', '采购成本', '头程成本', 'RTV金额退货率(%)', '退货成本', '广告成本', '平台扣点', '其他费用', '总成本', '利润额', '利润率(%)', '成本率(%)', '预警状态']].sort_values(['Month', '产品SKU']))
    alerts = valid[valid['利润率(%)'] < 13].sort_values(['Month', '利润率(%)'])
    st.subheader(f'低于13%的SKU月度预警：{len(alerts)}条')
    table(alerts[['Month', '产品SKU', '销售额', '利润额', '利润率(%)', '成本率(%)', '预警状态']])
    st.subheader('数据一致性检查')
    checks = pd.DataFrame({'检查项目': ['SKU汇总销售额', 'SKU汇总利润额', '月度汇总销售额', '月度汇总利润额'], '差异金额': [revenue - sku_profit['销售额'].sum(), profit - sku_profit['利润额'].sum(), revenue - monthly['月销售额'].sum(), profit - monthly['月利润额'].sum()]})
    checks['检查结果'] = np.where(checks['差异金额'].abs() < .01, '通过', '异常')
    table(checks)
    st.caption('估算口径：采购及头程按单位成本×销量；广告按全量比例分摊；退货使用RTV Date实际退货月份，RTV金额退货率=当月SKU退货金额÷当月SKU销售额，退货成本=当月SKU销售额×RTV金额退货率。RTV总扣款不重复扣除。无销售额的RTV月份须单独核对。')


# ================================================================
# 看板七：Remittance 月度毛利率核算（独立于看板六）
# ================================================================
with tabs[6]:
    st.header('💵 Remittance 月度毛利率与成本预算管理')
    st.caption('销售额按销售表 Order Date 月份；结算费用按 Remittance Payment/Chargeback Date 月份。看板六保持原有 RTV 估算口径不变。')
    if remittance_file is None:
        st.info('请在侧边栏上传第5份 Remittance Excel 文件，启用此看板。')
    else:
        rem = read_excel(remittance_file)
        required_rem = ['Doc Type', 'Transaction Value', 'Cash Discount Amount', 'Payment/Chargeback Date', 'Reason Code']
        missing_rem = [c for c in required_rem if c not in rem.columns]
        if missing_rem:
            st.error(f'Remittance缺少字段：{missing_rem}。实际字段：{list(rem.columns)}')
        else:
            rem = rem.copy()
            rem['Doc Type'] = rem['Doc Type'].fillna('').astype(str).str.strip().str.upper()
            rem['Reason Code'] = rem['Reason Code'].fillna('').astype(str).str.strip().str.upper()
            rem['Transaction Value'] = number(rem['Transaction Value'])
            rem['Cash Discount Amount'] = number(rem['Cash Discount Amount'])
            rem['Payment/Chargeback Date'] = pd.to_datetime(rem['Payment/Chargeback Date'], errors='coerce')
            rem['Month'] = month(rem['Payment/Chargeback Date'])
            rem['费用分类'] = '其他/对账'
            # 优先识别 TRADE DISCOUNT：每一行仅归属一个成本类别
            trade_mask = rem['Reason Code'].eq('*TRADE DISCOUNT')
            rem.loc[trade_mask, '费用分类'] = '平台佣金'
            rem.loc[~trade_mask & rem['Doc Type'].isin(['Z1', 'KG']), '费用分类'] = '退款费用'
            rem.loc[~trade_mask & rem['Doc Type'].eq('SA'), '费用分类'] = '广告费用'
            rem.loc[~trade_mask & rem['Doc Type'].eq('Z0'), '费用分类'] = 'Z0应付发票'
            rem.loc[~trade_mask & rem['Doc Type'].eq('ZP'), '费用分类'] = 'ZP实际到账'
            rem_valid = rem.dropna(subset=['Month']).copy()
            invalid_dates = rem['Month'].isna().sum()
            invalid_amounts = rem['Transaction Value'].isna().sum()
            invalid_cash7 = rem['Cash Discount Amount'].isna().sum()
            if invalid_dates or invalid_amounts or invalid_cash7:
                st.warning(f'Remittance中有 {invalid_dates} 行日期无效、{invalid_amounts} 行金额无效；Cash Discount Amount无效 {invalid_cash7} 行（按0处理）；无效日期/交易金额可能无法计入。')

            st.markdown('**计算规则：** 月毛利润 = 销售额 − Z1/KG退款 − 平台佣金（TRADE DISCOUNT + Cash Discount）− SA广告费 − 采购成本 − 头程运费 − 售后费用。Z0与ZP只用于结算对账，不计入毛利润。')
            st.info('注意：销售与结算费用采用不同日期口径，因此这是月度经营管理毛利率，不是严格按订单逐笔匹配的会计毛利率。')

            # 原始销售额：销售表 Order Date
            sales_by_month = sales.groupby('Month', dropna=True).agg(
                销售额=('Total Cost', 'sum'), 销量=('Quantity', 'sum')
            ).reset_index()
            sales_by_month = sales_by_month[sales_by_month['Month'].notna()].copy()

            # SKU单位采购成本、头程：与第六看板相同的固定表头
            c7 = costs[['SKU', '产品成本价', '头程运费']].copy()
            dup = c7['SKU'].duplicated(keep=False) & c7['SKU'].notna()
            if dup.any():
                st.warning(f'成本表有 {c7.loc[dup, "SKU"].nunique()} 个重复SKU，第七看板使用第一条成本记录，请核实。')
            c7 = c7.drop_duplicates(subset=['SKU'], keep='first')
            sc7 = sales[['Month', '产品SKU', 'Quantity', 'Total Cost']].merge(
                c7, left_on='产品SKU', right_on='SKU', how='left', validate='many_to_one'
            )
            sc7['成本匹配完整'] = sc7['产品成本价'].notna() & sc7['头程运费'].notna()
            sc7['采购成本'] = sc7['Quantity'] * sc7['产品成本价']
            sc7['头程成本'] = sc7['Quantity'] * sc7['头程运费']
            missing_skus7 = sorted(sc7.loc[~sc7['成本匹配完整'], '产品SKU'].dropna().unique().tolist())
            if missing_skus7:
                st.error(f'成本表未完整匹配 {len(missing_skus7)} 个SKU。涉及月份的毛利率暂不计算，避免将缺失成本当成0。')
                with st.expander('查看成本缺失SKU'):
                    st.write(missing_skus7)
            cost_month7 = sc7.groupby('Month', dropna=True).agg(
                采购成本=('采购成本', lambda x: x.sum(min_count=1)),
                头程运费=('头程成本', lambda x: x.sum(min_count=1)),
                成本完整=('成本匹配完整', 'all')
            ).reset_index()

            # Remittance：按费用分类与实际扣款月份汇总，保留冲销的负数
            rem_month7 = rem_valid.pivot_table(
                index='Month', columns='费用分类', values='Transaction Value',
                aggfunc='sum', fill_value=0
            ).reset_index()
            for key in ['退款费用', '平台佣金', '广告费用', 'Z0应付发票', 'ZP实际到账', '其他/对账']:
                if key not in rem_month7.columns:
                    rem_month7[key] = 0.0

            # Cash Discount Amount为独立费用列，可能与任意Doc Type并存，必须额外求和。
            cash_month7 = (rem_valid.groupby('Month', dropna=True)['Cash Discount Amount']
                           .sum(min_count=1).fillna(0).mul(-1).rename('Cash Discount佣金').reset_index())

            # 合并月份：包含只有费用、没有销售的月份
            month_index7 = pd.DataFrame({'Month': sorted(
                set(sales_by_month['Month'].dropna()) |
                set(rem_month7['Month'].dropna())
            )})
            fin7 = month_index7.merge(sales_by_month, on='Month', how='left')
            fin7 = fin7.merge(cost_month7, on='Month', how='left')
            fin7 = fin7.merge(rem_month7, on='Month', how='left')
            fin7 = fin7.merge(cash_month7, on='Month', how='left')
            for col in ['销售额', '销量', '退款费用', '平台佣金', '广告费用', 'Z0应付发票', 'ZP实际到账', '其他/对账', 'Cash Discount佣金']:
                fin7[col] = fin7[col].fillna(0)
            fin7['成本完整'] = fin7['成本完整'].fillna(False)
            fin7['平台佣金'] = fin7['平台佣金'] + fin7['Cash Discount佣金']

            st.subheader('1. 售后预算及实际费用设置')
            aftersale_rate7 = st.number_input(
                '售后费用预算费率（%）', min_value=0.0, max_value=100.0,
                value=2.0, step=0.25, format='%.2f', key='rem_aftersale_rate'
            )
            st.caption('可按月份填写实际售后费用；未填写的月份按销售额 × 预算费率估算。')
            manual7 = pd.DataFrame({
                'Month': fin7['Month'],
                '实际售后费用': [np.nan] * len(fin7)
            })
            edited7 = st.data_editor(
                manual7, hide_index=True, use_container_width=True,
                disabled=['Month'], num_rows='fixed', key='rem_aftersale_editor',
                column_config={'Month': st.column_config.TextColumn('月份'),
                               '实际售后费用': st.column_config.NumberColumn('实际售后费用（留空按预算）', format='%.2f', min_value=0.0)}
            )
            fin7['售后预算费用'] = fin7['销售额'] * aftersale_rate7 / 100
            actual_after7 = pd.to_numeric(edited7['实际售后费用'], errors='coerce')
            fin7['售后费用'] = actual_after7.where(actual_after7.notna(), fin7['售后预算费用']).to_numpy()
            fin7['售后费用口径'] = np.where(actual_after7.notna().to_numpy(), '实际录入', '预算估算')

            # 严格区分：没有销售、成本缺失、费用已发生但未有销售
            expenses7 = ['退款费用', '平台佣金', '广告费用', '采购成本', '头程运费', '售后费用']
            fin7['总成本支出'] = fin7[expenses7].sum(axis=1, min_count=len(expenses7))
            fin7.loc[~fin7['成本完整'], '总成本支出'] = np.nan
            fin7['毛利润'] = fin7['销售额'] - fin7['总成本支出']
            fin7['毛利率(%)'] = percent(fin7['毛利润'], fin7['销售额'])
            fin7['总成本率(%)'] = percent(fin7['总成本支出'], fin7['销售额'])
            for col in expenses7:
                fin7[col + '率(%)'] = percent(fin7[col], fin7['销售额'])
            fin7['13%目标成本上限'] = fin7['销售额'] * 0.87
            fin7['成本预算余额'] = fin7['13%目标成本上限'] - fin7['总成本支出']
            fin7['状态'] = np.select(
                [~fin7['成本完整'], fin7['销售额'] <= 0, fin7['毛利率(%)'] < 13],
                ['成本缺失', '无销售额，待核查', '低于13%'], default='达标'
            )

            months7 = fin7['Month'].tolist()
            selected_months7 = st.multiselect('选择核算月份（留空显示全部）', months7, key='rem_month_filter')
            view7 = fin7[fin7['Month'].isin(selected_months7)] if selected_months7 else fin7
            valid7 = view7[view7['状态'].isin(['达标', '低于13%'])]
            rev7 = valid7['销售额'].sum()
            exp7 = valid7['总成本支出'].sum()
            gross7 = rev7 - exp7
            margin7 = gross7 / rev7 * 100 if rev7 > 0 else np.nan
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric('销售额', f'${rev7:,.2f}')
            k2.metric('总成本支出', f'${exp7:,.2f}')
            k3.metric('毛利润', f'${gross7:,.2f}')
            k4.metric('毛利率', f'{margin7:.2f}%' if pd.notna(margin7) else '—')
            k5.metric('成本预算余额', f'${valid7["成本预算余额"].sum():,.2f}')
            if pd.notna(margin7) and margin7 < 13:
                st.error(f'毛利率 {margin7:.2f}%，低于13%目标，请检查成本支出。')
            elif pd.notna(margin7):
                st.success(f'毛利率 {margin7:.2f}%，达到13%目标。')
            if len(valid7) < len(view7):
                st.warning('有月份因无销售额或采购/头程成本缺失未纳入汇总毛利率；请检查月度明细。')

            st.subheader('2. 月度毛利率与费用率明细')
            display7 = ['Month', '销售额', '销量', '退款费用', '退款费用率(%)',
                        '平台佣金', '平台佣金率(%)', '广告费用', '广告费用率(%)',
                        'Cash Discount佣金',
                        '采购成本', '采购成本率(%)', '头程运费', '头程运费率(%)',
                        '售后费用', '售后费用率(%)', '售后费用口径',
                        '总成本支出', '总成本率(%)', '毛利润', '毛利率(%)',
                        '13%目标成本上限', '成本预算余额', '状态']
            table(view7[display7].sort_values('Month'))
            st.subheader('3. 月度毛利率趋势（13%目标线）')
            plot7 = view7[view7['毛利率(%)'].notna()].sort_values('Month')
            if not plot7.empty:
                fig7 = go.Figure()
                fig7.add_trace(go.Bar(
                    x=plot7['Month'], y=plot7['毛利率(%)'],
                    marker_color=['#2a936b' if v >= 13 else '#d74c4c' for v in plot7['毛利率(%)']],
                    text=[f'{v:.2f}%' for v in plot7['毛利率(%)']], textposition='outside'
                ))
                fig7.add_hline(y=13, line_dash='dash', line_color='red', annotation_text='13%目标线')
                fig7.update_layout(xaxis_type='category', yaxis_title='毛利率 (%)')
                st.plotly_chart(fig7, use_container_width=True)
            else:
                st.info('当前月份无可计算的毛利率。')

            st.subheader('4. 月度成本结构与费用率')
            cost_stack7 = view7.melt(id_vars='Month', value_vars=expenses7,
                                     var_name='费用项目', value_name='费用金额')
            if not cost_stack7.empty:
                st.plotly_chart(px.bar(cost_stack7, x='Month', y='费用金额', color='费用项目',
                                       barmode='stack', title='月度成本金额构成'), use_container_width=True)
            rate_cols7 = [c + '率(%)' for c in expenses7]
            rates7 = view7.melt(id_vars='Month', value_vars=rate_cols7,
                                var_name='费用项目', value_name='费率(%)')
            if not rates7.empty:
                st.plotly_chart(px.line(rates7, x='Month', y='费率(%)', color='费用项目',
                                        markers=True, title='各项费用率月度变化'), use_container_width=True)

            st.subheader('5. Remittance 交易类型与回款对账')
            reconciliation7 = view7[['Month', 'Z0应付发票', 'ZP实际到账',
                                      '退款费用', '平台佣金', 'Cash Discount佣金', '广告费用', '其他/对账']].copy()
            table(reconciliation7)
            st.caption('Cash Discount佣金按 Cash Discount Amount 取反后汇总，并已包含在平台佣金中，不能再次作为独立成本扣除；Z0、ZP仅展示原始有符号 Transaction Value 的合计；Z0负数并不意味着负销售额。不同月份的付款与发票可能跨期，不建议直接用 Z0 − ZP 作为损失。')
            st.subheader('6. Remittance 费用分类明细')
            types7 = (rem_valid.groupby(['Month', 'Doc Type', '费用分类'], dropna=False)
                      .agg(记录数=('Transaction Value', 'size'),
                           交易金额=('Transaction Value', 'sum'),
                           Cash_Discount_Amount=('Cash Discount Amount', 'sum')).reset_index())
            if selected_months7:
                types7 = types7[types7['Month'].isin(selected_months7)]
            table(types7.sort_values(['Month', 'Doc Type', '费用分类']))
            if (rem_valid['费用分类'] == '其他/对账').any():
                st.warning('Remittance存在未分类交易，未计入毛利率，请在对账表核实其业务性质。')
            st.caption('若需要严格的会计毛利率，后续还需核实跨期结算、广告SA与广告投放Spend差异、售后实际支出及成本表历史变价。')
