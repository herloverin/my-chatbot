import streamlit as st
import google.generativeai as genai
import requests
import json

# --- 유틸리티 함수들 ---

def get_deposit_products_from_api(api_key):
    """금융감독원 API를 호출하여 예금 상품 리스트를 JSON 문자열로 반환합니다."""
    url = "http://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json"
    params = {
        'auth': api_key,
        'topFinGrpNo': '020000',
        'pageNo': 1
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # 'baseList'가 비어있는지 확인
        if not data.get('result', {}).get('baseList'):
            return "현재 조회 가능한 예금 상품이 없습니다."
        
        # 성공 시, 결과의 baseList를 JSON 문자열로 변환하여 반환
        return json.dumps(data['result']['baseList'], ensure_ascii=False, indent=2)

    except requests.exceptions.RequestException as e:
        return f"API 호출 중 오류가 발생했습니다: {e}"
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        # 응답 형식이 예상과 다르거나 JSON 파싱에 실패한 경우
        return f"API 응답 데이터를 처리하는 중 오류가 발생했습니다: {e}"


def create_prompt(user_profile, product_list_str):
    """Gemini에게 보낼 프롬프트를 생성합니다."""
    return f"""
    당신은 최고의 금융 컨설턴트입니다. 아래의 '사용자 정보'와 '전체 금융상품 리스트'를 바탕으로, 사용자에게 가장 적합한 금융상품 3가지를 추천하고 그 이유를 구체적으로 설명해주세요.

    [사용자 정보]
    - 위험 감수 성향: {user_profile['risk']}

    [전체 금융상품 리스트 (JSON 형식)]
    {product_list_str}

    [출력 형식]
    - 추천은 순위 형식으로 1, 2, 3위로 나누어 설명해주세요.
    - 각 상품에 대한 추천 이유를 사용자의 정보와 연결지어 논리적으로 설명해주세요.
    - 말투는 친절하고 이해하기 쉽게 작성해주세요.
    """

# --- Streamlit UI 및 메인 로직 ---

st.set_page_config(page_title="Gemini 금융 챗봇", page_icon="💰")
st.title("💰 AI 금융상품 추천 챗봇")
st.write("간단한 질문에 답변하고 최적의 예금 상품을 추천받으세요!")

# --- 1. API 키 설정 (보안 및 실행 환경에 맞게 수정) ---
try:
    # Streamlit Cloud 배포 환경에서 Secrets를 통해 키를 가져옴
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    FSS_API_KEY = st.secrets["FSS_API_KEY"]
except (FileNotFoundError, KeyError):
    # 로컬 환경일 경우 (secrets.toml 파일이 없거나 키가 없을 때)
    # 직접 입력하거나 다른 방법으로 키를 관리할 수 있습니다.
    # 이 예제에서는 로컬 실행 시 에러 메시지를 보여줍니다.
    st.error("API 키를 설정해야 합니다. Streamlit Cloud의 Secrets에 키를 추가해주세요.")
    st.stop()

# Gemini API 설정은 키를 성공적으로 불러온 후에 한 번만 실행합니다.
genai.configure(api_key=GOOGLE_API_KEY)

# --- 2. 세션 상태 초기화 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "step" not in st.session_state:
    st.session_state.step = "start"

# --- 3. 이전 대화 내용 표시 ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. 챗봇의 단계별 로직 실행 ---

# 시작 단계: 첫 방문 시에만 시작 메시지를 추가하고, 사용자 입력을 기다림
if st.session_state.step == "start":
    if not st.session_state.messages: # 대화 내용이 비어있을 때만 시작 메시지 표시
        with st.chat_message("assistant"):
            st.markdown("안녕하세요! 당신의 투자 성향에 맞는 예금 상품을 찾아드릴게요. 투자 시 원금 손실에 대해 얼마나 감수할 수 있으신가요?")
            st.session_state.messages.append({"role": "assistant", "content": "안녕하세요! ..."})
    
    # 사용자 선택을 위한 버튼 생성
    risk_options = {"안정적 (원금 보장 선호)": "안정적", "중립적 (어느 정도 위험 감수)": "중립적", "공격적 (고수익 추구)": "공격적"}
    for display_text, risk_value in risk_options.items():
        if st.button(display_text):
            # 버튼 클릭 시 사용자 정보 저장 및 다음 단계로 전환
            st.session_state.user_profile = {'risk': risk_value}
            st.session_state.messages.append({"role": "user", "content": f"제 성향은 '{risk_value}'입니다."})
            st.session_state.step = "recommend"
            st.rerun() # 화면을 새로고침하여 다음 단계 로직 실행

# 추천 단계: API 호출 및 Gemini 응답을 받아 한 번만 실행
elif st.session_state.step == "recommend":
    with st.chat_message("assistant"):
        with st.spinner("최신 금융상품 정보를 조회하고 있어요..."):
            product_list_str = get_deposit_products_from_api(FSS_API_KEY)
        
        with st.spinner("Gemini AI가 맞춤 상품을 분석 중입니다..."):
            if "오류" not in product_list_str and "없습니다" not in product_list_str:
                prompt = create_prompt(st.session_state.user_profile, product_list_str)
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                recommendation = response.text
            else:
                # API 호출 실패 또는 상품이 없을 경우의 메시지
                recommendation = product_list_str
        
        st.markdown(recommendation)
        st.session_state.messages.append({"role": "assistant", "content": recommendation})
        st.session_state.step = "done" # 모든 과정이 끝났음을 표시