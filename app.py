import streamlit as st
import google.generativeai as genai
import requests
import json
import re # 금리 파싱을 위해 정규표현식 라이브러리 추가

# --- API 호출 함수들 ---

def get_products_from_api(api_key, product_type):
    """사용자가 선택한 상품 종류(예금/적금)에 따라 API를 호출합니다."""
    if product_type == "예금":
        url = "http://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json"
    elif product_type == "적금":
        url = "http://finlife.fss.or.kr/finlifeapi/savingProductsSearch.json"
    else:
        return "잘못된 상품 종류입니다."

    params = {'auth': api_key, 'topFinGrpNo': '020000', 'pageNo': 1}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data.get('result', {}).get('baseList'):
            return f"현재 조회 가능한 {product_type} 상품이 없습니다."
        return json.dumps(data, ensure_ascii=False, indent=2) # 전체 데이터를 넘겨주어 옵션(금리) 정보도 활용
    except Exception as e:
        return f"API 호출 또는 데이터 처리 중 오류가 발생했습니다: {e}"

# --- 추천 및 계산 로직 함수 ---

def create_prompt(user_profile, product_type):
    """수집된 사용자 정보로 Gemini 프롬프트를 생성합니다."""
    return f"""
    당신은 최고의 금융 컨설턴트입니다. 사용자는 '{product_type}' 상품을 찾고 있습니다.
    아래의 '사용자 정보'와 '전체 금융상품 리스트'를 바탕으로, 사용자에게 가장 적합한 상품 3가지를 추천하고 그 이유를 설명해주세요.

    [사용자 정보]
    - 위험 감수 성향: {user_profile.get('risk', '정보 없음')}
    - 투자 목표: {user_profile.get('goal', '정보 없음')}
    - 예상 투자 기간: {user_profile.get('period', '정보 없음')}

    [전체 금융상품 리스트 (JSON 형식)]
    {{product_list_str}}

    [출력 형식]
    - 추천 상품마다 이름과 **12개월 기준 세전 금리**를 명확하게 'OO 예금 (연 X.XX%)' 형식으로 표시해주세요.
    - 각 상품에 대한 추천 이유를 사용자의 모든 정보(성향, 목표, 기간)와 연결지어 논리적으로 설명해주세요.
    - 말투는 친절하고 이해하기 쉽게 작성해주세요.
    """

def parse_investment_string(text):
    """ '500만원' 같은 문자열에서 숫자 5000000을 추출합니다. """
    text = text.replace(',', '')
    amount = float(re.findall(r'[\d.]+', text)[0])
    if '억' in text:
        amount *= 100000000
    if '만' in text:
        amount *= 10000
    return int(amount)

def calculate_final_amount(product_name, amount_str, recommendation_text, product_type):
    """추천 텍스트에서 금리를 파싱하고 예상 수령액을 계산합니다."""
    try:
        # 투자 금액 파싱
        principal = parse_investment_string(amount_str)

        # 추천 텍스트에서 해당 상품 정보 찾기
        match = re.search(f"{re.escape(product_name)}.*?연\s*([\d.]+)\s*%", recommendation_text)
        if not match:
            return f"'{product_name}'의 금리 정보를 찾을 수 없습니다. 상품명을 정확하게 입력했는지 확인해주세요."
        
        interest_rate = float(match.group(1)) / 100  # 금리를 소수점으로 변환
        
        # 세금(이자소득세 15.4%)
        tax_rate = 0.154

        if product_type == "예금":
            # 예금 (1년 만기 단리)
            interest = principal * interest_rate
            tax = interest * tax_rate
            final_amount = principal + interest - tax
            return f"""
            - **투자 원금**: {principal:,.0f}원
            - **예상 이자(세전)**: {interest:,.0f}원 (연 {interest_rate*100:.2f}%)
            - **이자 소득세(15.4%)**: {tax:,.0f}원
            ---
            - **세후 예상 수령액**: **{final_amount:,.0f}원**
            """
        elif product_type == "적금":
            # 적금 (12개월 매월 납입, 만기지급식, 단리)
            monthly_payment = principal # 입력 금액을 월 납입액으로 가정
            total_principal = monthly_payment * 12
            # 단리 적금 이자 계산 (월복리 아님)
            interest = monthly_payment * interest_rate * (12 * (12 + 1) / 2) / 12
            tax = interest * tax_rate
            final_amount = total_principal + interest - tax
            return f"""
            '{amount_str}'을 **매월 납입**한다고 가정합니다.
            - **총 납입 원금**: {total_principal:,.0f}원 ({principal:,.0f}원 x 12개월)
            - **예상 이자(세전)**: {interest:,.0f}원 (연 {interest_rate*100:.2f}%, 단리)
            - **이자 소득세(15.4%)**: {tax:,.0f}원
            ---
            - **세후 예상 수령액**: **{final_amount:,.0f}원**
            """

    except (IndexError, ValueError):
        return "금액을 정확히 인식하지 못했습니다. '500만원', '1000000' 과 같이 입력해주세요."
    except Exception as e:
        return f"계산 중 오류가 발생했습니다: {e}"


# --- Streamlit UI 및 메인 로직 ---

st.set_page_config(page_title="AI 금융 비서", page_icon="🤖")
st.title("🤖 AI 금융 비서")

# --- API 키 설정 ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    FSS_API_KEY = st.secrets["FSS_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except (FileNotFoundError, KeyError):
    st.error("API 키를 Streamlit Secrets에 설정해야 합니다.")
    st.stop()

# --- 세션 상태 초기화 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "stage" not in st.session_state:
    st.session_state.stage = "start"
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}
if "product_type" not in st.session_state:
    st.session_state.product_type = None
if "recommendation_text" not in st.session_state:
    st.session_state.recommendation_text = ""

# --- 이전 대화 내용 표시 ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 메인 대화 로직 ---
if st.session_state.stage == "start":
    if not st.session_state.messages:
        st.session_state.messages.append({"role": "assistant", "content": "안녕하세요! 어떤 금융상품을 찾고 계신가요?"})
        with st.chat_message("assistant"):
            st.markdown("안녕하세요! 어떤 금융상품을 찾고 계신가요?")

    col1, col2 = st.columns(2)
    if col1.button("🏦 예금 추천받기"):
        st.session_state.product_type = "예금"
        st.session_state.stage = "ask_risk"
        st.rerun()
    if col2.button("💰 적금 추천받기"):
        st.session_state.product_type = "적금"
        st.session_state.stage = "ask_risk"
        st.rerun()

elif st.session_state.stage == "ask_risk":
    st.session_state.messages = [] # 새 추천 시작 시 대화 초기화
    initial_message = f"네, '{st.session_state.product_type}' 상품 추천을 시작하겠습니다. 먼저, 투자 성향을 알려주시겠어요? (예: 안정추구형, 공격투자형 등)"
    st.session_state.messages.append({"role": "assistant", "content": initial_message})
    with st.chat_message("assistant"):
        st.markdown(initial_message)
    st.session_state.stage = "ask_goal" # 바로 다음 단계로 이동하여 사용자 입력을 기다림

# 사용자 입력을 받는 부분은 chat_input으로 통합
if user_input := st.chat_input("메시지를 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        current_stage = st.session_state.get("stage")
        
        if current_stage == "ask_goal":
            st.session_state.user_profile['risk'] = user_input
            response_text = "성향을 파악했어요. 이 자금을 운용하려는 주요 목표는 무엇인가요? (예: 목돈 만들기, 여행 자금 등)"
            st.session_state.stage = "ask_period"
        
        elif current_stage == "ask_period":
            st.session_state.user_profile['goal'] = user_input
            response_text = "좋은 목표네요! 마지막으로, 예상 투자 기간은 얼마나 생각하세요? (예: 1년, 24개월 등)"
            st.session_state.stage = "generate_recommendation"
        
        elif current_stage == "generate_recommendation":
            st.session_state.user_profile['period'] = user_input
            with st.spinner("최신 금융상품 정보를 바탕으로 AI가 맞춤 추천을 생성 중입니다..."):
                product_list_str = get_products_from_api(FSS_API_KEY, st.session_state.product_type)
                if "오류" not in product_list_str and "없습니다" not in product_list_str:
                    final_prompt_template = create_prompt(st.session_state.user_profile, st.session_state.product_type)
                    final_prompt = final_prompt_template.format(product_list_str=product_list_str)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(final_prompt)
                    response_text = response.text
                    st.session_state.recommendation_text = response_text # 추천 내용을 저장
                else:
                    response_text = product_list_str
            st.session_state.stage = "calculate_interest" # 계산 단계로 이동
            response_text += "\n\n---\n**추천 상품의 예상 수령액이 궁금하신가요?**\n'상품이름, 투자금액' 형식으로 입력해보세요. (예: OO은행 예금, 500만원)"

        elif current_stage == "calculate_interest":
            try:
                product_name, amount_str = user_input.split(',')
                product_name = product_name.strip()
                amount_str = amount_str.strip()
                response_text = calculate_final_amount(product_name, amount_str, st.session_state.recommendation_text, st.session_state.product_type)
            except ValueError:
                response_text = "입력 형식을 확인해주세요. '상품이름, 투자금액' 형식으로 입력해야 합니다. (예: OO은행 예금, 500만원)"
        
        else: # "done" 또는 다른 단계일 경우
            response_text = "새로운 추천을 받으시려면 페이지를 새로고침 해주세요."

        st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
