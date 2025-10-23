import streamlit as st
import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe
import os # 파일 경로를 위한 모듈
import altair as alt # 차트 라이브러리
from datetime import datetime, timedelta # 💡 알림 계산을 위해 추가

# -----------------------------------------------------------------
# 1. Google Sheets 인증 및 데이터 로드 (이전과 동일)
# -----------------------------------------------------------------

@st.cache_data(ttl=60) # 60초마다 데이터를 새로고침 (캐시)
def load_data_from_gsheet():
    
    SPREADSHEET_NAME = "KOL 관리 시트" 
    WORKSHEET1_NAME = "KOL_Master"
    WORKSHEET2_NAME = "Activities"
    
    try:
        # --- (2) 인증 (배포/로컬 하이브리드) ---
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

        # --- (3) Google Sheets 파일 열기 ---
        sh = gc.open(SPREADSHEET_NAME)

        # --- (4) 탭 로드 ---
        master_ws = sh.worksheet(WORKSHEET1_NAME)
        master_df = get_as_dataframe(master_ws).dropna(how='all') # astype(str)은 날짜 계산을 위해 제거
        
        activities_ws = sh.worksheet(WORKSHEET2_NAME)
        activities_df = get_as_dataframe(activities_ws).dropna(how='all')
        
        # --- (5) 💡 날짜/숫자 데이터 타입 변환 ---
        # (알림 계산 및 차트를 위해 원본 데이터 타입을 변환)
        master_df['Contract_End'] = pd.to_datetime(master_df['Contract_End'], errors='coerce')
        activities_df['Due_Date'] = pd.to_datetime(activities_df['Due_Date'], errors='coerce')
        
        st.success("🎉 데이터 로드 완료!")
        return master_df, activities_df

    # --- 에러 핸들링 ---
    except Exception as e:
        st.error(f"데이터 로드 중 에러 발생: {e}")
        return None, None

# -----------------------------------------------------------------
# 2. Streamlit 대시보드 UI 그리기
# -----------------------------------------------------------------

st.set_page_config(page_title="KOL 대시보드 MVP", layout="wide")
st.title("📊 KOL 활동 관리 대시보드 (MVP)")

master_df, activities_df = load_data_from_gsheet()

st.sidebar.subheader("KOL 상세 조회 필터")
if master_df is not None:
    kol_names = master_df['Name'].tolist()
    selected_name = st.sidebar.selectbox("KOL 이름을 선택하세요:", ["전체"] + kol_names)
else:
    selected_name = st.sidebar.selectbox("KOL 이름을 선택하세요:", ["전체"])

# --- 데이터 로드 성공 시 메인 화면 구성 ---
if master_df is not None and activities_df is not None:

    if selected_name == "전체":
        
        st.header("KPI 요약")
        col1, col2, col3, col4 = st.columns(4)

        total_kols = master_df.shape[0]
        total_activities = activities_df.shape[0]
        done_activities = activities_df[activities_df['Status'] == 'Done'].shape[0]
        planned_activities = activities_df[activities_df['Status'] == 'Planned'].shape[0]

        with col1: st.metric(label="총 KOL 인원", value=total_kols)
        with col2: st.metric(label="총 활동 수", value=total_activities)
        with col3: st.metric(label="완료된 활동", value=done_activities)
        with col4: st.metric(label="계획된 활동", value=planned_activities)

        st.divider()

        # --- 💡💡 [알림 기능 섹션] 💡💡 ---
        st.header("🔔 경고 및 알림 (Alerts)")
        
        today = datetime.now()
        alert_found = False

        # 조건 1: 계약 만료 임박 (30일)
        contract_alert_date = today + timedelta(days=30)
        imminent_contracts = master_df[
            (master_df['Contract_End'] <= contract_alert_date) &
            (master_df['Contract_End'] >= today)
        ].copy()
        
        with st.expander(f"🚨 계약 만료 임박 ({imminent_contracts.shape[0]} 건) - 30일 이내", expanded=False):
            if not imminent_contracts.empty:
                alert_found = True
                imminent_contracts['D-Day'] = (imminent_contracts['Contract_End'] - today).dt.days
                st.dataframe(imminent_contracts[['Name', 'Country', 'Contract_End', 'D-Day']], use_container_width=True)
            else:
                st.info("해당 없음")

        # 조건 2: 활동 마감 임박 (7일, 'Planned' 상태)
        activity_alert_date = today + timedelta(days=7)
        imminent_activities = activities_df[
            (activities_df['Due_Date'] <= activity_alert_date) &
            (activities_df['Due_Date'] >= today) &
            (activities_df['Status'] == 'Planned')
        ].copy()
        
        with st.expander(f"⚠️ 활동 마감 임박 ({imminent_activities.shape[0]} 건) - 7일 이내", expanded=False):
            if not imminent_activities.empty:
                alert_found = True
                imminent_activities = pd.merge(imminent_activities, master_df[['Kol_ID', 'Name']], on='Kol_ID', how='left')
                imminent_activities['D-Day'] = (imminent_activities['Due_Date'] - today).dt.days
                st.dataframe(imminent_activities[['Name', 'Activity_Type', 'Due_Date', 'D-Day']], use_container_width=True)
            else:
                st.info("해당 없음")

        # 조건 3: 활동 지연 (마감일 지남, 'Done' 아님)
        overdue_activities = activities_df[
            (activities_df['Due_Date'] < today) &
            (activities_df['Status'] != 'Done')
        ].copy()

        with st.expander(f"🔥 활동 지연 ({overdue_activities.shape[0]} 건)", expanded=True): # 지연 건은 기본으로 펼침
            if not overdue_activities.empty:
                alert_found = True
                overdue_activities = pd.merge(overdue_activities, master_df[['Kol_ID', 'Name']], on='Kol_ID', how='left')
                overdue_activities['Overdue (Days)'] = (today - overdue_activities['Due_Date']).dt.days
                st.error("아래 활동들이 지연되고 있습니다. Follow-up이 필요합니다.")
                st.dataframe(overdue_activities[['Name', 'Activity_Type', 'Due_Date', 'Status', 'Overdue (Days)']], use_container_width=True)
            else:
                st.info("해당 없음")
        
        if not alert_found:
            st.success("🎉 모든 일정이 정상입니다!")
            
        st.divider()
        # --- 💡💡 [알림 기능 끝] 💡💡 ---


        st.header("차트 현황")
        col_chart1, col_chart2 = st.columns(2) 

        with col_chart1:
            if 'Country' in master_df.columns:
                st.subheader("국가별 KOL 인원수")
                country_counts = master_df['Country'].value_counts().reset_index()
                country_counts.columns = ['Country', 'Count']
                
                chart = alt.Chart(country_counts).mark_bar(height=15).encode(
                    x=alt.X('Count', title='인원수'),
                    y=alt.Y('Country', title='국가', sort='-x'),
                    tooltip=['Country', 'Count']
                ).interactive()
                st.altair_chart(chart, use_container_width=True)
        
        with col_chart2:
            if 'Status' in activities_df.columns:
                st.subheader("전체 활동 상태별 현황")
                status_counts = activities_df['Status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']

                chart = alt.Chart(status_counts).mark_bar(height=15).encode(
                    x=alt.X('Count', title='건수'),
                    y=alt.Y('Status', title='상태', sort='-x'),
                    tooltip=['Status', 'Count']
                ).interactive()
                st.altair_chart(chart, use_container_width=True)

        st.divider()

        st.header("원본 데이터 (Raw Data)")
        st.subheader("KOL 마스터")
        st.dataframe(master_df.astype(str), use_container_width=True) # 표시는 문자로
        st.subheader("모든 활동 내역")
        st.dataframe(activities_df.astype(str), use_container_width=True) # 표시는 문자로

    # --- (KOL 상세 뷰 - 수정 없음) ---
    else:
        try:
            selected_kol_id = master_df[master_df['Name'] == selected_name]['Kol_ID'].iloc[0]
            
            st.header(f"👨‍⚕️ {selected_name} 님 상세 정보")
            kol_details = master_df[master_df['Kol_ID'] == selected_kol_id]
            st.dataframe(kol_details.astype(str), use_container_width=True) # 표시는 문자로
            
            st.divider()
            st.header(f"📝 {selected_name} 님 활동 내역")
            kol_activities = activities_df[activities_df['Kol_ID'] == selected_kol_id]
            
            if not kol_activities.empty:
                col_detail1, col_detail2 = st.columns(2)
                
                with col_detail1:
                    st.metric(label="배정된 총 활동 수", value=kol_activities.shape[0])
                    st.metric(label="완료한 활동 수", value=kol_activities[kol_activities['Status'] == 'Done'].shape[0])

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
                kol_activities_display = kol_activities.copy()
                kol_activities_display['자료 열람'] = kol_activities_display['File_Link'].apply(
                    lambda url: f"[링크 열기]({url})" if url and url.startswith('http') else "링크 없음"
                )
                
                st.dataframe(
                    kol_activities_display.astype(str), # 표시는 문자로
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