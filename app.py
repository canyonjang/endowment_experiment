import streamlit as st
from supabase import create_client, Client
import pandas as pd

# 1. 수파베이스 연결 설정
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

        # 라운드별 거래 요약 (중앙 화면)
        st.divider()
        st.subheader("🏁 라운드별 거래 요약")
        all_trades = pd.DataFrame(supabase.table('trades').select("*").execute().data)
        
        if not all_trades.empty:
            summary = all_trades.groupby('round_num').size().reset_index(name='거래 건수')
            summary['이론적 예상'] = 10 
            cols = st.columns(4)
            for i in range(1, 5):
                count = summary[summary['round_num'] == i]['거래 건수'].values[0] if i in summary['round_num'].values else 0
                cols[i-1].metric(f"{i}라운드", f"{count}건")
            st.bar_chart(summary.set_index('round_num')[['거래 건수', '이론적 예상']])
        else:
            st.info("아직 성사된 거래가 없습니다.")

        # 4라운드 종료 후 최종 리포트
        if curr_round == 4 and status == 'result':
            st.divider()
            st.header("🎊 실험 최종 결과 분석")
            st.balloons()
            avg_prices = all_trades.groupby('round_num')['price'].mean().reset_index(name='평균 가격')
            st.subheader("💰 라운드별 평균 체결 가격 변화")
            st.line_chart(avg_prices.set_index('round_num'))
            st.write("💡 **교수님 가이드:** 역할이 반전된 4라운드에서 가격과 거래량이 어떻게 변했는지 학생들과 토론해 보세요.")

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
# 🎓 학생용 실험 화면 (시장 통계 제거 & 자산 정산 연출)
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

# --- [고도화] 결과 화면 자산 및 정산 금액 연출 로직 (UI 전용) ---
final_has_badge, my_trade = display_has_badge, None
display_cash = 10000 # 초기 기본 현금

if status == 'result':
    trade_q = supabase.table('trades').select("*").eq('round_num', curr_round).or_(f"seller_name.eq.{user_name},buyer_name.eq.{user_name}").execute().data
    if trade_q:
        my_trade = trade_q[0]
        # 내가 판매자였는데 성공했다면
        if user_name == my_trade['seller_name']:
            final_has_badge = False
            display_cash = 10000 + my_trade['price'] # 정산 금액 합산
        # 내가 구매자였는데 성공했다면
        else:
            final_has_badge = True
            display_cash = 10000 - my_trade['price'] # 정산 금액 차감

st.info(f"📍 {user_name}님, [ 제 {curr_round} 라운드 ] 진행 중")

col1, col2 = st.columns([1, 1.5])
with col1:
    st.subheader("나의 자산")
    if final_has_badge:
        st.image("starbucks_badge.png", width=180) # 파일명 확인 필수
        st.success("보유 중: 스벅 아아 배지")
    
    # [개선] 매도/매수 성공 여부와 상관없이 항상 정산된 현금을 보여줍니다.
    # 성공한 구매자에게는 배지와 줄어든 현금이, 성공한 판매자에게는 배지 없이 늘어난 현금이 나타납니다.
    st.metric(label="보유 현금", value=f"{display_cash:,}원")

with col2:
    st.subheader("거래 입력")
    if status == 'waiting': st.warning("대기 중입니다...")
    elif status == 'trading':
        label = "최소 판매가(WTA)" if display_role == 'seller' else "최대 구매가(WTP)"
        price = st.number_input(label, min_value=0, max_value=10000, step=100)
        if st.button("데이터 제출"):
            supabase.table('students').update({"bid_price": price}).eq('name', user_name).execute()
            st.balloons()
            st.success("제출 완료!")

if status == 'result':
    st.divider()
    if my_trade:
        st.balloons()
        st.success(f"### 🎉 거래 성공! (체결가: {my_trade['price']:,}원)")
        st.write(f"🤝 거래 상대방: **{my_trade['seller_name'] if user_name == my_trade['buyer_name'] else my_trade['buyer_name']}**님")
    elif user_data['bid_price'] > 0:
        st.error("### 📉 거래 실패 (가격 불일치)")
    # 학생 화면에서 전체 거래 건수 통계는 제거되었습니다.
