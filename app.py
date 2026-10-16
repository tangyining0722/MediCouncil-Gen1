import streamlit as st
import os
import json
import requests
import xml.etree.ElementTree as ET
import uuid
from openai import OpenAI

# ================= 页面配置 =================
st.set_page_config(page_title="人工智能辅助会诊系统", layout="wide")
st.title("人工智能辅助会诊系统")

# ================= 状态管理初始化 =================
if "messages" not in st.session_state: st.session_state.messages = []
if "report" not in st.session_state: st.session_state.report = ""
if "questions" not in st.session_state: st.session_state.questions = []
if "round" not in st.session_state: st.session_state.round = 0
if "pubmed_done" not in st.session_state: st.session_state.pubmed_done = False
if "asked_questions" not in st.session_state: st.session_state.asked_questions = []

def get_api_key(key_name):
    key = os.environ.get(key_name)
    if not key:
        try: key = st.secrets[key_name]
        except: pass
    return key

# ================= 底层 API 调用 =================
def call_llm(model_name, system_prompt, user_prompt, json_mode=False):
    try:
        if model_name == "deepseek":
            api_key = get_api_key("DEEPSEEK_API_KEY")
            if not api_key: return '{"error": "未配置 DeepSeek API Key"}'
            base_url = "https://api.deepseek.com/v1"
            model_id = "deepseek-chat"
        elif model_name == "doubao":
            api_key = get_api_key("DOUBAO_API_KEY")
            if not api_key: return '{"error": "豆包 API Key 未配置"}'
            base_url = "https://ark.cn-beijing.volces.com/api/v3"
            model_id = "doubao-seed-2.1-lite-260915" 
        else:
            return '{"error": "模型名称错误"}'

        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.3,
            response_format={"type": "json_object"} if json_mode else None
        )
        return response.choices[0].message.content
    except Exception as e:
        return f'{{"error": "调用失败: {str(e)}"}}'

# ================= PubMed 检索模块 =================
def search_pubmed(query, max_results=3):
    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmode=json&retmax={max_results}"
        res = requests.get(search_url, timeout=10)
        res.raise_for_status()
        id_list = res.json().get("esearchresult", {}).get("idlist", [])
        if not id_list: return ""

        ids_str = ",".join(id_list)
        fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml"
        fetch_res = requests.get(fetch_url, timeout=15)
        root = ET.fromstring(fetch_res.content)
        abstracts = []
        for article in root.findall(".//PubmedArticle"):
            title = article.find(".//ArticleTitle").text if article.find(".//ArticleTitle") is not None else "No Title"
            abstract_texts = article.findall(".//AbstractText")
            abstract = " ".join([t.text for t in abstract_texts if t.text]) if abstract_texts else "No Abstract"
            abstracts.append(f"标题：{title}\n摘要：{abstract[:600]}...")
        return "\n\n".join(abstracts)
    except:
        return ""

# ================= 核心逻辑：动态路由 =================
def evaluate_and_assign(messages_history):
    has_doubao = bool(get_api_key("DOUBAO_API_KEY"))
    if not has_doubao:
        return {"complexity": "low", "role_a_model": "deepseek", "role_b_model": "deepseek"}
    
    history_text = "".join([f"{'患者' if m['role']=='user' else '医生'}：{m['content']}\n" for m in messages_history])
    router_prompt = f"""
    以下是问诊对话历史：
    {history_text}
    请分析当前病例的复杂程度。如果症状单一、常见，定义复杂度为 "low"；如果症状涉及多系统、存在潜在风险、定义复杂度为 "high"。
    根据复杂度，请决定以下角色的分配（必须同时调用两个模型）：
    - 角色A（主诊医生）：负责生成核心诊断报告。
    - 角色B（质控专家）：负责严苛审查角色A的报告。
    请只输出 JSON 格式：{{"complexity": "low/high", "role_a_model": "deepseek/doubao", "role_b_model": "deepseek/doubao"}}
    """
    res = call_llm("deepseek", "你是一个医疗分诊调度系统。", router_prompt, json_mode=True)
    try:
        data = json.loads(res.strip().replace("```json", "").replace("```", ""))
        if "role_a_model" not in data or "role_b_model" not in data: raise ValueError("格式错误")
        return data
    except:
        return {"complexity": "low", "role_a_model": "deepseek", "role_b_model": "doubao"}

# ================= 核心逻辑：报告生成与追问 =================
def generate_report_and_questions(messages_history, route_info, current_round):
    role_a = route_info["role_a_model"]
    role_b = route_info["role_b_model"]
    context = "\n".join([f"{'患者' if m['role']=='user' else '医生'}：{m['content']}" for m in messages_history])
    asked_questions_text = "、".join(st.session_state.asked_questions) if st.session_state.asked_questions else "无"

    ask_instructions = ""
    if current_round < 3:
        ask_instructions = f"""
        4. 追问机制：提出最多3个针对性的追问问题。问题必须是选择题形式（提供选项，可多选），或简短填空。
        5. 【极其重要】你之前已经问过以下问题，绝对不允许再次提问完全一样的问题：
        历史问题：{asked_questions_text}
        6. 【强制要求】除非用户提供了极其详尽、无懈可击的病史（这种情况极少），否则你必须提出至少 1 个新的追问问题，不允许将 questions 数组留空。
        """
    else:
        ask_instructions = "4. 已达到最大追问轮次，不要再生成追问，questions 数组必须为空 []。"

    doctor_prompt = f"""
    你是一位资深全科医生。基于以下问诊历史，生成当前阶段的诊断报告。
    问诊历史：{context}
    规则：
    1. 必须优先输出一份【诊断报告】，包含：预诊断概述、可能疾病及概率排序、就诊建议。
    2. 必须围绕临床医学、器质性病变进行推理，严禁编造娱乐化诊断。
    3. 当前是第 {current_round + 1} 轮（最多3轮）。
    {ask_instructions}
    请只输出标准 JSON 格式：
    {{"report": "Markdown格式的报告内容", "questions": [ {{"id": "q1", "text": "问题1？", "options": ["选项A", "选项B"]}} ]}}
    """
    doctor_response = call_llm(role_a, "你是一位专业的医疗诊断医生。", doctor_prompt, json_mode=True)
    
    try:
        doctor_data = json.loads(doctor_response.strip().replace("```json", "").replace("```", ""))
        if not isinstance(doctor_data, dict): doctor_data = {}
    except:
        doctor_data = {}

    quality_prompt = f"""
    你是一位严苛的医疗质控专家。请审查另一位医生对以下患者的诊断报告。
    问诊历史：{context}
    初诊报告：{doctor_data.get('report', '暂无报告')}
    任务：
    1. 找出初诊报告中过度诊断、缺乏依据、或者遗漏的危险并发症。
    2. 如果是复杂病例，提供更深入的补充分析。
    3. 输出一份【最终审核报告】，必须包含初诊核心内容，并修正错误。
    {ask_instructions}
    请只输出标准 JSON 格式：
    {{"report": "Markdown格式的最终报告内容", "questions": [ ... ]}}
    """
    quality_response = call_llm(role_b, "你是一位严苛的医疗质控专家。", quality_prompt, json_mode=True)
    
    try:
        final_data = json.loads(quality_response.strip().replace("```json", "").replace("```", ""))
        if not isinstance(final_data, dict): final_data = {}
    except:
        final_data = {}
        
    raw_questions = final_data.get("questions", [])
    cleaned_questions = []
    for idx, q in enumerate(raw_questions):
        if not isinstance(q, dict): continue
        q_text = q.get("text", f"问题 {idx + 1}")
        if not q_text or q_text == "未知问题": q_text = f"请补充相关信息 {idx + 1}"
        if q_text in st.session_state.asked_questions: continue
            
        options = q.get("options", [])
        q_id = q.get("id") or f"q_{uuid.uuid4().hex[:8]}_{idx}"
        cleaned_questions.append({"id": q_id, "text": q_text, "options": options})
    
    for cq in cleaned_questions:
        st.session_state.asked_questions.append(cq["text"])
    
    report_text = final_data.get("report") or doctor_data.get("report") or "报告生成异常，请重试。"
    return {"report": report_text, "questions": cleaned_questions}

# ================= 终局：PubMed 校对 =================
def verify_with_pubmed(report_content, role_b):
    extract_prompt = f"请从以下报告中，提取出最核心的1-2个疾病名称，必须是标准的英文医学名词（例如 Tension-type headache），仅用于PubMed检索，不要有任何多余文字：\n{report_content}"
    search_query = call_llm(role_b, "你是一个医学信息提取助手。", extract_prompt).strip()
    
    if not search_query or "error" in search_query.lower():
        return report_content + "\n\n【系统提示】：未能提取到有效的医学检索词，跳过文献核查。"
    
    pubmed_evidence = search_pubmed(search_query)
    if not pubmed_evidence:
        return report_content + "\n\n【系统提示】：PubMed 中未检索到相关最新文献。"
    
    verify_prompt = f"""
    你是一位极其严谨的医学专家。以下是我们生成的诊断报告：
    {report_content}
    同时，我们在 PubMed 上检索到了以下相关医学文献摘要：
    {pubmed_evidence}
    请结合这些文献证据，对上述报告进行最后一次事实核查与校对。
    1. 如果文献支持诊断，予以确认。
    2. 如果文献提示遗漏了严重并发症，或概率排序与文献不符，直接修改报告。
    3. 必须在报告末尾增加一个“【文献参考】”段落，列出你参考的文献标题。
    """
    verified_report = call_llm(role_b, "你是一位医学文献核查专家。", verify_prompt)
    return verified_report

# ================= 界面交互流程 =================
with st.sidebar:
    st.header("患者信息录入")
    if st.button("🔄 重新开始一次会诊"):
        st.session_state.messages = []
        st.session_state.report = ""
        st.session_state.questions = []
        st.session_state.round = 0
        st.session_state.pubmed_done = False
        st.session_state.asked_questions = []
        st.rerun()

if not st.session_state.messages:
    st.info("请在下方描述您的基础症状（系统将根据病情复杂度，动态分配双模型进行交叉验证）")
    initial_symptom = st.text_area("症状描述：", height=100, key="initial_input")
    
    if st.button("开始智能会诊", type="primary"):
        if not initial_symptom.strip():
            st.warning("请先输入您的症状哦～")
        else:
            st.session_state.messages.append({"role": "user", "content": initial_symptom})
            with st.spinner("AI 医生正在调度双模型进行深度会诊..."):
                route_info = evaluate_and_assign(st.session_state.messages)
                result = generate_report_and_questions(st.session_state.messages, route_info, st.session_state.round)
                st.session_state.report = result.get("report", "")
                st.session_state.questions = result.get("questions", [])
                st.session_state.messages.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
                st.rerun()

if st.session_state.report:
    st.markdown("### 📋 交叉验证会诊报告")
    st.markdown(st.session_state.report)
    st.markdown("---")

if st.session_state.questions and st.session_state.round < 3:
    st.subheader(f"请您补充以下信息（第 {st.session_state.round + 1} 轮，最多 3 轮）")
    with st.form(key=f"follow_up_form_{st.session_state.round}"):
        answers = {}
        for q in st.session_state.questions:
            q_text = q.get("text", "未知问题")
            options = q.get("options", [])
            q_key = f"key_{q.get('id')}_{st.session_state.round}"
            if options:
                answers[q_text] = st.multiselect(q_text, options, key=q_key)
            else:
                answers[q_text] = st.text_input(q_text, key=q_key)
                
        submit_answers = st.form_submit_button("提交补充信息")
        
        if submit_answers:
            is_valid = True
            for v in answers.values():
                if isinstance(v, list) and len(v) == 0: is_valid = False
                elif isinstance(v, str) and v.strip() == "": is_valid = False
            if not is_valid:
                st.warning("请至少选择一个选项或填写内容后再提交。")
            else:
                formatted_answers = "\n".join([f"问：{k}\n答：{'、'.join(v) if isinstance(v, list) else v}" for k, v in answers.items()])
                st.session_state.messages.append({"role": "user", "content": f"补充信息：\n{formatted_answers}"})
                st.session_state.round += 1
                
                with st.spinner("AI 医生正在重新评估病情并更新报告..."):
                    route_info = evaluate_and_assign(st.session_state.messages)
                    result = generate_report_and_questions(st.session_state.messages, route_info, st.session_state.round)
                    st.session_state.report = result.get("report", "")
                    st.session_state.questions = result.get("questions", [])
                    st.session_state.messages.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
                    st.rerun()

if (st.session_state.round >= 3 or not st.session_state.questions) and st.session_state.report and not st.session_state.pubmed_done:
    st.session_state.pubmed_done = True
    with st.spinner("正在调用 PubMed 进行终极文献校对（约需 10-15 秒），请稍候..."):
        route_info = evaluate_and_assign(st.session_state.messages)
        role_b = route_info["role_b_model"]
        verified_report = verify_with_pubmed(st.session_state.report, role_b)
        st.session_state.report = verified_report
        st.session_state.messages.append({"role": "assistant", "content": json.dumps({"report": verified_report, "questions": []})})
        st.rerun()

# 优化文案
if st.session_state.round >= 3:
    st.info("已达到最大追问轮次（3轮）。以上是基于现有信息和医学文献核查的最全面分析，请结合报告尽快就医。")
    if st.button("🔄 重新开始一次会诊"):
        st.session_state.messages = []
        st.session_state.report = ""
        st.session_state.questions = []
        st.session_state.round = 0
        st.session_state.pubmed_done = False
        st.session_state.asked_questions = []
        st.rerun()
elif not st.session_state.questions and st.session_state.pubmed_done:
    st.info("AI 医生认为当前症状信息已经足够明确，无需继续追问，已直接为您生成包含文献核查的最终报告。")
    if st.button("🔄 重新开始一次会诊"):
        st.session_state.messages = []
        st.session_state.report = ""
        st.session_state.questions = []
        st.session_state.round = 0
        st.session_state.pubmed_done = False
        st.session_state.asked_questions = []
        st.rerun()

# ================= 【核心修改】构造完整报告用于下载 =================
if st.session_state.report:
    # 提取用户的所有输入（第一条是主诉，后面的是追问回答）
    user_messages = [msg["content"] for msg in st.session_state.messages if msg["role"] == "user"]
    
    download_content = "# 人工智能辅助会诊报告\n\n"
    
    if user_messages:
        # 1. 患者初始主诉
        download_content += "## 一、患者初始主诉\n"
        download_content += f"{user_messages[0]}\n\n"
        
        # 2. 多轮追问记录
        if len(user_messages) > 1:
            download_content += "## 二、智能追问与患者回答\n"
            for idx, qa in enumerate(user_messages[1:], 1):
                qa_clean = qa.replace("补充信息：\n", "").strip()
                # 稍微排版好看一点
                qa_clean = qa_clean.replace("问：", "\n**问：** ").replace("答：", "**答：** ")
                download_content += f"### 第 {idx} 轮追问\n{qa_clean}\n"
            download_content += "\n"
            
        # 3. 最终会诊报告
        download_content += "## 三、最终循证会诊报告\n"
        download_content += st.session_state.report
    else:
        download_content = st.session_state.report # 兜底

    # 渲染下载按钮
    st.download_button(
        label="📥 下载完整会诊报告 TXT",
        data=download_content,
        file_name="ai_consultation_report.txt",
        mime="text/plain"
    )