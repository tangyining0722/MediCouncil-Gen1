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
# 调整了部分提示，明确告知大模型选项支持多选
SYSTEM_PROMPT = """
你是一位三甲医院的资深全科医生。你的任务是根据患者的症状，进行临床推理。
请严格遵守以下规则：
1. 必须围绕临床医学、器质性病变进行推理，严禁编造娱乐化、心理化的虚假诊断（如“演唱会渴望综合征”）。
2. 每次接收用户输入，你都必须优先输出一份【诊断报告】。
3. 然后，评估患者提供的信息是否足够。如果信息太模糊（例如只有“我头疼”），你需要提出最多3个针对性的追问问题。如果信息已经足够，则不需要追问。
4. 追问必须是提供选项的选择题形式（患者可以从中选择一个甚至多个选项），或者简短填空形式，方便患者快速回答。

你必须且只能输出一个标准的 JSON 格式，不要包含任何 Markdown 代码块标记（如 ```json ）。
JSON 结构必须严格如下：
{
  "report": "Markdown格式的诊断报告。包含：1.预诊断概述 2.可能疾病及概率排序 3.就诊建议。如果没有足够信息给出详细的概率，请给出基于现有信息的最专业推断，并说明需要进一步确认。",
  "questions": [
    {
      "id": "q1",
      "text": "疼痛的具体性质是什么？（可多选）",
      "options": ["搏动性跳痛", "持续性钝痛", "刺痛", "其他"]
    },
    {
      "id": "q2",
      "text": "伴随症状有哪些？（可多选）",
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
            temperature=0.3,
        )
        
        raw_text = response.choices[0].message.content.strip()
        if raw_text.startswith("```json"): raw_text = raw_text[7:]
        if raw_text.startswith("```"): raw_text = raw_text[3:]
        if raw_text.endswith("```"): raw_text = raw_text[:-3]
        
        result = json.loads(raw_text.strip())
        
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

# 侧边栏问诊历史
with st.sidebar:
    st.markdown("---")
    st.subheader("问诊历史")
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.caption(f"🙋 患者：{msg['content']}")
        elif msg["role"] == "assistant":
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

# 展示当前报告
if st.session_state.report:
    st.markdown("### 📋 诊断报告")
    st.markdown(st.session_state.report)
    st.markdown("---")

# 处理追问逻辑 (多选版)
if st.session_state.questions and st.session_state.round < 3:
    st.subheader(f"请您补充以下信息（第 {st.session_state.round + 1} 轮，最多 3 轮）")
    
    # 使用表单收集追问回答
    with st.form(key=f"follow_up_form_{st.session_state.round}"):
        answers = {}
        for q in st.session_state.questions:
            q_text = q.get("text", "未知问题")
            options = q.get("options", [])
            
            # 判断类型并渲染组件
            if options:
                # 【修改点】：改为多选，允许用户选择一个甚至多个选项
                answers[q_text] = st.multiselect(q_text, options, key=f"{q.get('id')}_{st.session_state.round}")
            else:
                # 没选项就用 text_input
                answers[q_text] = st.text_input(q_text, key=f"{q.get('id')}_{st.session_state.round}")
                
        submit_answers = st.form_submit_button("提交补充信息")
        
        if submit_answers:
            # 【修改点】：多选情况的空值判断
            is_valid = True
            for v in answers.values():
                if isinstance(v, list) and len(v) == 0:
                    is_valid = False
                    break
                elif isinstance(v, str) and v.strip() == "":
                    is_valid = False
                    break
            
            if not is_valid:
                st.warning("请至少选择一个选项或填写内容后再提交。")
            else:
                # 【修改点】：将列表格式的答案转换为顿号分隔的字符串，拼接给大模型
                formatted_answers = []
                for k, v in answers.items():
                    if isinstance(v, list):
                        val_text = "、".join(v) # 例如："搏动性跳痛、伴随恶心"
                    else:
                        val_text = v
                    formatted_answers.append(f"问：{k}\n答：{val_text}")
                    
                answers_text = "\n".join(formatted_answers)
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