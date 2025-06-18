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
        
        if not data.get('result', {}).get('baseList'):
            return "현재 조회 가능한 예금 상품이 없습니다."
        
        return json.dumps(data['result']['baseList'], ensure_ascii=False, indent=2)

    except requests.exceptions.RequestException as e:
        return f"API 호출 중 오류가 발생했습니다: {e}"
    except Exception as e:
        return f"데이터 처리 중 오류가 발생했습니다: {e}"


def create_prompt(user_profile):
    """수집된 모든 사용자 정보를 바탕으로 Gemini에게 보낼 프롬프트를 생성합니다."""
    # product_list_str는 추천 단계에서 API 호출 후 전달받습니다.
    return f"""
    당신은 최고의 금융 컨설턴트입니다. 아래의 '사용자 정보'와 '전체 금융상품 리스트'를 바탕으로, 사용자에게 가장 적합한 금융상품 3가지를 추천하고 그 이유를 구체적으로 설명해주세요.

    [사용자 정보]
    - 위험 감수 성향: {user_profile.get('risk', '정보 없음')}
    - 투자 목표: {user_profile.get('goal', '정보 없음')}
    - 예상 투자 기간: {user_profile.get('period', '정보 없음')}

    [전체 금융상품 리스트 (JSON 형식)]
    {{product_list_str}}

    [출력 형식]
    - 추천은 순위 형식으로 1, 2, 3위로 나누어 설명해주세요.
    - 각 상품에 대한 추천 이유를 사용자의 모든 정보(성향, 목표, 기간)와 연결지어 논리적으로 설명해주세요.
    - 말투는 친절하고 이해하기 쉽게 작성해주세요.
    """

# --- Streamlit UI 및 메인 로직 ---

st.set_page_config(page_title="대화형 금융 챗봇", page_icon="💬")
st.title("💬 대화형 AI 금융상품 추천 챗봇")
st.write("자연스러운 대화를 통해 최적의 예금 상품을 추천받으세요!")

# --- 1. API 키 설정 ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    FSS_API_KEY = st.secrets["FSS_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except (FileNotFoundError, KeyError):
    st.error("API 키를 설정해야 합니다. Streamlit Cloud의 Secrets에 키를 추가해주세요.")
    st.stop()

# --- 2. 세션 상태 초기화 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
# 대화의 단계를 관리할 'stage' 추가
if "stage" not in st.session_state:
    st.session_state.stage = "ask_risk"
# 사용자 정보를 저장할 딕셔너리 초기화
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}


# --- 3. 첫 방문 시 시작 메시지 표시 ---
if not st.session_state.messages:
    initial_message = "안녕하세요! 당신에게 꼭 맞는 예금 상품을 찾아드릴게요. 먼저, 투자 성향을 알려주시겠어요? (예: 안정적인게 좋아요, 공격적으로 하고 싶어요 등)"
    st.session_state.messages.append({"role": "assistant", "content": initial_message})

# --- 4. 이전 대화 내용 표시 ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# --- 5. 사용자 입력 처리 및 대화 흐름 관리 ---
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 사용자의 메시지를 대화 기록에 추가하고 화면에 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 챗봇의 다음 행동을 'stage'에 따라 결정
    with st.chat_message("assistant"):
        
        # [Stage 1] 위험 성향을 물어본 상태
        if st.session_state.stage == "ask_risk":
            st.session_state.user_profile['risk'] = prompt
            response_text = "네, '"+ prompt + "' 성향이시군요! 그럼 이 자금을 운용하려는 주요 목표는 무엇인가요? (예: 1년 안에 해외여행 가기, 5년 뒤 내 집 마련 등)"
            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            st.session_state.stage = "ask_goal" # 다음 단계로 변경

        # [Stage 2] 투자 목표를 물어본 상태
        elif st.session_state.stage == "ask_goal":
            st.session_state.user_profile['goal'] = prompt
            response_text = "좋은 목표네요! 마지막으로, 예상 투자 기간은 얼마나 생각하고 계신가요? (예: 1년 미만, 1~3년, 5년 이상 등)"
            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            st.session_state.stage = "ask_period" # 다음 단계로 변경

        # [Stage 3] 투자 기간을 물어본 상태 -> 모든 정보 수집 완료!
        elif st.session_state.stage == "ask_period":
            st.session_state.user_profile['period'] = prompt
            
            with st.spinner("최신 금융상품 정보를 조회하고 있어요..."):
                product_list_str = get_deposit_products_from_api(FSS_API_KEY)
            
            with st.spinner("수집된 정보를 바탕으로 Gemini AI가 맞춤 상품을 분석 중입니다..."):
                if "오류" not in product_list_str and "없습니다" not in product_list_str:
                    # format()을 사용하여 최종 프롬프트 완성
                    final_prompt_template = create_prompt(st.session_state.user_profile)
                    final_prompt = final_prompt_template.format(product_list_str=product_list_str)

                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(final_prompt)
                    recommendation = response.text
                else:
                    recommendation = product_list_str
            
            st.markdown(recommendation)
            st.session_state.messages.append({"role": "assistant", "content": recommendation})
            st.session_state.stage = "done" # 모든 과정이 끝났음을 표시
