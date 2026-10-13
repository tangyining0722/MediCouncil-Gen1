 import streamlit as st
import os
import time
import json
from openai import OpenAI

# 页面配置
st.set_page_config(page_title="MediCouncil 智能辅助诊断", layout="wide")
st.title("MediCouncil 智能辅助诊断系统")

# 初始化 Session State（用于管理多步交互）
if "step" not in st.session_state:
    st.session_state.step = 1
if "symptoms" not in st.session_state:
    st.session_state.symptoms = ""
if "questions_json" not in st.session_state:
    st.session_state.questions_json = []
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "final_report" not in st.session_state:
    st.session_state.final_report = ""

def get_api_key(key_name):
    key = os.environ.get(key_name)
    if not key:
        try:
            key = st.secrets[key_name]
        except:
            pass
    return key

# 严格限制为临床导向的 Prompt
SYSTEM_PROMPT = """
你是一位三甲医院的资深全科医生。请严格遵守以下规则：
1. 必须围绕临床医学、器质性病变和常见躯体疾病进行推理。
2. 严禁将非器质性心理状态（如追星、不想上班、FOMO）作为主要诊断，除非患者明确提及并伴有严重的生理症状。
3. 语言要专业、通俗，直接给出就医指导，不要写段子或编造幽默诊断。

输出格式要求：必须只输出一个标准的 JSON 格式数据，不要包含任何 Markdown 代码块标记（如 ```json ）。
JSON 结构必须如下：
{
  "questions": [
    {
      "id": "q1",
      "text": "疼痛的具体性质是什么？",
      "options": ["搏动性跳痛", "持续性钝痛", "刺痛", "其他"]
    },
    {
      "id": "q2",
      "text": "伴随症状有哪些？",
      "options": ["无", "恶心/呕吐", "发热", "视力模糊"]
    }
  ]
}
请根据患者的初步症状，生成 3-5 个最关键的选择题。选项不要超过4个。
"""

REPORT_PROMPT = """
你是一位三甲医院的资深全科医生。请根据患者提供的基础症状和后续的选择题回答，生成一份最终的医学辅助报告。
报告必须包含：
1. 预诊断概述（根据现有信息，给出综合判断，安抚情绪）
2. 可能疾病及概率排序（列出3-5种，按可能性从高到低，标注粗略概率）
3. 就诊建议（建议挂什么科室，做什么检查，就诊前如何缓解，如果有紧急危险信号必须用加粗字体警告）

请使用通俗易懂且专业的语言，输出 Markdown 格式。
"""

def call_deepseek_for_questions(symptoms):
    try:
        api_key = get_api_key("DEEPSEEK_API_KEY")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"患者症状：{symptoms}"}
            ],
            temperature=0.3,
        )
        # 清理可能存在的 Markdown 标记
        raw_text = response.choices[0].message.content.strip()
        if raw_text.startswith("```json"): raw_text = raw_text[7:]
        if raw_text.startswith("```"): raw_text = raw_text[3:]
        if raw_text.endswith("```"): raw_text = raw_text[:-3]
        
        return json.loads(raw_text.strip())
    except Exception as e:
        st.error(f"生成追问问题失败: {str(e)}")
        return None

def call_ai_for_report(symptoms, answers_text):
    try:
        api_key = get_api_key("DEEPSEEK_API_KEY")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        final_input = f"基础症状：{symptoms}\n追问回答：{answers_text}"
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": REPORT_PROMPT},
                {"role": "user", "content": final_input}
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"【调用失败】{str(e)}"

# ================= 界面渲染逻辑 =================

# 侧边栏，可以放重置按钮
with st.sidebar:
    st.header("患者信息录入")
    if st.button("🔄 重新开始一次诊断"):
        st.session_state.step = 1
        st.session_state.symptoms = ""
        st.session_state.questions_json = []
        st.session_state.answers = {}
        st.session_state.final_report = ""
        st.rerun()

# 步骤一：输入初始症状
if st.session_state.step == 1:
    symptoms = st.text_area("请输入您的基础症状（一句话即可，例如：我头疼，晚上睡觉流口水）：", height=150, value=st.session_state.symptoms)
    if st.button("下一步：生成追问", type="primary"):
        if not symptoms.strip():
            st.warning("请先输入您的症状哦～")
        else:
            st.session_state.symptoms = symptoms
            with st.spinner("AI 正在为您生成关键追问..."):
                questions_data = call_deepseek_for_questions(symptoms)
                if questions_data and "questions" in questions_data:
                    st.session_state.questions_json = questions_data["questions"]
                    st.session_state.step = 2
                    st.rerun()
                else:
                    st.error("生成追问失败，请检查 API 或网络。")

# 步骤二：回答选择题
elif st.session_state.step == 2:
    st.subheader("请您补充以下关键信息")
    st.info("为了让诊断更精确，请回答以下几个问题：")
    
    answers = {}
    for q in st.session_state.questions_json:
        q_text = q.get("text", "未知问题")
        options = q.get("options", ["是", "否"])
        # 使用 selectbox 或 radio 渲染选择题
        answer = st.radio(q_text, options, index=None, key=q.get("id"))
        answers[q_text] = answer
        
    if st.button("确认回答，生成报告", type="primary"):
        # 检查是否所有题目都回答了
        if None in answers.values():
            st.warning("请回答所有问题后再点击确认。")
        else:
            st.session_state.answers = answers
            with st.spinner("双模型协作中，正在为您生成深度分析报告..."):
                # 将回答拼接成文本
                answers_text = "\n".join([f"问：{k}\n答：{v}" for k, v in answers.items()])
                report = call_ai_for_report(st.session_state.symptoms, answers_text)
                st.session_state.final_report = report
                st.session_state.step = 3
                st.rerun()

# 步骤三：展示最终报告
elif st.session_state.step == 3:
    st.success("✅ 分析完成！以下是为您生成的辅助诊断报告")
    st.markdown("---")
    st.markdown(st.session_state.final_report)
    st.markdown("---")
    st.download_button("下载辅助报告 TXT", st.session_state.final_report, "medicouncil_report.txt", "text/plain")