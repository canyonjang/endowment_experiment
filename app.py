import streamlit as st
from supabase import create_client, Client
import pandas as pd

# 1. 수파베이스 연결
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="행동재무학 실험 대시보드", layout="centered")

# URL 파라미터 기반 세션 유지
if "user_name" not in st.session_state:
    name_from_url = st.query_params.get("name")
    if name_from_url:
        st.session_state.user_name = name_from_url

# 현재 실험 세션 상태 가져오기
def get_session():
    return supabase.table('experiment_sessions').select("*").order('id', desc=True).limit(1).execute().data[0]

session = get_session()
curr_round = session['current_round']
status = session['status']

# 관리자 여부 확인 (?admin=true)
is_admin = st.query_params.get("admin") == "true"

if is_admin:
    # ==========================================
    # 👨‍🏫 교수님 전용 관리자 & 스크린용 화면
    # ==========================================
    st.title("📊 행동재무학 실험 실시간 대시보드")
    st.write(f"**상태:** {status.upper()} | **현재 진행:** 제 {curr_round} 라운드")
    
    admin_password = st.sidebar.text_input("관리자 비밀번호", type="password")

    if admin_password == "3383":
        st.sidebar.subheader("🕹️ 실험 제어")
        
        # 라운드 및 상태 조절
        new_round = st.sidebar.number_input("라운드 설정", min_value=1, max_value=4, value=curr_round)
        if new_round != curr_round:
            supabase.table('experiment_sessions').update({"current_round": new_round}).eq('id', session['id']).execute()
            st.rerun()

        new_status = st.sidebar.selectbox("상태 변경", ["waiting", "trading", "result"], index=["waiting", "trading", "result"].index(status))
        if st.sidebar.button("상태 업데이트 및 방송"):
            supabase.table('experiment_sessions').update({"status": new_status}).eq('id', session['id']).execute()
            if new_status == 'trading':
                supabase.table('students').update({"bid_price": 0}).neq('name', '').execute()
            st.rerun()

        if st.sidebar.button("💡 거래 매칭 실행"):
            # (매칭 로직은 이전과 동일)
            all_students = supabase.table('students').select("*").execute().data
            sellers, buyers = [], []
            for s in all_students:
                role = s['role']
                if curr_round == 4: role = "buyer" if s['role'] == "seller" else "seller"
                if role == "seller" and s['bid_price'] > 0: sellers.append(s)
                elif role == "buyer" and s['bid_price'] > 0: buyers.append(s)
            
            sellers.sort(key=lambda x: x['bid_price'])
            buyers.sort(key=lambda x: x['bid_price'], reverse=True)
            
            for s_idx in range(min(len(sellers), len(buyers))):
                if buyers[s_idx]['bid_price'] >= sellers[s_idx]['bid_price']:
                    supabase.table('trades').insert({"round_num": curr_round, "price": sellers[s_idx]['bid_price'], "seller_name": sellers[s_idx]['name'], "buyer_name": buyers[s_idx]['name']}).execute()
            
            supabase.table('experiment_sessions').update({"status": "result"}).eq('id', session['id']).execute()
            st.rerun()

        # ------------------------------------------
        # 📈 [추가] 교수님 화면 전용 실시간 통계 (스크린용)
        # ------------------------------------------
        st.divider()
        st.subheader("🏁 라운드별 거래 요약")
        
        # 전체 거래 데이터 가져오기
        all_trades = pd.DataFrame(supabase.table('trades').select("*").execute().data)
        
        if not all_trades.empty:
            summary = all_trades.groupby('round_num').size().reset_index(name='거래 건수')
            summary['이론적 예상'] = 10  # 20명 판매자 기준
            
            # 메트릭으로 시각화
            cols = st.columns(4)
            for i in range(1, 5):
                count = summary[summary['round_num'] == i]['거래 건수'].values[0] if i in summary['round_num'].values else 0
                cols[i-1].metric(f"{i}라운드", f"{count}건", f"{count-10} vs 이론")

            # 차트 표시
            st.bar_chart(summary.set_index('round_num')[['거래 건수', '이론적 예상']])
        else:
            st.info("아직 성사된 거래가 없습니다.")

        # ------------------------------------------
        # 🎊 [추가] 4라운드 종료 후 최종 리포트
        # ------------------------------------------
        if curr_round == 4 and status == 'result':
            st.divider()
            st.header("🎊 실험 최종 결과 분석")
            st.balloons()
            
            # 평균 체결 가격 계산
            avg_prices = all_trades.groupby('round_num')['price'].mean().reset_index(name='평균 가격')
            st.subheader("💰 라운드별 평균 체결 가격 변화")
            st.line_chart(avg_prices.set_index('round_num'))
            
            st.write("💡 **교수님 가이드:** 4라운드(역할 반전)에서 거래 건수가 늘어났나요? 아니면 평균 가격이 급격히 변했나요? 소유 효과가 사라지거나 강화되는 지점을 학생들과 논의해 보세요.")

        # 입력 현황 모니터링 (수동)
        st.divider()
        if st.button("🔄 학생 입력 현황 새로고침"):
            df = pd.DataFrame(supabase.table('students').select("name, role, bid_price").execute().data)
            st.write(f"제출 인원: {len(df[df['bid_price'] > 0])} / 39명")
            st.dataframe(df)

    else:
        st.warning("비밀번호를 입력하세요.")
    st.stop()

# ==========================================
# 🎓 학생용 실험 화면 (시장 통계 제거)
# ==========================================
st.title("🥤 행동재무학 실험: 스벅 아아 소유효과")

if 'user_name' not in st.session_state:
    with st.form("login"):
        name = st.text_input("이름을 입력하세요")
        if st.form_submit_button("실험 입장") and name:
            st.session_state.user_name = name
            st.query_params["name"] = name
            st.rerun()
    st.stop()

user_name = st.session_state.user_name

if st.button("🔄 화면 새로고침"):
    st.rerun()

user_data = supabase.table('students').select("*").eq('name', user_name).execute().data[0]

# 역할 계산
if curr_round == 4:
    display_role, display_has_badge = ("buyer", not user_data['has_badge']) if user_data['role'] == "seller" else ("seller", not user_data['has_badge'])
else:
    display_role, display_has_badge = user_data['role'], user_data['has_badge']

# 자산 연출 (result 상태일 때)
final_has_badge, my_trade = display_has_badge, None
if status == 'result':
    trade_q = supabase.table('trades').select("*").eq('round_num', curr_round).or_(f"seller_name.eq.{user_name},buyer_name.eq.{user_name}").execute().data
    if trade_q:
        my_trade = trade_q[0]
        final_has_badge = False if user_name == my_trade['seller_name'] else True

st.info(f"📍 {user_name}님, [ 제 {curr_round} 라운드 ] 진행 중")

col1, col2 = st.columns([1, 1.5])
with col1:
    st.subheader("나의 자산")
    if final_has_badge:
        st.image("starbucks_badge.png", width=180)
        st.success("보유 중: 스벅 아아")
    else:
        st.metric(label="보유 현금", value="10,000원")

with col2:
    st.subheader("거래 입력")
    if status == 'waiting': st.warning("대기 중...")
    elif status == 'trading':
        label = "최소 판매가(WTA)" if display_role == 'seller' else "최대 구매가(WTP)"
        price = st.number_input(label, min_value=0, max_value=10000, step=100)
        if st.button("데이터 제출"):
            supabase.table('students').update({"bid_price": price}).eq('name', user_name).execute()
            st.success("제출 완료!")

if status == 'result':
    st.divider()
    if my_trade:
        st.success(f"### 🎉 거래 성공! (체결가: {my_trade['price']:,}원)")
    elif user_data['bid_price'] > 0:
        st.error("### 📉 거래 실패 (가격 불일치)")
    # 학생 화면에서 전체 거래 건수 통계는 제거되었습니다.
