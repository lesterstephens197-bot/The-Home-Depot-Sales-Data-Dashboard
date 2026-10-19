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

tabs = st.tabs(['1. 销售总看板', '2. 产品SKU看板', '3. 运营维度看板', '4. 退货与扣款看板', '5. 广告数据分析看板', '6. 利润率与成本率看板'])

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
    st.caption('先对全部SKU、全部月份建立统一利润底表，再筛选SKU。成本表字段固定为：SKU、产品成本价、头程运费。')
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
    ret = rtv.groupby(['Order_Month', '产品SKU'], dropna=False).agg(退货金额=('Total Cost', 'sum'), 退货件数=('QTY', 'sum'), RTV扣款=('总扣款', 'sum')).reset_index().rename(columns={'Order_Month': 'Month'})
    base = base.merge(ret, on=['Month', '产品SKU'], how='left', validate='one_to_one')
    for field in ['退货金额', '退货件数', 'RTV扣款']:
        base[field] = base[field].fillna(0)
    base['退货成本'] = base['退货金额']
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
    table(filtered[['Month', '产品SKU', '产品名称', '品牌', '销售额', '销量', '采购成本', '头程成本', '退货成本', '广告成本', '平台扣点', '其他费用', '总成本', '利润额', '利润率(%)', '成本率(%)', '预警状态']].sort_values(['Month', '产品SKU']))
    alerts = valid[valid['利润率(%)'] < 13].sort_values(['Month', '利润率(%)'])
    st.subheader(f'低于13%的SKU月度预警：{len(alerts)}条')
    table(alerts[['Month', '产品SKU', '销售额', '利润额', '利润率(%)', '成本率(%)', '预警状态']])
    st.subheader('数据一致性检查')
    checks = pd.DataFrame({'检查项目': ['SKU汇总销售额', 'SKU汇总利润额', '月度汇总销售额', '月度汇总利润额'], '差异金额': [revenue - sku_profit['销售额'].sum(), profit - sku_profit['利润额'].sum(), revenue - monthly['月销售额'].sum(), profit - monthly['月利润额'].sum()]})
    checks['检查结果'] = np.where(checks['差异金额'].abs() < .01, '通过', '异常')
    table(checks)
    st.caption('估算口径：采购及头程按成本表单位金额×销量；广告按全量比例分摊；退货按原订单月份及SKU归属，以RTV Total Cost估算退货损失；RTV总扣款不再重复扣除。零成本记录请人工确认。')
