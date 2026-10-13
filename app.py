import streamlit as st
import os
import json
from openai import OpenAI

# 页面配置
st.set_page_config(page_title="MediCouncil 智能辅助诊断", layout="wide")
st.title("MediCouncil 智能辅助诊断系统")

# ================= 状态管理初始化 =================
if "messages" not in st.session_state:
    st.session_state.messages = [] # 记录问诊历史
if "report" not in st.session_state:
    st.session_state.report = ""   # 当前的诊断报告
if "questions" not in st.session_state:
    st.session_state.questions = [] # 当前的追问问题
if "round" not in st.session_state:
    st.session_state.round = 0      # 当前追问轮数（最多3轮）
if "input_text" not in st.session_state:
    st.session_state.input_text = ""

def get_api_key(key_name):
    key = os.environ.get(key_name)
    if not key:
        try:
            key = st.secrets[key_name]
        except:
            pass
    return key

# ================= 核心 Prompt =================
# 让 AI 自己判断是否需要追问，并且强制 JSON 输出
SYSTEM_PROMPT = """
你是一位三甲医院的资深全科医生。你的任务是根据患者的症状，进行临床推理。
请严格遵守以下规则：
1. 必须围绕临床医学、器质性病变进行推理，严禁编造娱乐化、心理化的虚假诊断（如“演唱会渴望综合征”）。
2. 每次接收用户输入，你都必须优先输出一份【诊断报告】。
3. 然后，评估患者提供的信息是否足够。如果信息太模糊（例如只有“我头疼”），你需要提出最多3个针对性的追问问题。如果信息已经足够，则不需要追问。
4. 追问必须是选择题形式（提供选项）或者简短填空形式，方便患者快速回答。

你必须且只能输出一个标准的 JSON 格式，不要包含任何 Markdown 代码块标记（如 ```json ）。
JSON 结构必须严格如下：
{
  "report": "Markdown格式的诊断报告。包含：1.预诊断概述 2.可能疾病及概率排序 3.就诊建议。如果没有足够信息给出详细的概率，请给出基于现有信息的最专业推断，并说明需要进一步确认。",
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
如果不需要追问，questions 请留空数组 []。
"""

def call_ai_doctor(messages, max_questions=3):
    try:
        api_key = get_api_key("DEEPSEEK_API_KEY")
        if not api_key:
            return {"report": "【错误】未配置 API Key", "questions": []}
        
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        
        # 构建对话上下文
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        api_messages.extend(messages)
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=api_messages,
            temperature=0.3, # 降低随机性，保证诊断的严谨性
        )
        
        # 清理可能存在的 Markdown 标记
        raw_text = response.choices[0].message.content.strip()
        if raw_text.startswith("```json"): raw_text = raw_text[7:]
        if raw_text.startswith("```"): raw_text = raw_text[3:]
        if raw_text.endswith("```"): raw_text = raw_text[:-3]
        
        result = json.loads(raw_text.strip())
        
        # 强制限制最多返回3个问题
        if "questions" in result and len(result["questions"]) > max_questions:
            result["questions"] = result["questions"][:max_questions]
            
        return result
    except Exception as e:
        return {"report": f"【调用失败】{str(e)}", "questions": []}

# ================= 界面渲染 =================

with st.sidebar:
    st.header("患者信息录入")
    if st.button("🔄 重新开始一次诊断"):
        st.session_state.messages = []
        st.session_state.report = ""
        st.session_state.questions = []
        st.session_state.round = 0
        st.session_state.input_text = ""
        st.rerun()

# 侧边栏显示历史记录（可选）
with st.sidebar:
    st.markdown("---")
    st.subheader("问诊历史")
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.caption(f"🙋 患者：{msg['content']}")
        elif msg["role"] == "assistant":
            # 助手消息是JSON，只显示报告部分的前两行做摘要
            try:
                data = json.loads(msg["content"])
                st.caption(f"👨‍⚕️ 医生：{data.get('report', '')[:50]}...")
            except:
                pass

# 第一步：初始输入
if not st.session_state.messages:
    st.info("请在下方描述您的基础症状（例如：我头疼，晚上睡觉流口水）")
    initial_symptom = st.text_area("症状描述：", height=100, key="initial_input")
    
    if st.button("开始智能分析", type="primary"):
        if not initial_symptom.strip():
            st.warning("请先输入您的症状哦～")
        else:
            st.session_state.messages.append({"role": "user", "content": initial_symptom})
            with st.spinner("AI 医生正在思考并生成初步报告..."):
                result = call_ai_doctor(st.session_state.messages)
                st.session_state.report = result.get("report", "")
                st.session_state.questions = result.get("questions", [])
                st.session_state.messages.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
                st.rerun()

# 如果已有报告，直接展示
if st.session_state.report:
    st.markdown("### 📋 诊断报告")
    st.markdown(st.session_state.report)
    st.markdown("---")

# 处理追问逻辑
if st.session_state.questions and st.session_state.round < 3:
    st.subheader(f"请您补充以下信息（第 {st.session_state.round + 1} 轮，最多 3 轮）")
    
    # 使用表单收集追问回答
    with st.form(key=f"follow_up_form_{st.session_state.round}"):
        answers = {}
        for q in st.session_state.questions:
            q_text = q.get("text", "未知问题")
            options = q.get("options", [])
            if options:
                # 如果有选项，用 radio
                answers[q_text] = st.radio(q_text, options, index=None, key=f"{q.get('id')}_{st.session_state.round}")
            else:
                # 没选项就用 text_input
                answers[q_text] = st.text_input(q_text, key=f"{q.get('id')}_{st.session_state.round}")
                
        submit_answers = st.form_submit_button("提交补充信息")
        
        if submit_answers:
            # 检查是否所有问题都回答了
            if any(v is None or v == "" for v in answers.values()):
                st.warning("请回答所有问题后再提交。")
            else:
                # 记录用户回答
                answers_text = "\n".join([f"问：{k}\n答：{v}" for k, v in answers.items()])
                st.session_state.messages.append({"role": "user", "content": f"补充信息：\n{answers_text}"})
                st.session_state.round += 1
                
                with st.spinner("AI 医生正在根据补充信息更新报告..."):
                    result = call_ai_doctor(st.session_state.messages)
                    st.session_state.report = result.get("report", "")
                    st.session_state.questions = result.get("questions", [])
                    st.session_state.messages.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
                    st.rerun()

elif st.session_state.round >= 3:
    st.info("已达到最大追问轮次（3轮）。以上是基于现有信息的最全面分析，请结合报告尽快就医。")
    if st.button("🔄 重新开始一次诊断"):
        st.session_state.messages = []
        st.session_state.report = ""
        st.session_state.questions = []
        st.session_state.round = 0
        st.rerun()

# 提供下载按钮
if st.session_state.report:
    st.download_button(
        label="下载最终报告 TXT",
        data=st.session_state.report,
        file_name="medicouncil_final_report.txt",
        mime="text/plain"
    )