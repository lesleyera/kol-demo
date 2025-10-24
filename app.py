import streamlit as st
import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe
import os
import altair as alt
from datetime import datetime, timedelta 

# -----------------------------------------------------------------
# 0. 전역 변수 선언 및 유틸리티 함수
# -----------------------------------------------------------------
master_df = None
activities_df = None

def get_max_value(df, column, is_percentage=False):
    """주어진 컬럼의 최대값보다 10% 더 큰 값을 계산합니다."""
    if df.empty or column not in df.columns:
        return 100 if is_percentage else 10 # 기본값
    
    max_val = df[column].max()
    
    if is_percentage:
        # 백분율은 최대 100%로 고정
        return 100 
    else:
        # 건수/금액은 최대값보다 10% 크게 설정
        return max_val * 1.1 if max_val > 0 else 10


# -----------------------------------------------------------------
# 1. Google Sheets 인증 및 데이터 로드 (이전과 동일)
# -----------------------------------------------------------------

@st.cache_data(ttl=60) 
def load_data_from_gsheet():
    
    SPREADSHEET_NAME = "KOL 관리 시트" 
    WORKSHEET1_NAME = "KOL_Master"
    WORKSHEET2_NAME = "Activities"
    
    try:
        # --- 인증 로직 ---
        gc = None
        script_dir = os.path.dirname(os.path.abspath(__file__))
        creds_path = os.path.join(script_dir, 'google_credentials.json')
        
        if os.path.exists(creds_path):
            gc = gspread.service_account(filename=creds_path)
        elif 'gcp_service_account' in st.secrets:
            creds_dict = st.secrets['gcp_service_account']
            gc = gspread.service_account_from_dict(creds_dict)
        else:
            st.error("인증 실패: 'google_credentials.json' 파일을 찾거나 Streamlit 'Secrets' 설정을 확인하세요.")
            return None, None

        # --- 데이터 로드 ---
        sh = gc.open(SPREADSHEET_NAME)
        master_df = get_as_dataframe(sh.worksheet(WORKSHEET1_NAME)).dropna(how='all') 
        activities_df = get_as_dataframe(sh.worksheet(WORKSHEET2_NAME)).dropna(how='all')
        
        # --- 데이터 타입 변환 및 계산 ---
        master_df['Contract_End'] = pd.to_datetime(master_df['Contract_End'], errors='coerce')
        activities_df['Due_Date'] = pd.to_datetime(activities_df['Due_Date'], errors='coerce')
        master_df['Budget (USD)'] = pd.to_numeric(master_df['Budget (USD)'], errors='coerce').fillna(0)
        master_df['Spent (USD)'] = pd.to_numeric(master_df['Spent (USD)'], errors='coerce').fillna(0)
        
        activities_df['Done'] = activities_df['Status'].apply(lambda x: 1 if x == 'Done' else 0)
        activity_summary = activities_df.groupby('Kol_ID').agg(Total=('Activity_ID', 'count'), Done=('Done', 'sum')).reset_index()
        activity_summary['Completion_Rate'] = (activity_summary['Done'] / activity_summary['Total']) * 100
        master_df = pd.merge(master_df, activity_summary[['Kol_ID', 'Completion_Rate']], on='Kol_ID', how='left').fillna({'Completion_Rate': 0})
        master_df['Utilization_Rate'] = (master_df['Spent (USD)'] / master_df['Budget (USD)']) * 100
        master_df['Utilization_Rate'] = master_df['Utilization_Rate'].fillna(0).apply(lambda x: min(x, 100))
        
        activities_df['YearMonth'] = activities_df['Due_Date'].dt.to_period('M').astype(str)

        st.success("🎉 데이터 로드 및 초기 계산 완료!")
        return master_df, activities_df

    except Exception as e:
        st.error(f"데이터 로드 중 에러 발생: {e}")
        return None, None

# -----------------------------------------------------------------
# 2. 조건부 서식 함수 정의 (이전과 동일)
# -----------------------------------------------------------------

def highlight_master_row(row, today, alert_days=30):
    """KOL_Master 테이블에서 계약 만료 임박 행을 강조합니다."""
    contract_end = row['Contract_End']
    is_imminent = False
    if pd.notnull(contract_end):
        is_imminent = (contract_end.date() >= today.date()) and \
                      (contract_end.date() <= (today + timedelta(days=alert_days)).date())
    
    if is_imminent:
        return ['background-color: #ffd70040'] * len(row) 
    return [''] * len(row)

def highlight_activity_row(row, today):
    """Activities 테이블에서 지연된 활동 행을 강조합니다."""
    due_date = row['Due_Date']
    status = row['Status']
    
    is_overdue = False
    if pd.notnull(due_date):
        is_overdue = (due_date.date() < today.date()) and (status != 'Done')
    
    if is_overdue:
        return ['background-color: #ff4c4c40'] * len(row)
    return [''] * len(row)

# -----------------------------------------------------------------
# 3. Streamlit UI 그리기 
# -----------------------------------------------------------------

st.set_page_config(page_title="KOL 대시보드 MVP", layout="wide")

# --- 💡💡💡 CSS: 흰색 배경 강제 설정 💡💡💡 ---
st.markdown(
    """
    <style>
    /* 전체 배경을 흰색으로 강제 */
    .stApp {
        background-color: #FFFFFF !important; 
        color: #000000 !important; /* 기본 텍스트 검은색 */
    }
    /* 헤더 및 부제목 색상 */
    h1, h2, h3, h4, h5, h6 {
        color: #111111 !important; 
    }
    /* 사이드바 배경 및 텍스트 */
    [data-testid="stSidebar"] {
        background-color: #F8F9FA !important; /* 약간 밝은 회색 */
    }
    [data-testid="stSidebar"] * {
        color: #333333 !important; /* 사이드바 텍스트 어둡게 */
    }
    /* 테이블 및 차트 배경 */
    .stDataFrame, .stPlotlyChart {
        background-color: #FFFFFF !important; /* 흰색 */
        border: 1px solid #EEEEEE; /* 옅은 테두리 */
        border-radius: 8px;
    }
    /* 알림 메시지 배경 */
    .stAlert {
        color: inherit !important; /* 글자색 상속 */
    }
    /* 메트릭 값 색상 */
    [data-testid="stMetricValue"] {
        color: #222222 !important;
    }
    /* 메트릭 레이블 색상 */
    [data-testid="stMetricLabel"] {
        color: #555555 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
# ---------------------------------------------------------

st.title("📊 KOL 활동 관리 대시보드 (MVP)")

master_df, activities_df = load_data_from_gsheet()

st.sidebar.subheader("KOL 상세 조회 필터")
if master_df is not None:
    kol_names = master_df['Name'].tolist()
    selected_name = st.sidebar.selectbox("KOL 이름을 선택하세요:", ["전체"] + kol_names)
else:
    selected_name = st.sidebar.selectbox("KOL 이름을 선택하세요:", ["전체"])

if master_df is not None and activities_df is not None:

    if selected_name == "전체":
        
        # ===================================
        # 1. KPI 요약
        # ===================================
        st.header("1. KPI 요약")
        
        total_budget = master_df['Budget (USD)'].sum()
        total_spent = master_df['Spent (USD)'].sum()
        avg_completion = master_df['Completion_Rate'].mean()
        avg_utilization = (total_spent / total_budget) * 100 if total_budget > 0 else 0
        
        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
        with col_kpi1: st.metric(label="총 KOL 인원", value=master_df.shape[0])
        with col_kpi2: st.metric(label="총 예산 규모", value=f"${total_budget:,.0f}")
        with col_kpi3: st.metric(label="평균 완료율", value=f"{avg_completion:.1f}%")
        with col_kpi4: st.metric(label="예산 활용률", value=f"{avg_utilization:.1f}%")
        
        st.divider()

        # ===================================
        # 2. 주요 차트 현황 (3x2 레이아웃 및 축 설정)
        # ===================================
        st.header("2. 주요 차트 현황")
        
        # --- 💡 축 최대값 계산 ---
        max_count = get_max_value(activities_df.groupby('YearMonth').size().reset_index(name='Count'), 'Count')
        max_budget = get_max_value(master_df.groupby('Country')['Budget (USD)'].sum().reset_index(name='Total_Budget'), 'Total_Budget')
        
        # -----------------------------------
        # Row 1: 차트 3개 (파이차트, 파이차트, 혼합 세로 막대+선)
        # -----------------------------------
        col_r1_c1, col_r1_c2, col_r1_c3 = st.columns(3)

        with col_r1_c1:
            st.subheader("활동 상태별 분포")
            status_counts = activities_df['Status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            
            base = alt.Chart(status_counts).encode(theta=alt.Theta("Count", stack=True), color=alt.Color("Status", title='상태'))
            
            # Pie Chart
            pie = base.mark_arc(outerRadius=100, innerRadius=60).encode(tooltip=['Status', alt.Tooltip('Count', title='활동 건수', format='d')])
            
            # Text Label for Pie Chart (옆에 위치)
            text_labels = base.mark_text(radius=120, fill='black', fontSize=14).encode( # 💡 검은색 텍스트
                text=alt.Text('Count', format='d'),
                order=alt.Order('Count', sort='descending')
            )

            chart1 = (pie + text_labels).interactive()
            st.altair_chart(chart1, use_container_width=True)
        
        with col_r1_c2:
            st.subheader("KOL 등급별 분포")
            type_counts = master_df['KOL_Type'].value_counts().reset_index()
            type_counts.columns = ['Type', 'Count']
            
            base = alt.Chart(type_counts).encode(theta=alt.Theta("Count", stack=True), color=alt.Color("Type", title='등급'))
            
            # Pie Chart
            pie = base.mark_arc(outerRadius=100, innerRadius=60).encode(tooltip=['Type', alt.Tooltip('Count', title='KOL 건수', format='d')])
            
            # Text Label for Pie Chart (옆에 위치)
            text_labels = base.mark_text(radius=120, fill='black', fontSize=14).encode( # 💡 검은색 텍스트
                text=alt.Text('Count', format='d'),
                order=alt.Order('Count', sort='descending')
            )

            chart2 = (pie + text_labels).interactive()
            st.altair_chart(chart2, use_container_width=True)
                
        with col_r1_c3:
            st.subheader("월별 총 활동 스케줄")
            timeline_data = activities_df.groupby('YearMonth').size().reset_index(name='Count')
            
            # Bar Chart (Volume)
            bar_chart = alt.Chart(timeline_data).mark_bar(color='#4c78a8').encode(
                x=alt.X('YearMonth', title='월별 마감일', sort=timeline_data['YearMonth'].tolist()),
                y=alt.Y('Count', title='활동 건수 (건)', axis=alt.Axis(format='d'), scale=alt.Scale(domain=[0, max_count])), 
                tooltip=['YearMonth', alt.Tooltip('Count', title='활동 건수', format='d')]
            )

            # Text Label for Bar Chart
            text_bar = bar_chart.mark_text(
                align='center',
                baseline='bottom',
                dy=-5, 
                color='black' # 💡 검은색 텍스트
            ).encode(
                text=alt.Text('Count', format='d')
            )

            # Line Chart (Trend)
            line_chart = alt.Chart(timeline_data).mark_line(point=True, color='red').encode(
                x=alt.X('YearMonth'), 
                y=alt.Y('Count'), 
                tooltip=['YearMonth', alt.Tooltip('Count', title='활동 건수', format='d')]
            )

            chart3 = (bar_chart + text_bar + line_chart).interactive()
            st.altair_chart(chart3, use_container_width=True)

        st.divider()

        # -----------------------------------
        # Row 2: 차트 3개 (꺾은선, 혼합 차트 분리, 세로 막대)
        # -----------------------------------
        col_r2_c1, col_r2_c2, col_r2_c3 = st.columns(3)

        with col_r2_c1:
            st.subheader("월별 완료 활동 트렌드")
            completed_df = activities_df[activities_df['Status'] == 'Done'].copy()
            completed_df['YearMonth'] = completed_df['Due_Date'].dt.to_period('M').astype(str)
            completed_timeline = completed_df.groupby('YearMonth').size().reset_index(name='Completed')
            
            max_completed = get_max_value(completed_timeline, 'Completed')

            line = alt.Chart(completed_timeline).mark_line(point=True, color='green').encode(
                x=alt.X('YearMonth', title='월별 완료 시점', sort=completed_timeline['YearMonth'].tolist()),
                y=alt.Y('Completed', title='완료된 활동 건수 (건)', axis=alt.Axis(format='d'), scale=alt.Scale(domain=[0, max_completed])), 
                tooltip=['YearMonth', alt.Tooltip('Completed', title='완료된 활동 건수', format='d')]
            )
            
            text_line = line.mark_text(
                align='left',
                baseline='middle',
                dx=5, 
                color='green'
            ).encode(
                text=alt.Text('Completed', format='d')
            )
            
            chart4 = (line + text_line).interactive()
            st.altair_chart(chart4, use_container_width=True)

        with col_r2_c2:
            st.subheader("국가별 총 예산 (USD)") 
            country_summary = master_df.groupby('Country').agg(
                Total_Budget=('Budget (USD)', 'sum'),
            ).reset_index()

            max_budget_single = get_max_value(country_summary, 'Total_Budget')

            bar = alt.Chart(country_summary).mark_bar().encode(
                x=alt.X('Total_Budget', title='총 예산 (USD)', axis=alt.Axis(format='$,.0f'), scale=alt.Scale(domain=[0, max_budget_single])), 
                y=alt.Y('Country', title='국가', sort='-x'),
                tooltip=['Country', alt.Tooltip('Total_Budget', title='총 예산', format='$,.0f')]
            )

            # Text Label for Bar Chart
            text_bar = bar.mark_text(
                align='left',
                baseline='middle',
                dx=5,
                color='black' # 💡 검은색 텍스트
            ).encode(
                text=alt.Text('Total_Budget', format='$,.0f')
            )

            st.altair_chart(bar + text_bar, use_container_width=True)
        
        with col_r2_c3:
            st.subheader("활동 유형별 분포")
            type_counts = activities_df['Activity_Type'].value_counts().reset_index()
            type_counts.columns = ['Type', 'Count']
            
            max_type_count = get_max_value(type_counts, 'Count')

            bar = alt.Chart(type_counts).mark_bar().encode(
                x=alt.X('Type', title='활동 유형'), 
                y=alt.Y('Count', title='활동 건수 (건)', axis=alt.Axis(format='d'), scale=alt.Scale(domain=[0, max_type_count])), 
                tooltip=['Type', alt.Tooltip('Count', title='활동 건수', format='d')]
            )
            
            text_bar = bar.mark_text(
                align='center',
                baseline='bottom',
                dy=-5,
                color='black' # 💡 검은색 텍스트
            ).encode(
                text=alt.Text('Count', format='d')
            )

            chart6 = (bar + text_bar).interactive()
            st.altair_chart(chart6, use_container_width=True)

        st.divider()

        # -----------------------------------
        # Row 3: 새로운 차트 - 우수 KOL 순위 (세로 막대, 폭 자동)
        # -----------------------------------
        st.subheader("🏆 우수 KOL별 완료율 순위 (Top 10)")
        
        top_kols = master_df.sort_values(by='Completion_Rate', ascending=False).head(10).reset_index(drop=True)
        max_completion = get_max_value(top_kols, 'Completion_Rate', is_percentage=True)
        
        bar = alt.Chart(top_kols).mark_bar().encode( 
            x=alt.X('Name', title='KOL 이름', sort='-y'), 
            y=alt.Y('Completion_Rate', title='활동 완료율 (%)', axis=alt.Axis(format='.1f'), scale=alt.Scale(domain=[0, max_completion])), 
            color=alt.Color('Completion_Rate', title='완료율 (%)', scale=alt.Scale(range='heatmap')),
            tooltip=['Name', alt.Tooltip('Completion_Rate', title='완료율', format='.1f')]
        )
        
        text_bar = bar.mark_text(
            align='center',
            baseline='bottom',
            dy=-5,
            color='black' # 💡 검은색 텍스트
        ).encode(
            text=alt.Text('Completion_Rate', format='.1f')
        )
        
        chart7 = (bar + text_bar).interactive()
        st.altair_chart(chart7, use_container_width=True)


        st.divider()

        # ===================================
        # 3. 경고 및 알림 (Alerts)
        # ===================================
        st.header("3. 경고 및 알림 (Alerts)")
        
        today = datetime.now()
        alert_found = False

        contract_alert_date = today + timedelta(days=30)
        imminent_contracts = master_df[
            (master_df['Contract_End'] <= contract_alert_date) &
            (master_df['Contract_End'] >= today)
        ].copy()
        
        with st.expander(f"🚨 계약 만료 임박 ({imminent_contracts.shape[0]} 건) - 30일 이내", expanded=False):
            if not imminent_contracts.empty:
                alert_found = True
                imminent_contracts['D-Day'] = (imminent_contracts['Contract_End'] - today).dt.days
                st.dataframe(imminent_contracts[['Name', 'Country', 'Contract_End', 'D-Day']].astype(str), use_container_width=True)
            else:
                st.info("해당 없음")

        overdue_activities = activities_df[
            (activities_df['Due_Date'] < today) &
            (activities_df['Status'] != 'Done')
        ].copy()

        with st.expander(f"🔥 활동 지연 ({overdue_activities.shape[0]} 건)", expanded=True): 
            if not overdue_activities.empty:
                alert_found = True
                overdue_activities = pd.merge(overdue_activities, master_df[['Kol_ID', 'Name']], on='Kol_ID', how='left')
                overdue_activities['Overdue (Days)'] = (today - overdue_activities['Due_Date']).dt.days
                st.error("아래 활동들이 지연되고 있습니다. Follow-up이 필요합니다.")
                st.dataframe(overdue_activities[['Name', 'Activity_Type', 'Due_Date', 'Status', 'Overdue (Days)']].astype(str), use_container_width=True)
            else:
                st.info("해당 없음")
        
        if not alert_found: st.success("🎉 모든 일정이 정상입니다!")
        st.divider()

        # ===================================
        # 4. 원본 데이터 (조건부 서식 적용)
        # ===================================
        st.header("4. 원본 데이터 (Raw Data - 시각화 적용)")
        today = datetime.now() 

        st.subheader("KOL 마스터")
        st.dataframe(
            master_df.style.apply(highlight_master_row, today=today, axis=1).format({'Contract_End': lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''}),
            use_container_width=True
        ) 
        
        st.subheader("모든 활동 내역")
        st.dataframe(
            activities_df.style.apply(highlight_activity_row, today=today, axis=1).format({'Due_Date': lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''}),
            use_container_width=True
        )

    # --- (KOL 상세 뷰 - 이전과 동일) ---
    else:
        try:
            selected_kol_id = master_df[master_df['Name'] == selected_name]['Kol_ID'].iloc[0]
            
            st.header(f"👨‍⚕️ {selected_name} 님 상세 정보")
            kol_details = master_df[master_df['Kol_ID'] == selected_kol_id]
            st.dataframe(kol_details.astype(str), use_container_width=True) 
            
            st.divider()
            st.header(f"📝 {selected_name} 님 활동 내역")
            kol_activities = activities_df[activities_df['Kol_ID'] == selected_kol_id]
            
            if not kol_activities.empty:
                col_detail1, col_detail2 = st.columns(2)
                
                # 상세 KPI 계산
                total = kol_activities.shape[0]
                done = kol_activities[kol_activities['Status'] == 'Done'].shape[0]
                completion_rate = (done / total) * 100 if total > 0 else 0
                
                kol_budget = kol_details['Budget (USD)'].iloc[0]
                kol_spent = kol_details['Spent (USD)'].iloc[0]
                kol_utilization = (kol_spent / kol_budget) * 100 if kol_budget > 0 else 0

                with col_detail1:
                    st.metric(label="배정된 총 활동 수", value=total)
                    st.metric(label="활동 완료율", value=f"{completion_rate:.1f}%")
                    st.metric(label="배정된 예산", value=f"${kol_budget:,.0f}")
                    st.metric(label="예산 활용률", value=f"{kol_utilization:.1f}%")

                with col_detail2:
                    if 'Status' in kol_activities.columns:
                        st.subheader("활동 상태 요약")
                        kol_status_counts = kol_activities['Status'].value_counts().reset_index()
                        kol_status_counts.columns = ['Status', 'Count']
                        
                        chart = alt.Chart(kol_status_counts).mark_bar(height=15).encode(
                            x=alt.X('Count', title='건수'),
                            y=alt.Y('Status', title='상태', sort='-x'),
                            tooltip=['Status', 'Count']
                        ).interactive()
                        st.altair_chart(chart, use_container_width=True)
                
                st.divider()
                
                st.subheader("활동 상세 목록 (Raw Data)")
                # --- 상세 뷰 로데이터 조건부 서식 적용 ---
                st.dataframe(
                    kol_activities.style.apply(highlight_activity_row, today=datetime.now(), axis=1).format({'Due_Date': lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''}),
                    column_config={
                        "File_Link": None, 
                        "자료 열람": st.column_config.LinkColumn(
                            "자료 열람 (링크)",
                            display_text="🔗 링크 열기"
                        )
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("이 KOL에 배정된 활동 내역이 없습니다.")
        except IndexError:
            st.error(f"'{selected_name}' 님의 'Kol_ID'를 'KOL_Master' 시트에서 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"데이터 표시 중 에러: {e}")