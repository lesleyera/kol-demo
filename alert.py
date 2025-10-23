import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe
from datetime import datetime, timedelta

# --- 설정값 ---
SPREADSHEET_NAME = "KOL 관리 시트"
WORKSHEET1_NAME = "KOL_Master"
WORKSHEET2_NAME = "Activities"
CONTRACT_ALERT_DAYS = 30  # 계약 만료 30일 전
ACTIVITY_ALERT_DAYS = 7   # 활동 마감 7일 전

# --- 1. Google Sheets 인증 및 데이터 로드 ---
# (이 스크립트는 GitHub Actions에서 실행될 것이므로,
# app.py와 동일하게 'google_credentials.json' 파일을 찾아서 인증합니다)
try:
    gc = gspread.service_account(filename='google_credentials.json')
    sh = gc.open(SPREADSHEET_NAME)
    
    master_df = get_as_dataframe(sh.worksheet(WORKSHEET1_NAME)).dropna(how='all')
    activities_df = get_as_dataframe(sh.worksheet(WORKSHEET2_NAME)).dropna(how='all')
    
    print("✅ Google Sheets 데이터 로드 성공")

except Exception as e:
    print(f"❌ Google Sheets 연결 실패: {e}")
    exit(1) # 에러 발생 시 중단


# --- 2. 날짜 데이터 변환 ---
try:
    # 'YYYY-MM-DD' 형식을 datetime 객체로 변환
    master_df['Contract_End_DT'] = pd.to_datetime(master_df['Contract_End'], errors='coerce')
    activities_df['Due_Date_DT'] = pd.to_datetime(activities_df['Due_Date'], errors='coerce')
    
    # NaT (날짜 변환 실패)가 있는 행은 알림에서 제외
    master_df = master_df.dropna(subset=['Contract_End_DT'])
    activities_df = activities_df.dropna(subset=['Due_Date_DT'])

except Exception as e:
    print(f"❌ 날짜 변환 중 에러: {e}")
    print("KOL_Master의 'Contract_End' 또는 Activities의 'Due_Date' 컬럼 형식을 확인하세요.")
    exit(1)


# --- 3. 알림 조건 검색 ---
today = datetime.now()
print(f"\n--- {today.strftime('%Y-%m-%d')} 기준 알림 ---")

alert_found = False # 알림을 찾았는지 여부

# 조건 1: 계약 만료일이 30일 이내로 다가오는 KOL
print(f"\n🔔 [1] {CONTRACT_ALERT_DAYS}일 이내 계약 만료 건:")
contract_alert_date = today + timedelta(days=CONTRACT_ALERT_DAYS)

imminent_contracts = master_df[
    (master_df['Contract_End_DT'] <= contract_alert_date) &
    (master_df['Contract_End_DT'] >= today)
]

if not imminent_contracts.empty:
    alert_found = True
    for index, row in imminent_contracts.iterrows():
        d_day = (row['Contract_End_DT'] - today).days
        print(f"  - [D-{d_day}] {row['Name']} ({row['Country']}) - 계약 만료: {row['Contract_End']}")
else:
    print("  (해당 없음)")


# 조건 2: 마감일이 7일 이내로 다가오는 'Planned' 상태의 활동
print(f"\n🔔 [2] {ACTIVITY_ALERT_DAYS}일 이내 마감 활동 (Planned):")
activity_alert_date = today + timedelta(days=ACTIVITY_ALERT_DAYS)

imminent_activities = activities_df[
    (activities_df['Due_Date_DT'] <= activity_alert_date) &
    (activities_df['Due_Date_DT'] >= today) &
    (activities_df['Status'] == 'Planned')
]

if not imminent_activities.empty:
    alert_found = True
    # 가독성을 위해 master_df에서 이름(Name)을 찾아 합칩니다.
    imminent_activities = pd.merge(imminent_activities, master_df[['Kol_ID', 'Name']], on='Kol_ID', how='left')
    for index, row in imminent_activities.iterrows():
        d_day = (row['Due_Date_DT'] - today).days
        print(f"  - [D-{d_day}] {row['Name']} - 활동 마감: {row['Activity_Type']} ({row['Due_Date']})")
else:
    print("  (해당 없음)")


# 조건 3: 마감일이 지났지만 'Done'이 아닌 활동 (지연됨)
print(f"\n🔔 [3] 마감일이 지난 활동 (Delayed/Planned):")
overdue_activities = activities_df[
    (activities_df['Due_Date_DT'] < today) &
    (activities_df['Status'] != 'Done') # 'Done'이 아닌 모든 것
]

if not overdue_activities.empty:
    alert_found = True
    overdue_activities = pd.merge(overdue_activities, master_df[['Kol_ID', 'Name']], on='Kol_ID', how='left')
    for index, row in overdue_activities.iterrows():
        overdue_days = (today - row['Due_Date_DT']).days
        print(f"  - [D+{overdue_days}] {row['Name']} - 활동 지연: {row['Activity_Type']} (마감: {row['Due_Date']}, 상태: {row['Status']})")
else:
    print("  (해당 없음)")


print("\n--- 알림 검색 완료 ---")

if not alert_found:
    print("🎉 모든 일정이 정상입니다.")

# (추후 이 스크립트에 smtplib (이메일) 또는 requests (슬랙) 코드를 추가하여
# 이 print() 결과 대신 실제 알림을 발송하게 됩니다.)