import streamlit as st
import os
import time
from openai import OpenAI

# 页面配置
st.set_page_config(page_title="MediCouncil 智能辅助诊断", layout="wide")
st.title("MediCouncil 智能辅助诊断系统")
st.caption("请在左侧输入您的症状，即使只有一句话，AI 也会为您生成完整的分析和就医指南。")

# ================= 安全获取密钥 =================
def get_api_key(key_name):
    # 优先从 Render 环境变量读取，其次从 Streamlit Secrets 读取
    key = os.environ.get(key_name)
    if not key:
        try:
            key = st.secrets[key_name]
        except:
            pass
    return key

# ================= 核心 Prompt 定义 =================
SYSTEM_PROMPT = """
你是一位三甲医院的资深全科医生。用户可能会提供非常简短甚至模糊的症状描述（如“我头疼”）。
请不要抱怨信息不足，而是基于你丰富的临床经验，像真正的医生一样进行“顺藤摸瓜”式的推理。

请严格按照以下 Markdown 格式输出一份专业、通俗、让人能看懂的报告：
### 1. 预诊断概述
（简要说明根据当前症状，最可能的几种情况，并安抚患者情绪）

### 2. 可能疾病及概率排序
（列出3-5种可能的疾病，按可能性从高到低排序，并给出粗略的概率百分比。例如：1. 紧张性头痛（概率约60%）：由于...引起。）

### 3. 就诊建议
（明确建议挂什么科室，建议做哪些检查，以及在就诊前可以做什么来缓解。如果是紧急症状，请立刻用加粗字体警告就医！）

请注意：必须使用通俗易懂的语言，避免过多生涩的医学术语，同时保持专业度。
"""

# ================= 真实调用 API =================
def call_deepseek(symptoms):
    try:
        api_key = get_api_key("DEEPSEEK_API_KEY")
        if not api_key:
            return "【错误】未配置 DeepSeek API Key"
        
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"患者症状：{symptoms}"}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"【调用失败】{str(e)}"

def call_doubao(symptoms, deepseek_result):
    """
    让豆包作为“专家会诊”，对DeepSeek的诊断进行补充和复核。
    """
    try:
        api_key = get_api_key("DOUBAO_API_KEY")
        if not api_key:
            return "" # 如果没有配置豆包，静默返回空
        
        # 使用火山方舟的 API 地址
        client = OpenAI(api_key=api_key, base_url="https://ark.cn-beijing.volces.com/api/v3")
        
        prompt = f"""
        患者症状：{symptoms}
        另一位AI医生给出的初步分析如下：
        {deepseek_result}
        
        请基于上述信息，以“专家补充建议”的身份，补充分析中遗漏的可能疾病，并给出更细致的日常护理建议。
        输出格式要求：不要重复已有的分析，直接列出补充的内容，标题为“### 4. 专家补充与护理建议”。
        """
        
        # 使用你截图中的真实模型 ID
        response = client.chat.completions.create(
            model="doubao-seed-2.1-lite-260915", 
            messages=[
                {"role": "system", "content": "你是一位资深医学专家，负责对初步诊断进行查漏补缺和护理指导。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        # 如果豆包报错，返回空字符串，不让错误信息显示在页面上
        return ""

# ================= 界面交互 =================
with st.sidebar:
    st.header("患者信息录入")
    symptoms = st.text_area("请输入患者主诉、现病史等（简单一句话即可）：", height=150, placeholder="例如：我头疼，晚上睡觉流口水...")
    analyze_button = st.button("开始智能分析", type="primary")

if analyze_button:
    if not symptoms.strip():
        st.warning("请先输入您的症状哦～")
    else:
        with st.spinner("双模型协作推理中，正在为您生成高质量报告..."):
            # 1. 调用 DeepSeek 进行首轮预诊断
            deepseek_result = call_deepseek(symptoms)
            
            # 2. 调用豆包进行专家补充
            doubao_result = call_doubao(symptoms, deepseek_result)
            
            # 3. 合并结果，隐藏中间过程，直接展示一份完整的报告
            final_report = deepseek_result + "\n\n" + doubao_result
            
            st.success("✅ 分析完成！")
            st.markdown("---")
            # 直接渲染最终报告
            st.markdown(final_report)
            
            # 提供下载按钮
            st.download_button(
                label="下载辅助报告 TXT",
                data=final_report,
                file_name="medicouncil_report.txt",
                mime="text/plain"
            )