import streamlit as st
import os
import time
import requests
import json

# 页面配置
st.set_page_config(page_title="MediCouncil 第一代", layout="wide")
st.title("MediCouncil 第一代 (通用医疗协同决策教育原型)")

# 初始化 session_state
if "result" not in st.session_state:
    st.session_state["result"] = None

# 安全获取密钥的函数（兼容 Render 和 Streamlit）
def get_api_key(key_name):
    # 优先从 Render 环境变量读取，其次从 Streamlit Secrets 读取
    key = os.environ.get(key_name)
    if not key:
        try:
            key = st.secrets[key_name]
        except:
            pass
    return key

# 模拟双模型调用
def call_ai_model(provider, prompt):
    try:
        if provider == "deepseek":
            api_key = get_api_key("DEEPSEEK_API_KEY")
            if not api_key:
                return {"error": "未配置 DeepSeek API Key，请在 Render 环境变量中设置 DEEPSEEK_API_KEY"}
            
            # 这里替换为你实际的 DeepSeek API 调用代码
            # 实际调用时需要携带 api_key，例如：
            # headers = {"Authorization": f"Bearer {api_key}"}
            # 为演示，此处直接返回模拟结果，以便你确认界面正常
            return {"content": "DeepSeek 分析结果：根据患者症状，建议进行进一步的心血管检查。"}
            
        elif provider == "doubao":
            api_key = get_api_key("DOUBAO_API_KEY")
            if not api_key:
                return {"error": "未配置豆包 API Key，请在 Render 环境变量中设置 DOUBAO_API_KEY"}
            
            # 这里替换为你实际的豆包 API 调用代码
            return {"content": "豆包分析结果：建议结合既往病史，重点关注血压和血糖指标。"}
            
    except Exception as e:
        return {"error": f"调用 {provider} 失败: {str(e)}"}

    return {"error": f"{provider} 未返回任何数据"}

# 侧边栏输入
with st.sidebar:
    st.header("患者信息录入")
    symptoms = st.text_area("请输入患者主诉、现病史等：", height=150)
    analyze_button = st.button("开始协同决策分析", type="primary")

# 主界面逻辑
if analyze_button and symptoms:
    with st.spinner("正在调用双模型进行独立分析..."):
        time.sleep(1.0) # 模拟网络延迟
        
        prompt = f"患者症状：{symptoms}。请给出医疗建议。"
        
        deepseek_result = call_ai_model("deepseek", prompt)
        doubao_result = call_ai_model("doubao", prompt)
        
        st.session_state["result"] = {
            "warnings": ["妊娠或产后头痛，伴血压高、水肿、上腹痛、视物模糊。"],
            "questions": ["症状从什么时候开始？是否突然出现或持续加重？", "具体部位、严重程度和伴随症状是什么？"],
            "opinions": [
                {"provider": "deepseek", **deepseek_result},
                {"provider": "doubao", **doubao_result}
            ],
            "evidence": [],
            "evidence_review": "证据核查通过。",
            "disagreement_review": "双模型分歧审查：两者建议方向一致，无显著分歧。"
        }

# 展示结果
if st.session_state["result"] is not None:
    r = st.session_state["result"]
    
    # 1. 建议追问
    st.subheader("建议追问")
    for q in r.get("questions", []):
        st.write(f"• {q}")
        
    # 2. 双模型独立分析
    st.subheader("双模型独立分析")
    cols = st.columns(2)
    
    for i, provider in enumerate(["deepseek", "doubao"]):
        with cols[i]:
            st.markdown(f"**{provider.capitalize()}**")
            match = next((x for x in r.get("opinions", []) if x.get("provider") == provider), None)
            
            if match:
                if hasattr(match, 'error') and match.error:
                    st.error(match.error)
                elif hasattr(match, 'content'):
                    st.write(match.content)
                else:
                    st.write(match)
            else:
                st.caption("未调用")
                
    # 3. 其他展示模块
    st.subheader("PubMed 检索结果 (摘要，不等于全文)")
    for item in r.get("evidence", []):
        st.markdown(f"[{item.get('title', '无标题')}]({item.get('url', '#')}) · PMID {item.get('pmid', '未知')}")
        
    st.subheader("证据核查")
    st.write(r.get("evidence_review", "无"))
    
    st.subheader("分歧审查")
    st.write(r.get("disagreement_review", "无"))

    # ================= 新增：生成并展示报告 =================
    report_lines = []
    report_lines.append("# MediCouncil 辅助决策报告\n")
    report_lines.append("## 建议追问")
    for q in r.get("questions", []):
        report_lines.append(f"- {q}")
    
    report_lines.append("\n## 双模型独立分析")
    for op in r.get("opinions", []):
        report_lines.append(f"### {op.get('provider', '未知模型').capitalize()}")
        if op.get("error"): report_lines.append(f"【错误信息】: {op['error']}")
        elif op.get("content"): report_lines.append(op['content'])
    
    report_text = "\n".join(report_lines)

    st.subheader("📄 生成的辅助报告")
    st.markdown(report_text)

    st.download_button("下载辅助报告 TXT", report_text, "medicouncil_report.txt", "text/plain")
