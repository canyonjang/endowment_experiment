import streamlit as st
from supabase import create_client, Client
import pandas as pd

# 1. 수파베이스 연결 설정
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="스벅 아아 소유효과 실험", layout="centered")

# --- [개선] URL 파라미터 기반 세션 유지 ---
# 새로고침 시 세션이 날아가는 것을 방지하기 위해 주소창의 name을 읽어옵니다.
if "user_name" not in st.session_state:
    name_from_url = st.query_params.get("name")
    if name_from_url:
        st.session_state.user_name = name_from_url

# 2. 현재 실험 세션 상태 가져오기 함수
def get_session():
    # 최신 세션 정보를 가져옵니다.
    return supabase.table('experiment_sessions').select("*").order('id', desc=True).limit(1).execute().data[0]

session = get_session()
curr_round = session['current_round']
status = session['status'] # waiting, trading, result

# --- 관리자 여부 확인 (?admin=true) ---
is_admin = st.query_params.get("admin") == "true"

if is_admin:
    # ==========================================
    # 👨‍🏫 교수님 전용 관리자 화면
    # ==========================================
    st.title("👨‍🏫 실험 관리자 제어판")
    st.write(f"현재 상태: **{status.upper()}** | 현재 라운드: **{curr_round}**")
    
    admin_password = st.sidebar.text_input("관리자 비밀번호", type="password")

    if admin_password == "3383":
        st.sidebar.subheader("실험 컨트롤러")
        
        # 라운드 조절
        new_round = st.sidebar.number_input("라운드 설정", min_value=1, max_value=4, value=curr_round)
        if new_round != curr_round:
            supabase.table('experiment_sessions').update({"current_round": new_round}).eq('id', session['id']).execute()
            st.sidebar.success(f"{new_round}라운드로 변경됨")
            st.rerun()

        # 상태 조절
        new_status = st.sidebar.selectbox("실험 상태 변경", ["waiting", "trading", "result"], index=["waiting", "trading", "result"].index(status))
        if st.sidebar.button("상태 업데이트 및 방송"):
            supabase.table('experiment_sessions').update({"status": new_status}).eq('id', session['id']).execute()
            if new_status == 'trading':
                # 새 라운드 시작 시 모든 학생의 가격 초기화
                supabase.table('students').update({"bid_price": 0}).neq('name', '').execute()
            st.rerun()

        # 거래 매칭 버튼
        st.divider()
        st.subheader("💡 거래 매칭 실행")
        if st.button("실시간 거래 성사 (매칭 실행)"):
            all_students = supabase.table('students').select("*").execute().data
            
            sellers = []
            buyers = []
            for s in all_students:
                # 4라운드 반전 로직 반영
                actual_role = s['role']
                if curr_round == 4:
                    actual_role = "buyer" if s['role'] == "seller" else "seller"
                
                if actual_role == "seller" and s['bid_price'] > 0:
                    sellers.append(s)
                elif actual_role == "buyer" and s['bid_price'] > 0:
                    buyers.append(s)

            sellers.sort(key=lambda x: x['bid_price'])
            buyers.sort(key=lambda x: x['bid_price'], reverse=True)

            trade_count = 0
            for s_idx in range(min(len(sellers), len(buyers))):
                if buyers[s_idx]['bid_price'] >= sellers[s_idx]['bid_price']:
                    trade_count += 1
                    supabase.table('trades').insert({
                        "round_num": curr_round,
                        "price": sellers[s_idx]['bid_price'],
                        "seller_name": sellers[s_idx]['name'],
                        "buyer_name": buyers[s_idx]['name']
                    }).execute()
            
            supabase.table('experiment_sessions').update({"status": "result"}).eq('id', session['id']).execute()
            st.success(f"매칭 완료! 총 {trade_count}건 거래 성사.")
            st.rerun()
            
        # [개선] 수동 입력 현황 확인 (통신량 절약)
        st.divider()
        st.subheader("📊 학생 입력 현황 모니터링")
        if st.button("🔄 입력 현황 새로고침"):
            df = pd.DataFrame(supabase.table('students').select("name, role, bid_price").execute().data)
            submitted_count = len(df[df['bid_price'] > 0])
            st.write(f"현재 제출 인원: {submitted_count}명 / 39명")
            st.dataframe(df)

    else:
        st.warning("사이드바에 관리자 비밀번호를 입력해주세요.")
    st.stop()

# ==========================================
# 🎓 학생용 실험 화면
# ==========================================
st.title("🥤 행동재무학 실험: 스벅 아아 소유효과")

# 로그인 처리
if 'user_name' not in st.session_state:
    with st.form("login"):
        name = st.text_input("이름을 입력하세요 (출석부 이름)")
        submit = st.form_submit_button("실험 입장")
        if submit and name:
            st.session_state.user_name = name
            st.query_params["name"] = name # URL에 이름 저장
            st.rerun()
    st.stop()

user_name = st.session_state.user_name

# [개선] 수동 데이터 갱신 버튼
if st.button("🔄 화면 새로고침 (교수님 지시 시 클릭)"):
    st.rerun()

# 내 정보 및 라운드 정보 가져오기
user_data = supabase.table('students').select("*").eq('name', user_name).execute().data[0]

# --- 4라운드 스왑 로직 ---
if curr_round == 4:
    display_role = "buyer" if user_data['role'] == "seller" else "seller"
    display_has_badge = not user_data['has_badge']
else:
    display_role = user_data['role']
    display_has_badge = user_data['has_badge']

st.info(f"📍 {user_name}님, 현재 [ 제 {curr_round} 라운드 ] 진행 중")

# --- UI 레이아웃 ---
col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("나의 자산")
    if display_has_badge:
        st.image("starbucks_badge.png", width=180) # 파일명 확인 필수
        st.success("보유 중: 스벅 아아 배지")
    else:
        st.metric(label="보유 가상 현금", value="10,000원")
        st.write("배지가 없습니다.")

with col2:
    st.subheader("거래 입력")
    if status == 'waiting':
        st.warning("대기 중입니다. 교수님의 지시를 기다리세요.")
    
    elif status == 'trading':
        if display_role == 'seller':
            st.write("**최소 판매 희망가(WTA)**")
            price = st.number_input("받고 싶은 금액 (원)", min_value=0, step=100, key="wta")
        else:
            st.write("**최대 구매 희망가(WTP)**")
            price = st.number_input("지불할 용의가 있는 금액 (원)", min_value=0, max_value=10000, step=100, key="wtp")
        
        if st.button("데이터 제출"):
            supabase.table('students').update({"bid_price": price}).eq('name', user_name).execute()
            st.balloons()
            st.success("제출 완료! 결과 발표를 기다리세요.")

# ==========================================
# 📊 [개선] 거래 결과 시각적 피드백
# ==========================================
if status == 'result':
    st.divider()
    st.subheader("📢 라운드 거래 결과")
    
    # 내 거래 성사 여부 확인
    my_trade = supabase.table('trades').select("*").eq('round_num', curr_round).or_(f"seller_name.eq.{user_name},buyer_name.eq.{user_name}").execute().data
    
    if my_trade:
        # 거래 성공 시
        trade_info = my_trade[0]
        st.balloons()
        st.success(f"### 🎉 거래 성공!")
        st.write(f"체결 가격: **{trade_info['price']:,}원**")
        if user_name == trade_info['seller_name']:
            st.write(f"🤝 구매자 **{trade_info['buyer_name']}**님에게 배지를 전달했습니다.")
        else:
            st.write(f"🤝 판매자 **{trade_info['seller_name']}**님으로부터 배지를 획득했습니다.")
    else:
        # 거래 실패 시
        if user_data['bid_price'] > 0:
            st.error("### 📉 거래 실패")
            st.write("상대방과 가격 합의가 이루어지지 않아 거래가 성사되지 않았습니다.")
        else:
            st.info("입력된 데이터가 없어 이번 라운드 거래에 참여하지 않았습니다.")

    # 전체 시장 통계
    st.divider()
    trade_count = supabase.table('trades').select("*", count='exact').eq('round_num', curr_round).execute().count
    c1, c2 = st.columns(2)
    c1.metric("이론적 예상 거래", "10건")
    c2.metric("실제 성사 거래", f"{trade_count}건")
