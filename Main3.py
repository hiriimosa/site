import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc

# -------------------------
# Загрузка данных (Этап 3)
# -------------------------
df = pd.read_excel('credit_data_featured.xlsx')

# tariff_id как строка
df['tariff_id'] = df['tariff_id'].astype(str).fillna('Unknown')

# === ВАЖНО: восстанавливаем категориальный тип с правильным порядком ===
if 'age_group' in df.columns:
    age_order = ['18-25', '26-35', '36-45', '46-55', '55+']
    df['age_group'] = pd.Categorical(df['age_group'], categories=age_order, ordered=True)

if 'income_level' in df.columns:
    income_order = ['Низкий', 'Средний', 'Высокий']
    df['income_level'] = pd.Categorical(df['income_level'], categories=income_order, ordered=True)

if 'region_group' in df.columns:
    df['region_group'] = df['region_group'].astype('category')

# Все остальные возможные категориальные колонки
for col in ['gender', 'marital_status', 'job_position', 'education', 'living_region', 'segment']:
    if col in df.columns:
        df[col] = df[col].astype('category')
# =====================================================================

# === Этап 4: сегментация ===
def define_segment(row):
    """
    Расширенная интерпретируемая сегментация клиентов.
    Группы формируются на основе:
    - возраста
    - медианного дохода (относительно всех клиентов)
    - долговой нагрузки (debt_burden = credit_sum / monthly_income)
    - наличия просрочек
    - типа занятости (для выделения ИП/самозанятых)
    """
    age = row['age']
    debt = row['debt_burden']
    overdue = row['has_overdue']
    job = str(row.get('job_position', '')).upper()
    income = row['monthly_income']

    if pd.isna(debt) or pd.isna(age) or pd.isna(income):
        return 'Не определено'

    # Пороги дохода (квантили) – вычисляем один раз при старте
    income_low = df['monthly_income'].quantile(0.3)
    income_high = df['monthly_income'].quantile(0.7)

    # Категория по доходу
    if income <= income_low:
        inc_cat = 'низкий'
    elif income <= income_high:
        inc_cat = 'средний'
    else:
        inc_cat = 'высокий'

    # Категория по возрасту
    if age < 25:
        age_cat = 'молодой'
    elif age < 35:
        age_cat = 'средний'
    elif age < 55:
        age_cat = 'зрелый'
    else:
        age_cat = 'пенсионный'

    # Долговая нагрузка
    high_burden = debt > 2.0
    very_high_burden = debt > 4.0

    # Логика сегментов
    # 1. Пенсионеры (практически всегда консервативная группа)
    if age_cat == 'пенсионный':
        if overdue:
            return 'Пенсионеры с просрочками'
        if inc_cat == 'высокий' and not high_burden:
            return 'Обеспеченные пенсионеры'
        return 'Пенсионеры (стандарт)'

    # 2. Молодые специалисты с высокой нагрузкой (возраст до 30, большая нагрузка)
    if age <= 30 and high_burden:
        if overdue:
            return 'Молодые с просрочками и нагрузкой'
        return 'Молодые специалисты с высокой нагрузкой'

    # 3. Премиум-клиенты (высокий доход, низкая нагрузка, без просрочек)
    if inc_cat == 'высокий' and not high_burden and not overdue:
        return 'Премиум клиенты'

    # 4. Семейные со средним доходом (возраст 30-50, средний доход)
    if 30 <= age <= 50 and inc_cat == 'средний' and not high_burden:
        if overdue:
            return 'Семейные с просрочками'
        return 'Семейные со средним доходом'

    # 5. ИП / самозанятые (любой возраст, но нестабильный доход)
    if job in ['IP', 'SELF', 'FR']:
        if overdue:
            return 'ИП с просрочками'
        if inc_cat == 'низкий':
            return 'ИП с низким доходом'
        return 'ИП / самозанятые'

    # 6. Клиенты с очень высокой нагрузкой (критический риск)
    if very_high_burden:
        return 'Критическая нагрузка (debt > 4x)'

    # 7. Проблемные заёмщики (любые с просрочками, не попавшие в другие группы)
    if overdue:
        return 'Проблемные заёмщики'

    # 8. Остальные – стандартные клиенты
    return 'Стандартные клиенты'

df['segment'] = df.apply(define_segment, axis=1).astype('category')

# === Dash-приложение ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
app.title = "Кредитный скоринг – Аналитика"

app.layout = dbc.Container([
    html.H1("Дашборд кредитного портфеля", className="text-center my-3"),

    # ---------- ФИЛЬТРЫ ----------
    dbc.Row([
        dbc.Col([
            html.Label("Группа регионов"),
            dcc.Dropdown(
                id='region-filter',
                options=[{'label': r, 'value': r} for r in df['region_group'].cat.categories],
                multi=True, placeholder="Все регионы"
            )
        ], width=2),
        dbc.Col([
            html.Label("Тариф (tariff_id)"),
            dcc.Dropdown(
                id='tariff-filter',
                options=[{'label': t, 'value': t} for t in sorted(df['tariff_id'].unique())],
                multi=True, placeholder="Все тарифы"
            )
        ], width=2),
        dbc.Col([
            html.Label("Возрастная группа"),
            dcc.Dropdown(
                id='age-filter',
                options=[{'label': a, 'value': a} for a in df['age_group'].cat.categories],
                multi=True, placeholder="Все возрасты"
            )
        ], width=2),
        dbc.Col([
            html.Label("Уровень дохода"),
            dcc.Dropdown(
                id='income-filter',
                options=[{'label': i, 'value': i} for i in df['income_level'].cat.categories],
                multi=True, placeholder="Все уровни"
            )
        ], width=2),
        dbc.Col([
            html.Label("Сегмент"),
            dcc.Dropdown(
                id='segment-filter',
                options=[{'label': s, 'value': s} for s in df['segment'].cat.categories],
                multi=True, placeholder="Все сегменты"
            )
        ], width=2),
        dbc.Col([
            html.Button("Сбросить фильтры", id='reset-btn', className="btn btn-outline-secondary mt-4")
        ], width=2)
    ], className="mb-3"),

    # ---------- KPI ----------
    dbc.Row(id='kpi-row', className="mb-4"),

    # ---------- ГРАФИКИ ----------
    dbc.Row([
        dbc.Col(dcc.Graph(id='segment-pie'), width=4),
        dbc.Col(dcc.Graph(id='overdue-bar'), width=4),
        dbc.Col(dcc.Graph(id='debt-burden-bar'), width=4),
    ]),
    dbc.Row([
        dbc.Col(dcc.Graph(id='income-debt-scatter'), width=6),
        dbc.Col(dcc.Graph(id='pti-box'), width=6),
    ]),
    dbc.Row([
        dbc.Col(dcc.Graph(id='risk-heatmap'), width=12)
    ]),
    dbc.Row([
        dbc.Col(html.Div(id='insights-text', className="p-3 bg-light rounded"), width=12)
    ])
], fluid=True)

# ------------------------- Callback -------------------------
@app.callback(
    [Output('kpi-row', 'children'),
     Output('segment-pie', 'figure'),
     Output('overdue-bar', 'figure'),
     Output('debt-burden-bar', 'figure'),
     Output('income-debt-scatter', 'figure'),
     Output('pti-box', 'figure'),
     Output('risk-heatmap', 'figure'),
     Output('insights-text', 'children')],
    [Input('region-filter', 'value'),
     Input('tariff-filter', 'value'),
     Input('age-filter', 'value'),
     Input('income-filter', 'value'),
     Input('segment-filter', 'value')]
)
def update_dashboard(regions, tariffs, ages, incomes, segments):
    dff = df.copy()
    if regions:
        dff = dff[dff['region_group'].isin(regions)]
    if tariffs:
        dff = dff[dff['tariff_id'].isin(tariffs)]
    if ages:
        dff = dff[dff['age_group'].isin(ages)]
    if incomes:
        dff = dff[dff['income_level'].isin(incomes)]
    if segments:
        dff = dff[dff['segment'].isin(segments)]

    # KPI
    total = len(dff)
    overdue_pct = dff['has_overdue'].mean() * 100 if total > 0 else 0
    median_burden = dff['debt_burden'].median()
    avg_income = dff['monthly_income'].median()
    kpi_cards = dbc.Row([
        dbc.Col(dbc.Card([html.H4(f"{total:,}", className="text-center text-primary"),
                           html.P("Клиентов")], body=True, color="light"), width=3),
        dbc.Col(dbc.Card([html.H4(f"{overdue_pct:.2f}%", className="text-center text-danger"),
                           html.P("Доля просрочек")], body=True, color="light"), width=3),
        dbc.Col(dbc.Card([html.H4(f"{median_burden:.2f}", className="text-center text-warning"),
                           html.P("Медианная нагрузка")], body=True, color="light"), width=3),
        dbc.Col(dbc.Card([html.H4(f"{avg_income:,.0f} ₽", className="text-center text-success"),
                           html.P("Медианный доход")], body=True, color="light"), width=3),
    ])

    # График 1: pie
    seg_counts = dff['segment'].value_counts().reset_index()
    seg_counts.columns = ['segment', 'count']
    pie_fig = px.pie(seg_counts, names='segment', values='count', title='Распределение по сегментам')
    pie_fig.update_traces(textposition='inside', textinfo='percent+label')

    # График 2: доля просрочек по сегментам
    overdue_by_seg = dff.groupby('segment')['has_overdue'].mean().mul(100).reset_index()
    overdue_by_seg.columns = ['segment', 'overdue_rate']
    overdue_bar_fig = px.bar(overdue_by_seg, x='segment', y='overdue_rate',
                             title='Доля просрочек по сегментам (%)',
                             text_auto='.2f', color='segment')
    overdue_bar_fig.update_layout(showlegend=False, yaxis_title='% просрочек')

    # График 3: медианная нагрузка по сегментам
    burden_by_seg = dff.groupby('segment')['debt_burden'].median().reset_index()
    burden_by_seg.columns = ['segment', 'median_debt_burden']
    burden_bar_fig = px.bar(burden_by_seg, x='segment', y='median_debt_burden',
                            title='Медианная долговая нагрузка по сегментам',
                            text_auto='.2f', color='segment')
    burden_bar_fig.update_layout(showlegend=False, yaxis_title='Нагрузка (разы)')

    # Scatter: доход vs нагрузка
    sample_df = dff.sample(min(2000, len(dff)), random_state=42)
    scatter_fig = px.scatter(sample_df, x='monthly_income', y='debt_burden',
                             color='has_overdue',
                             title='Доход и долговая нагрузка (цвет = просрочка)',
                             opacity=0.7)
    scatter_fig.update_layout(coloraxis_colorbar=dict(title='Просрочка'))

    # Box: PTI по сегментам
    pti_fig = px.box(dff, x='segment', y='payment_to_income', color='segment',
                     title='Доля платежа в доходе (PTI) по сегментам',
                     points='outliers')
    pti_fig.update_layout(showlegend=False)

    # Heatmap: риск матрица
    risk_pivot = dff.pivot_table(values='has_overdue', index='age_group',
                                 columns='segment', aggfunc='mean')
    heat_fig = px.imshow(risk_pivot, text_auto='.1%',
                         title='Матрица риска: доля просрочек (возраст × сегмент)',
                         aspect='auto', color_continuous_scale='Reds')
    heat_fig.update_layout(xaxis_title='Сегмент', yaxis_title='Возрастная группа')

    # Текстовые выводы
    insights = []
    if total > 0:
        seg_risk = dff.groupby('segment')['has_overdue'].mean().sort_values(ascending=False)
        if not seg_risk.empty:
            insights.append(html.P(f"Самый рискованный сегмент: «{seg_risk.index[0]}» — доля просрочек {seg_risk.iloc[0]*100:.2f}%"))
        overall_median = df['debt_burden'].median()
        if median_burden > overall_median * 1.2:
            insights.append(html.P(f"Медианная нагрузка ({median_burden:.2f}) выше среднерыночной ({overall_median:.2f})"))
        age_risk = dff.groupby('age_group')['has_overdue'].mean()
        if not age_risk.empty:
            insights.append(html.P(f"Возраст с макс. риском: «{age_risk.idxmax()}» ({age_risk.max()*100:.2f}%)"))
        high_pti = (dff['payment_to_income'] > 0.5).mean() * 100
        insights.append(html.P(f"Доля клиентов с платежом >50% дохода: {high_pti:.1f}%"))
    else:
        insights.append(html.P("Нет данных для выбранных фильтров."))
    insights_block = html.Div([html.H5("Ключевые выводы"), *insights])

    return (kpi_cards, pie_fig, overdue_bar_fig, burden_bar_fig,
            scatter_fig, pti_fig, heat_fig, insights_block)

# Кнопка сброса
@app.callback(
    [Output('region-filter', 'value'),
     Output('tariff-filter', 'value'),
     Output('age-filter', 'value'),
     Output('income-filter', 'value'),
     Output('segment-filter', 'value')],
    [Input('reset-btn', 'n_clicks')]
)
def reset_filters(n_clicks):
    return None, None, None, None, None
server = app.server  # нужно для gunicorn

if __name__ == '__main__':
    app.run(debug=False, port=8051)
