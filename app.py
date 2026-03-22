import streamlit as st
from supabase import create_client, Client
import pandas as pd

# 1. 수파베이스 연결
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="스벅 아아 소유효과 실험", layout="centered")

# 2. 현재 실험 세션 상태 가져오기 (실시간 반영을 위해 매번 쿼리)
def get_session():
    return supabase.table('experiment_sessions').select("*").limit(1).execute().data[0]

session = get_session()
curr_round = session['current_round']
status = session['status'] # 'waiting', 'trading', 'result'

st.title("🥤 행동재무학 실험: 스벅 아아 소유효과")

# 3. 학생 로그인
if 'user_name' not in st.session_state:
    with st.form("login"):
        name = st.text_input("이름을 입력하세요 (출석부 이름)")
        submit = st.form_submit_button("실험 입장")
        if submit and name:
            st.session_state.user_name = name
            st.rerun()
    st.stop()

user_name = st.session_state.user_name

# 4. 내 역할 및 배지 소유 정보 가져오기
user_query = supabase.table('students').select("*").eq('name', user_name).execute()
if not user_query.data:
    st.error("등록되지 않은 학생입니다. 교수님께 문의하세요.")
    st.stop()

user_data = user_query.data[0]

# --- 4라운드 스왑 로직 적용 ---
# 1~3라운드는 DB에 저장된 원래 역할 사용, 4라운드는 반전
if curr_round == 4:
    display_role = "buyer" if user_data['role'] == "seller" else "seller"
    display_has_badge = not user_data['has_badge']
else:
    display_role = user_data['role']
    display_has_badge = user_data['has_badge']

# --- UI 레이아웃 ---
st.info(f"📍 현재 [ 제 {curr_round} 라운드 ] 진행 중입니다.")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("나의 자산")
    if display_has_badge:
        # 배지 이미지는 아까 만드신 것을 URL로 넣으시면 됩니다.
        st.image("https://your-image-url.com/starbucks_badge.png", width=180)
        st.success("소유 중: 스벅 아아")
    else:
        st.metric(label="보유 가상 현금", value="10,000원")
        st.write("아직 배지가 없습니다.")

with col2:
    st.subheader("거래 입력")
    if status == 'waiting':
        st.warning("교수님이 라운드를 시작할 때까지 기다려주세요.")
    
    elif status == 'trading':
        if display_role == 'seller':
            st.write("이 배지를 팔기 위한 **최소 판매가(WTA)**를 입력하세요.")
            price = st.number_input("금액 (원)", min_value=0, step=100, key="wta")
        else:
            st.write("이 배지를 사기 위한 **최대 구매가(WTP)**를 입력하세요.")
            price = st.number_input("금액 (원)", min_value=0, max_value=10000, step=100, key="wtp")
        
        if st.button("제출하기"):
            supabase.table('students').update({"bid_price": price}).eq('name', user_name).execute()
            st.success("제출되었습니다! 결과 발표를 기다리세요.")

# --- 결과 발표 (거래 건수 포함) ---
if status == 'result':
    st.divider()
    st.subheader("📊 라운드 결과")
    
    # 해당 라운드의 거래 성공 건수 계산 (서버에서 가져온다고 가정)
    trade_count = supabase.table('trades').select("*", count='exact').eq('round_num', curr_round).execute().count
    
    c1, c2 = st.columns(2)
    c1.metric("이론적 예상 거래", "10건")
    c2.metric("실제 성사 거래", f"{trade_count}건")
    
    if trade_count < 7:
        st.error("📢 거래 건수가 예상보다 적습니다! '소유효과'가 강력하게 작용하고 있네요.")
    else:
        st.success("📢 시장이 비교적 활발하게 작동했습니다.")

# --- 교수님 전용 관리자 사이드바 ---
st.sidebar.divider()
admin_password = st.sidebar.text_input("관리자 비밀번호", type="password")

if admin_password == "3383": # 교수님만의 비밀번호로 변경하세요
    st.sidebar.subheader("👨‍🏫 실험 제어판")
    
    # 1. 라운드 조절
    new_round = st.sidebar.number_input("라운드 설정", min_value=1, max_value=4, value=curr_round)
    if new_round != curr_round:
        supabase.table('experiment_sessions').update({"current_round": new_round}).eq('id', session['id']).execute()
        st.sidebar.success(f"{new_round}라운드로 변경됨")

    # 2. 상태 조절
    new_status = st.sidebar.selectbox("실험 상태 변경", ["waiting", "trading", "result"], index=["waiting", "trading", "result"].index(status))
    if st.sidebar.button("상태 업데이트"):
        supabase.table('experiment_sessions').update({"status": new_status}).eq('id', session['id']).execute()
        # 상태가 trading으로 갈 때 학생들 가격 초기화
        if new_status == 'trading':
            supabase.table('students').update({"bid_price": 0}).neq('name', '').execute()
        st.rerun()

    # 3. 거래 매칭 버튼 (핵심!)
    if st.sidebar.button("💡 거래 매칭 실행 (결과 산출)"):
        # 학생 데이터 가져오기
        all_students = supabase.table('students').select("*").execute().data
        
        # 4라운드라면 스왑된 역할로 계산
        sellers = []
        buyers = []
        for s in all_students:
            actual_role = s['role']
            if curr_round == 4:
                actual_role = "buyer" if s['role'] == "seller" else "seller"
            
            if actual_role == "seller" and s['bid_price'] > 0:
                sellers.append(s)
            elif actual_role == "buyer" and s['bid_price'] > 0:
                buyers.append(s)

        # 가격순 정렬 (판매자는 낮은순, 구매자는 높은순)
        sellers.sort(key=lambda x: x['bid_price'])
        buyers.sort(key=lambda x: x['bid_price'], reverse=True)

        # 매칭 로직: 구매자 희망가 >= 판매자 희망가 인 경우 거래 성사
        trade_count = 0
        for s_idx in range(min(len(sellers), len(buyers))):
            if buyers[s_idx]['bid_price'] >= sellers[s_idx]['bid_price']:
                trade_count += 1
                # 거래 로그 기록
                supabase.table('trades').insert({
                    "round_num": curr_round,
                    "price": sellers[s_idx]['bid_price'],
                    "seller_name": sellers[s_idx]['name'],
                    "buyer_name": buyers[s_idx]['name']
                }).execute()
        
        # 상태를 결과 발표(result)로 변경
        supabase.table('experiment_sessions').update({"status": "result"}).eq('id', session['id']).execute()
        st.sidebar.success(f"{trade_count}건의 거래가 성사되었습니다!")
        st.rerun()