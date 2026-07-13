# llama3_api.py
import requests
import json
import re
from datetime import datetime, timedelta




def _empty_summary():
    """返回摘要的空结构，作为解析失败或 API 调用失败时的统一回退值。"""
    return {
        "Subject": "N/A",
        "KeyDates": [],
        "StartTime": "",
        "EndTime": "",
        "KeyLocations": [],
        "KeyEvents": []
    }


def _call_ollama(payload, server_url):
    """
    统一的本地模型调用入口：封装网络请求并处理 API 调用失败。
    捕获连接被拒（Ollama 未启动）、超时以及非 2xx 状态码等异常，
    失败时返回 None，由上层函数回退到默认结构，避免整个分析线程崩溃。
    """
    try:
        response = requests.post(server_url, json=payload, timeout=60)
        response.raise_for_status()  # 非 2xx 状态码视为 API 调用失败
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"调用本地模型失败（API 调用异常）: {e}")
        return None


def _complete_summary_fields(summary):
    """
    字段补全：模型输出可能缺字段或缺结束时间，这里做统一补全，
    保证下游日历写入拿到完整、可直接使用的结构。
    """
    # 补全缺失的键，避免下游 KeyError
    for key, default in _empty_summary().items():
        summary.setdefault(key, default)

    # 若有开始时间但缺结束时间，默认按 1 小时补全结束时间
    start = summary.get("StartTime")
    if start and not summary.get("EndTime"):
        try:
            start_dt = datetime.fromisoformat(start)
            summary["EndTime"] = (start_dt + timedelta(hours=1)).isoformat()
        except (ValueError, TypeError):
            pass  # 时间格式非法则保持为空，交由上层校验拦截
    return summary


def sanitize_email_content(email_content):
    """
    清理邮件内容中的无效字符并优化格式。
    """
    if not email_content:
        return ""
    
    # 移除 HTML 标签
    clean_content = re.sub(r'<[^>]+>', '', email_content)

    # 移除多余空格和空行
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()

    # 移除非打印字符
    clean_content = re.sub(r'[^\x20-\x7E]', '', clean_content)

    return clean_content


def send_to_llama_for_analysis(email_data, server_url="http://localhost:11434/api/generate"):
    """发送邮件内容到 Llama 模型进行扩展分类分析"""

    clean_subject = sanitize_email_content(email_data.get('subject', '')).replace('{', '{{').replace('}', '}}')
    clean_body = sanitize_email_content(email_data.get('body', '')).replace('{', '{{').replace('}', '}}')
    raw_sender = email_data.get('from', '')  # 原始发件人字段
   
    prompt = f"""
    You are an email assistant. Your task is to classify the email into one of the following categories:
    - Social: Notifications from social networks (e.g., Facebook, LinkedIn).
    - Promotions: Promotional emails offering deals or discounts.(Words such as sale/promotion appeared, or the sender's email address includes sale/promo/Aliexpress or Amazon, etc.)
    - Important: Emails flagged by the user as significant.(Indicates a specific date/place/time/event)
    - Personal: Conversations with known contacts.(usually a personal email address with a polite greeting and possibly a reference to the event.)
    - Spam: Junk or irrelevant emails.(The email content is empty/garbled or Claim your get free gift/cash rewards)
    Always use email address as the primary sorting basis, if none of the above categories apply, classify it as "Other".

    Sender Email: {raw_sender}
    Subject: {clean_subject}
    Body: {clean_body}

    Please respond in the following JSON format:
    {{
        "Category": "One of the above categories",
        "Reasoning": "Short explanation of why this category was chosen"
    }}
    """
    print(f"生成的 Prompt:\n{prompt}")

    payload = {
        "model": "llama3.1",
        "prompt": prompt,
        "max_tokens": 300,
        "temperature": 0.5,
        "stream": False
    }

    result = _call_ollama(payload, server_url)
    if result is None:
        # API 调用失败时的异常回退：返回 Unknown 分类，保证批量流程继续
        return {"Category": "Unknown", "Reasoning": "Model API call failed"}
    print(f"模型返回内容: {result}")

    generated_text = result.get('response', '').strip()

    # 使用正则提取 JSON 部分
    json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
    if json_match:
        json_text = json_match.group()
        print(f"提取到的 JSON 数据: {json_text}")
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            # 模型输出错误：JSON 结构非法，回退到 Unknown
            print(f"解析分类 JSON 失败: {e}")
            return {"Category": "Unknown", "Reasoning": "Invalid JSON in response"}
    else:
        print("未找到有效的 JSON 数据，标记为 Unknown")
        return {"Category": "Unknown", "Reasoning": "No valid JSON found in response"}


def summarize_email_content(email_data, server_url="http://localhost:11434/api/generate"):
    """对邮件进行重要内容提取和总结"""

    clean_subject = sanitize_email_content(email_data.get('subject', '')).replace('{', '{{').replace('}', '}}')
    clean_body = sanitize_email_content(email_data.get('body', '')).replace('{', '{{').replace('}', '}}')

    prompt = f"""
    You are an email assistant. Your task is to extract and summarize the important contents of the email, focusing on the subject, key dates, start and end times, locations, and events mentioned in the body.

    There may be situations where the end time is not specified.
     -When the event is an appointment, the default duration is 1 hour; 
     -When the event is a meeting, the default duration is 3 hours. 
    Based on this, adjust the corresponding EndTime according to the StartTime. No comments required.
    
    Ensure that the start and end times are returned in the format YYYY-MM-DDTHH:MM:SS to be used directly in a calendar event.

    Subject: {clean_subject}
    Body: {clean_body}
    Please respond in the following JSON format:
    {{
        "Subject": "Extracted subject",
        "KeyDates": ["List of important dates"],
        "StartTime": "The content only include first start time in YYYY-MM-DDTHH:MM:SS format",
        "EndTime": "The content only include first end time in YYYY-MM-DDTHH:MM:SS format",
        "KeyLocations": ["List of important locations"],
        "KeyEvents": ["Short summary of this e-mail"]
    }}

    Examples:
    - Subject: "Meeting Confirmation" Body: "The meeting is on 2024-11-30 at 10:00 AM in Conference Room A."
    Response:
    {{
        "Subject": "Meeting Confirmation",
        "KeyDates": ["2024-11-30"],
        "StartTime": "2024-11-30T10:00:00",
        "EndTime": "2024-11-30T13:00:00",
        "KeyLocations": ["Conference Room A"],
        "KeyEvents": ["Confirmation for a meeting scheduled on 2024-11-30."]
    }}
    """
    print(f"生成的 Prompt:\n{prompt}")

    payload = {
        "model": "llama3.1",
        "prompt": prompt,
        "max_tokens": 300,
        "temperature": 0.5,
        "stream": False
    }

    result = _call_ollama(payload, server_url)
    if result is None:
        # API 调用失败回退到空结构，避免摘要线程中断
        return _empty_summary()

    generated_text = result.get('response', '').strip()
    print(f"模型生成的文本: {generated_text}")

    json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
    if json_match:
        json_text = json_match.group()
        clean_json_text = re.sub(r'//.*', '', json_text).strip()

        try:
            parsed_result = json.loads(clean_json_text)
            # 字段补全：补齐缺失字段并根据开始时间推断结束时间
            parsed_result = _complete_summary_fields(parsed_result)
            print(f"解析结果: {parsed_result}")
            return parsed_result
        except json.JSONDecodeError as e:
            print(f"解析 JSON 失败: {e}")
            return _empty_summary()
    else:
        print("未找到有效的 JSON 数据，返回空结构")
        return _empty_summary()
