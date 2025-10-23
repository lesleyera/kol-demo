import streamlit as st
import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe
import os # 파일 경로를 위한 모듈
import altair as alt # 차트 라이브러리

# -----------------------------------------------------------------
# 1. Google Sheets 인증 및 데이터 로드 (배포/로컬 겸용 수정)
# -----------------------------------------------------------------

@st.cache_data(ttl=60) # 60초마다 데이터를 새로고침 (캐시)
def load_data_from_gsheet():
    
    # --- (1) 시트 파일/탭 이름 설정 ---
    SPREADSHEET_NAME = "KOL 관리 시트" 
    WORKSHEET1_NAME = "KOL_Master"
    WORKSHEET2_NAME = "Activities"
    
    try:
        # --- (2) 인증 (배포/로컬 하이브리드) ---
        gc = None # gc 변수 초기화
        
        # --- (2-A) 로컬 파일 먼저 확인 ---
        script_dir = os.path.dirname(os.path.abspath(__file__))
        creds_path = os.path.join(script_dir, 'google_credentials.json')
        
        if os.path.exists(creds_path):
            # Local PC (로컬 환경)
            gc = gspread.service_account(filename=creds_path)
            st.info("✅ 1/4: Local 'google_credentials.json' 파일로 인증 성공")
        
        # --- (2-B) 로컬 파일이 없으면, Streamlit Cloud Secrets 확인 ---
        elif 'gcp_service_account' in st.secrets:
            # Streamlit Cloud (배포 환경)
            creds_dict = st.secrets['gcp_service_account']
            gc = gspread.service_account_from_dict(creds_dict)
            st.info("✅ 1/4: Streamlit Cloud Secret으로 인증 성공")
            
        else:
            # 둘 다 없으면 에러
            st.error("인증 실패: 'google_credentials.json' 파일을 찾을 수 없습니다.")
            st.error("배포(Deploy)하는 경우, Streamlit Cloud 'Secrets'에 'gcp_service_account'를 설정했는지 확인하세요.")
            return None, None

        # --- (3) Google Sheets 파일 열기 ---
        sh = gc.open(SPREADSHEET_NAME)
        st.info(f"✅ 2/4: Google Sheets 파일 ('{SPREADSHEET_NAME}') 열기 성공")

        # --- (4) 'KOL_Master' 탭 로드 ---
        master_ws = sh.worksheet(WORKSHEET1_NAME)
        master_df = get_as_dataframe(master_ws).dropna(how='all').astype(str)
        st.info(f"✅ 3/4: '{WORKSHEET1_NAME}' 탭 로드 성공")

        # --- (5) 'Activities' 탭 로드 ---
        activities_ws = sh.worksheet(WORKSHEET2_NAME)
        activities_df = get_as_dataframe(activities_ws).dropna(how='all').astype(str)
        st.info(f"✅ 4/4: '{WORKSHEET2_NAME}' 탭 로드 성공")
        
        # 숫자형 데이터 변환
        master_df['Kol_ID'] = master_df['Kol_ID'].astype(str)
        activities_df['Kol_ID'] = activities_df['Kol_ID'].astype(str)
        
        st.success("🎉 데이터 로드 완료!")
        return master_df, activities_df

    # --- 에러 핸들링 (이전과 동일) ---
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"파일 찾기 실패: Google Sheets 파일 이름이 '{SPREADSHEET_NAME}'이 맞는지 확인하세요.")
        st.error("또는 Google Sheets [공유]에 'client_email'이 '편집자'로 추가되었는지 확인하세요.")
        return None, None
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"워크시트(탭) 찾기 실패: Google Sheets 파일 안에 '{e.message}'라는 이름의 탭이 없습니다.")
        st.error(f"실제 탭 이름이 '{WORKSHEET1_NAME}'와 '{WORKSHEET2_NAME}'이 맞는지 확인하세요.")
        return None, None
    except Exception as e:
        st.error(f"기타 에러 발생: {e}")
        return None, None

# -----------------------------------------------------------------
# 2. Streamlit 대시보드 UI 그리기 (수정 없음)
# -----------------------------------------------------------------

st.set_page_config(page_title="KOL 대시보드 MVP", layout="wide")

st.title("📊 KOL 활동 관리 대시보드 (MVP)")

# --- 데이터 로드 먼저 실행 ---
master_df, activities_df = load_data_from_gsheet()

# --- 사이드바 필터 (데이터 로드 후 한번만 그리기) ---
st.sidebar.subheader("KOL 상세 조회 필터")
if master_df is not None:
    kol_names = master_df['Name'].tolist()
    selected_name = st.sidebar.selectbox("KOL 이름을 선택하세요:", ["전체"] + kol_names)
else:
    selected_name = st.sidebar.selectbox("KOL 이름을 선택하세요:", ["전체"])
    # st.error("데이터 로드 실패. 사이드바가 비어있을 수 있습니다.") # 이 에러 메시지는 load_data_from_gsheet 함수에서 이미 보여줌


# --- 데이터 로드 성공 시 메인 화면 구성 ---
if master_df is not None and activities_df is not None:

    if selected_name == "전체":
        
        st.header("KPI 요약")
        col1, col2, col3, col4 = st.columns(4)

        total_kols = master_df.shape[0]
        total_activities = activities_df.shape[0]
        done_activities = activities_df[activities_df['Status'] == 'Done'].shape[0]
        planned_activities = activities_df[activities_df['Status'] == 'Planned'].shape[0]

        with col1:
            st.metric(label="총 KOL 인원", value=total_kols)
        with col2:
            st.metric(label="총 활동 수", value=total_activities)
        with col3:
            st.metric(label="완료된 활동", value=done_activities)
        with col4:
            st.metric(label="계획된 활동", value=planned_activities)

        st.divider()

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
        st.dataframe(master_df, use_container_width=True)
        st.subheader("모든 활동 내역")
        st.dataframe(activities_df, use_container_width=True)

    else:
        try:
            selected_kol_id = master_df[master_df['Name'] == selected_name]['Kol_ID'].iloc[0]
            
            st.header(f"👨‍⚕️ {selected_name} 님 상세 정보")
            kol_details = master_df[master_df['Kol_ID'] == selected_kol_id]
            st.dataframe(kol_details, use_container_width=True)
            
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
                    kol_activities_display,
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