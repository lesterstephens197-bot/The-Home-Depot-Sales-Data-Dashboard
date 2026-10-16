
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='多维电商业务看板', page_icon='📊', layout='wide')
st.title('📊 多维电商业务智能分析看板')

@st.cache_data
def read_excel(f):
    d = pd.read_excel(f)
    d.columns = d.columns.astype(str).str.strip()
    return d

def pick(df, names):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None

def number(df, col, default=0):
    if col not in df.columns:
        df[col] = default
    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False).str.replace('$', '', regex=False), errors='coerce').fillna(default)

def divide(a, b):
    return np.where(np.asarray(b) != 0, np.asarray(a) / np.asarray(b), np.nan)

def chart(df, x, y, title, color=None):
    if df.empty:
        st.info('当前筛选条件下没有数据')
        return
    fig = px.bar(df, x=x, y=y, color=color, barmode='group', title=title, text_auto='.2f')
    fig.update_layout(xaxis_type='category', margin=dict(t=60, b=30))
    st.plotly_chart(fig, use_container_width=True)

def rate_table(sales, returns, sales_month, return_month):
    s = sales.groupby([sales_month, '产品SKU'], dropna=False).agg(销售件数=('Quantity','sum'), 销售金额=('Total Cost','sum')).reset_index().rename(columns={sales_month:'月份'})
    r = returns.groupby([return_month, '产品SKU'], dropna=False).agg(退货件数=('QTY','sum'), 退货金额=('Total Cost','sum'), 扣款金额=('总扣款','sum')).reset_index().rename(columns={return_month:'月份'})
    d = s.merge(r, on=['月份','产品SKU'], how='outer')
    for c in ['销售件数','销售金额','退货件数','退货金额','扣款金额']:
        d[c] = d[c].fillna(0)
    d['数量退货率(%)'] = divide(d['退货件数'], d['销售件数']) * 100
    d['金额退货率(%)'] = divide(d['退货金额'], d['销售金额']) * 100
    return d.sort_values(['月份','产品SKU'])

st.sidebar.header('📁 数据源上传')
files = [st.sidebar.file_uploader(label, type=['xlsx','xls'], key=str(i)) for i,label in enumerate(['1. 销售数据','2. RTV退货数据','3. 产品成本数据','4. 广告数据'])]
if not all(files):
    st.info('请上传四份 Excel 数据表以显示看板。')
    st.stop()

sales, rtv, cost, ads = [read_excel(f) for f in files]
for name, df, cols in [('销售表',sales,['产品SKU','Order Date','Quantity','Total Cost']), ('RTV表',rtv,['产品SKU','Order Date','RTV Date','QTY','Total Cost','总扣款'])]:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        st.error(f'{name}缺少字段：{missing}')
        st.stop()

for d in [sales,rtv]:
    d['产品SKU'] = d['产品SKU'].astype('string').str.strip().fillna('未知SKU')
for c in ['Quantity','Total Cost']:
    number(sales,c)
for c in ['QTY','Total Cost','总扣款']:
    number(rtv,c)
for c in ['Order Date']:
    sales[c] = pd.to_datetime(sales[c], errors='coerce')
for c in ['Order Date','RTV Date']:
    rtv[c] = pd.to_datetime(rtv[c], errors='coerce')
sales['Month'] = sales['Order Date'].dt.strftime('%Y-%m')
rtv['Order_Month'] = rtv['Order Date'].dt.strftime('%Y-%m')
rtv['RTV_Month'] = rtv['RTV Date'].dt.strftime('%Y-%m')
for col in ['产品名称','品牌','运营','Customer Order Number']:
    if col not in sales:
        sales[col] = sales.index.astype(str) if col == 'Customer Order Number' else '未填写'

all_skus = sorted(set(sales['产品SKU'].dropna()) | set(rtv['产品SKU'].dropna()))

tabs = st.tabs(['1. 销售总看板','2. 产品SKU看板','3. 运营维度看板','4. 退货与扣款看板','5. 广告数据看板','6. 利润率与成本率看板'])

with tabs[0]:
    st.header('整体销售数据')
    revenue = sales['Total Cost'].sum()
    qty = sales['Quantity'].sum()
    orders = sales['Customer Order Number'].nunique()
    days = (sales['Order Date'].max()-sales['Order Date'].min()).days+1 if sales['Order Date'].notna().any() else 0
    for c, label, val in zip(st.columns(5), ['总销售额','总销量','总订单数','平均客单价','日均销量'], [f'${revenue:,.2f}',f'{qty:,.0f}',f'{orders:,}',f'${revenue/orders:,.2f}' if orders else '—',f'{qty/days:,.2f}' if days else '—']):
        c.metric(label,val)
    m = sales.groupby('Month').agg(总销售额=('Total Cost','sum'),总销量=('Quantity','sum'),总订单数=('Customer Order Number','nunique')).reset_index()
    m['平均客单价'] = divide(m['总销售额'],m['总订单数'])
    m['日均销量'] = divide(m['总销量'],m['Month'].map(lambda x: pd.Period(x).days_in_month))
    metric = st.selectbox('月度趋势指标', ['总销售额','总销量','总订单数','平均客单价','日均销量'])
    chart(m,'Month',metric,f'月度{metric}')
    st.dataframe(m,use_container_width=True,hide_index=True)

with tabs[1]:
    st.header('SKU销售排名与月度趋势')
    sku_month = sales.groupby(['Month','产品SKU']).agg(销售额=('Total Cost','sum'),销量=('Quantity','sum'),订单数=('Customer Order Number','nunique'),有销售天数=('Order Date','nunique')).reset_index()
    sku_month['日均销量'] = divide(sku_month['销量'],sku_month['有销售天数'])
    sku_month['销售额占比(%)'] = divide(sku_month['销售额'],sku_month.groupby('Month')['销售额'].transform('sum'))*100
    sku_month['月度排名'] = sku_month.groupby('Month')['销售额'].rank(ascending=False,method='min').astype(int)
    sku_month['SKU等级'] = pd.cut(sku_month.groupby('Month')['销售额'].rank(ascending=False,pct=True),bins=[0,.2,.5,.8,1],labels=['A','B','C','D'],include_lowest=True)
    st.dataframe(sku_month.sort_values(['Month','月度排名']),use_container_width=True,hide_index=True)
    selected = st.selectbox('搜索SKU',sorted(sales['产品SKU'].unique()),key='sku_sales')
    sd = sku_month[sku_month['产品SKU']==selected]
    c1,c2=st.columns(2)
    with c1: chart(sd,'Month','销量','SKU每月销量')
    with c2: chart(sd,'Month','销售额','SKU每月销售额')

with tabs[2]:
    st.header('运营人员月度销售数据')
    op = sales.groupby(['Month','运营']).agg(销售额=('Total Cost','sum'),销量=('Quantity','sum'),订单数=('Customer Order Number','nunique')).reset_index()
    st.dataframe(op,use_container_width=True,hide_index=True)
    chart(op,'Month','销售额','运营人员月度销售额','运营')

with tabs[3]:
    st.header('退货与扣款分析')
    chosen = st.multiselect('筛选产品SKU（不选择代表全部）',all_skus,key='rtv_skus')
    ss = sales[sales['产品SKU'].isin(chosen)].copy() if chosen else sales.copy()
    rr = rtv[rtv['产品SKU'].isin(chosen)].copy() if chosen else rtv.copy()
    sq,sa = ss['Quantity'].sum(),ss['Total Cost'].sum()
    rq,ra,ded = rr['QTY'].sum(),rr['Total Cost'].sum(),rr['总扣款'].sum()
    vals=[f'{rq:,.0f}',f'${ra:,.2f}',f'${ded:,.2f}',f'{rq/sq*100:.2f}%' if sq else '—',f'{ra/sa*100:.2f}%' if sa else '—']
    for c,l,v in zip(st.columns(5),['退货件数','退货商品金额','总扣款','数量退货率','金额退货率'],vals): c.metric(l,v)
    sub = st.tabs(['1. SKU退货率排行榜','2. 退货原因占比','3. Order Date视角','4. RTV Date视角'])
    with sub[0]:
        s=ss.groupby('产品SKU').agg(销售件数=('Quantity','sum'),销售金额=('Total Cost','sum')).reset_index()
        r=rr.groupby('产品SKU').agg(退货件数=('QTY','sum'),退货金额=('Total Cost','sum'),扣款金额=('总扣款','sum')).reset_index()
        d=s.merge(r,on='产品SKU',how='outer').fillna(0)
        d['数量退货率(%)']=divide(d['退货件数'],d['销售件数'])*100
        d['金额退货率(%)']=divide(d['退货金额'],d['销售金额'])*100
        rank_by=st.selectbox('排行榜指标',['数量退货率(%)','金额退货率(%)','退货件数','扣款金额'])
        min_sales=st.number_input('最少销售件数（避免低销量SKU排名失真）',min_value=0,value=10,step=1)
        ranking=d[d['销售件数']>=min_sales].sort_values(rank_by,ascending=False,na_position='last')
        st.dataframe(ranking,use_container_width=True,hide_index=True)
        chart(ranking.head(15),'产品SKU',rank_by,'SKU退货Top 15')
    with sub[1]:
        reason=pick(rr,['Return Reason','RTV Reason','Reason','Reason Description','Return Reason Description','退货原因','退货理由','原因'])
        if reason is None:
            st.warning('RTV文件未发现退货原因字段。请提供 Return Reason / RTV Reason / 退货原因 列。')
        else:
            x=rr.copy()
            x[reason]=x[reason].fillna('未填写').astype(str)
            reasons=x.groupby(reason).agg(退货件数=('QTY','sum'),退货金额=('Total Cost','sum'),扣款金额=('总扣款','sum')).reset_index()
            base=st.radio('占比依据',['退货件数','退货金额','扣款金额'],horizontal=True)
            reasons['占比(%)']=divide(reasons[base],reasons[base].sum())*100
            st.dataframe(reasons.sort_values(base,ascending=False),use_container_width=True,hide_index=True)
            if reasons[base].sum()>0:
                fig=px.pie(reasons,names=reason,values=base,title=f'退货原因按{base}占比',hole=.4)
                st.plotly_chart(fig,use_container_width=True)
                chart(reasons.sort_values(base,ascending=False),reason,base,'退货原因分布')
    for tab,month,title in [(sub[2],'Order_Month','Order Date（原订单月份）'),(sub[3],'RTV_Month','RTV Date（实际退货月份）')]:
        with tab:
            st.subheader(title)
            detail=rate_table(ss,rr,'Month',month)
            if month=='RTV_Month':
                st.info('RTV Date口径：当月退货 / 当月销售。退货可能来自更早月份，因此该比率可能超过100%，不等同订单批次最终退货率。')
            else:
                st.info('Order Date口径：按退货记录关联的原订单月份归属，最近订单月份可能因退货滞后而低估。')
            monthly=detail.groupby('月份',dropna=False)[['销售件数','销售金额','退货件数','退货金额','扣款金额']].sum().reset_index()
            monthly['数量退货率(%)']=divide(monthly['退货件数'],monthly['销售件数'])*100
            monthly['金额退货率(%)']=divide(monthly['退货金额'],monthly['销售金额'])*100
            st.dataframe(monthly,use_container_width=True,hide_index=True)
            for metric in ['数量退货率(%)','金额退货率(%)']:
                chart(monthly,'月份',metric,f'{title}：每月{metric}')
            st.subheader('SKU × 月份明细')
            st.dataframe(detail,use_container_width=True,hide_index=True)

with tabs[4]:
    st.header('广告数据分析')
    for c in ['Spend','SPA Revenue','Clicks','Impressions']:
        number(ads,c)
    spend=ads['Spend'].sum()
    rev=ads['SPA Revenue'].sum()
    c1,c2,c3=st.columns(3)
    c1.metric('广告花费',f'${spend:,.2f}')
    c2.metric('广告销售额',f'${rev:,.2f}')
    c3.metric('ROAS',f'{rev/spend:.2f}' if spend else '—')
    if 'Campaign Name' in ads:
        campaigns=ads.groupby('Campaign Name').agg(广告花费=('Spend','sum'),广告销售额=('SPA Revenue','sum'),点击量=('Clicks','sum')).reset_index()
        campaigns['ROAS']=divide(campaigns['广告销售额'],campaigns['广告花费'])
        st.dataframe(campaigns,use_container_width=True,hide_index=True)
        chart(campaigns.sort_values('广告花费',ascending=False).head(10),'Campaign Name','广告花费','广告活动花费Top 10')

with tabs[5]:
    st.header('利润率与成本率深度分析')
    st.caption('目标利润率 ≥ 13%；采购、头程按SKU单位成本估算；广告及退货费用使用可追溯或分摊口径。')
    chosen=st.multiselect('筛选产品SKU（不选择代表全部）',sorted(sales['产品SKU'].unique()),key='profit_skus')
    ss=sales[sales['产品SKU'].isin(chosen)].copy() if chosen else sales.copy()
    cost=cost.copy()
    sku_col=pick(cost,['SKU','产品SKU','Vendor Part #','Vendor Part'])
    unit_col=pick(cost,['产品成本价','采购成本价','成本价','单位成本','Product Cost'])
    freight_col=pick(cost,['头程运费','头程成本','单位头程运费','Freight Cost'])
    if not sku_col or not unit_col:
        st.error('成本表必须有 SKU 和单位产品成本字段。')
        st.stop()
    cost['产品SKU']=cost[sku_col].astype('string').str.strip()
    cost['单位采购成本']=pd.to_numeric(cost[unit_col],errors='coerce')
    cost['单位头程']=pd.to_numeric(cost[freight_col],errors='coerce').fillna(0) if freight_col else 0.0
    duplicates=cost['产品SKU'].duplicated().sum()
    if duplicates:
        st.warning(f'成本表存在 {duplicates} 条重复SKU记录；当前采用每个SKU第一条成本，建议核实。')
    cc=cost[['产品SKU','单位采购成本','单位头程']].drop_duplicates('产品SKU')
    ss=ss.merge(cc,on='产品SKU',how='left',validate='many_to_one')
    missing=ss.loc[ss['单位采购成本'].isna(),'产品SKU'].unique().tolist()
    if missing:
        st.error(f'以下SKU缺少成本数据，不能可靠计算利润：{missing[:30]}。请先补齐成本表。')
        st.stop()
    ss['采购成本']=ss['Quantity']*ss['单位采购成本']
    ss['头程成本']=ss['Quantity']*ss['单位头程']
    # RTV费用以原订单月份和SKU归属
    ret=rtv.groupby(['Order_Month','产品SKU']).agg(退货成本项=('Total Cost','sum')).reset_index().rename(columns={'Order_Month':'Month'})
    base=ss.groupby(['Month','产品SKU']).agg(销售额=('Total Cost','sum'),销量=('Quantity','sum'),采购成本=('采购成本','sum'),头程成本=('头程成本','sum')).reset_index()
    base=base.merge(ret,on=['Month','产品SKU'],how='left')
    base['退货成本项']=base['退货成本项'].fillna(0)
    # 广告费用按整体销售额比例分摊
    ad_total=ads['Spend'].sum()
    all_rev=sales['Total Cost'].sum()
    ad_rate=ad_total/all_rev if all_rev>0 else 0
    st.sidebar.header('利润模型参数')
    platform_rate=st.sidebar.number_input('平台费率(%)',value=3.25,min_value=0.0,step=0.25)/100
    other_rate=st.sidebar.number_input('其他费用率(%)',value=2.0,min_value=0.0,step=0.25)/100
    st.sidebar.caption(f'广告分摊率（整体花费/整体销售额）：{ad_rate*100:.2f}%')
    base['广告成本项']=base['销售额']*ad_rate
    base['平台扣点项']=base['销售额']*platform_rate
    base['其他费用项']=base['销售额']*other_rate
    costs=['采购成本','头程成本','退货成本项','广告成本项','平台扣点项','其他费用项']
    base['总成本']=base[costs].sum(axis=1)
    base['利润额']=base['销售额']-base['总成本']
    base['利润率(%)']=divide(base['利润额'],base['销售额'])*100
    base['总成本率(%)']=divide(base['总成本'],base['销售额'])*100
    base['采购成本率(%)']=divide(base['采购成本'],base['销售额'])*100
    base['状态']=np.select([base['利润率(%)']<10,base['利润率(%)']<13],['严重预警','低于目标'],default='达标')
    base.loc[base['利润率(%)'].isna(),'状态']='无销售额'
    rev=base['销售额'].sum()
    profit=base['利润额'].sum()
    margin=profit/rev*100 if rev else np.nan
    c1,c2,c3,c4=st.columns(4)
    c1.metric('销售额',f'${rev:,.2f}')
    c2.metric('利润额',f'${profit:,.2f}')
    c3.metric('综合利润率',f'{margin:.2f}%' if rev else '—',delta=f'{margin-13:.2f}个百分点' if rev else None)
    c4.metric('综合成本率',f'{base["总成本"].sum()/rev*100:.2f}%' if rev else '—')
    if rev:
        if margin<10: st.error(f'严重预警：综合利润率 {margin:.2f}%，低于13%目标 {13-margin:.2f} 个百分点。')
        elif margin<13: st.warning(f'利润率未达标：当前 {margin:.2f}%，目标至少13%。')
        else: st.success(f'利润率达标：当前 {margin:.2f}%，高于13%目标。')
    monthly=base.groupby('Month')[['销售额','销量','利润额','总成本']+costs].sum().reset_index()
    monthly['利润率(%)']=divide(monthly['利润额'],monthly['销售额'])*100
    monthly['总成本率(%)']=divide(monthly['总成本'],monthly['销售额'])*100
    monthly['采购成本率(%)']=divide(monthly['采购成本'],monthly['销售额'])*100
    monthly['利润目标差(百分点)']=monthly['利润率(%)']-13
    monthly['预警状态']=np.select([monthly['利润率(%)']<10,monthly['利润率(%)']<13],['严重预警','低于目标'],default='达标')
    monthly.loc[monthly['利润率(%)'].isna(),'预警状态']='无销售额'
    st.subheader('每月利润率与13%目标线')
    fig=go.Figure()
    fig.add_trace(go.Bar(x=monthly['Month'],y=monthly['利润率(%)'],name='利润率',marker_color=['#dc3545' if pd.notna(v) and v<13 else '#198754' for v in monthly['利润率(%)']]))
    fig.add_hline(y=13,line_dash='dash',line_color='orange',annotation_text='目标13%')
    fig.update_layout(xaxis_type='category',yaxis_title='利润率 (%)')
    st.plotly_chart(fig,use_container_width=True)
    chart(monthly,'Month','总成本率(%)','月度总成本率')
    chart(monthly,'Month','采购成本率(%)','月度采购成本率')
    chart(monthly,'Month','利润额','月度利润额')
    st.subheader('月度成本结构')
    structure=monthly.melt(id_vars='Month',value_vars=costs,var_name='成本类别',value_name='金额')
    fig=px.bar(structure,x='Month',y='金额',color='成本类别',title='每月各项成本构成',barmode='stack')
    st.plotly_chart(fig,use_container_width=True)
    st.subheader('月度利润率与成本率汇总')
    st.dataframe(monthly,use_container_width=True,hide_index=True)
    st.subheader('SKU利润率排行榜与预警')
    sku=base.groupby('产品SKU')[['销售额','销量','利润额','总成本']+costs].sum().reset_index()
    sku['利润率(%)']=divide(sku['利润额'],sku['销售额'])*100
    sku['成本率(%)']=divide(sku['总成本'],sku['销售额'])*100
    sku['预警状态']=np.select([sku['利润率(%)']<10,sku['利润率(%)']<13],['严重预警','低于目标'],default='达标')
    sku.loc[sku['利润率(%)'].isna(),'预警状态']='无销售额'
    st.dataframe(sku.sort_values('利润率(%)'),use_container_width=True,hide_index=True)
    alerts=base[base['利润率(%)']<13].sort_values(['Month','利润率(%)'])
    st.subheader(f'月度SKU预警明细（{len(alerts)}条）')
    st.dataframe(alerts[['Month','产品SKU','销售额','利润额','利润率(%)','总成本率(%)','状态']],use_container_width=True,hide_index=True)
    st.caption('口径提醒：广告按整体销售额比例分摊；退货按原订单月归属；未将RTV总扣款与退货商品金额同时扣除，以避免可能的重复计算。实际利润需根据费用和结算明细核对。')
