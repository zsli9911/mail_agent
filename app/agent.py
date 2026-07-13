# agent.py
"""
邮件处理 Agent：把已有的分类/摘要/工具调用串成一条自动化工作流。

工作流阶段：邮件读取 -> 任务识别 -> 工具调用 -> 结果校验 -> 状态保存。
Agent 根据邮件内容（分类结果）动态选择执行路径，而不是由用户逐个点击按钮：
  - Spam          -> 调用「移入垃圾箱」工具
  - Important/Personal -> 摘要提取时间/地点/事件 -> 校验通过则调用「写入日历」工具
  - 其它类别       -> 仅分类，不触发副作用工具

每封邮件处理完都会返回一份结构化状态（分类依据、时间、地点、事件、处理状态），
交由上层持久化以支持结果复用。
"""

from llama_api import send_to_llama_for_analysis, summarize_email_content
from gmail_api import (
    move_email_to_trash,
    add_event_to_calendar,
    get_calendar_service,
)


def _is_valid_event(summary):
    """结果校验：只有同时具备开始/结束时间和地点，才认为可以写入日历。"""
    if not isinstance(summary, dict):
        return False
    return bool(summary.get("StartTime")
                and summary.get("EndTime")
                and summary.get("KeyLocations"))


def process_email(email, service, creds):
    """
    对单封邮件执行完整 Agent 工作流，返回结构化处理状态。

    :param email: 邮件字典（含 message_id/subject/body 等，来自 gmail_api）
    :param service: Gmail API 服务对象（用于垃圾箱等邮件工具）
    :param creds: 凭据对象（用于按需创建 Calendar 服务）
    :return: 结构化状态 dict，可直接持久化
    """
    # 阶段 1：邮件读取（email 已由调用方读取传入）

    # 阶段 2：任务识别 —— 先分类，决定后续执行路径
    analysis = send_to_llama_for_analysis(email) or {}
    category = analysis.get("Category", "Unknown")
    reasoning = analysis.get("Reasoning", "")

    # 结构化状态：分类依据、时间、地点、事件、处理状态
    state = {
        "category": category,
        "reasoning": reasoning,
        "summary": None,
        "status": "classified",  # 默认仅完成分类
    }

    # 阶段 3 & 4：根据类别动态选择工具、调用并校验
    if category == "Spam":
        # 垃圾邮件路径：直接调用邮件工具移入垃圾箱
        move_email_to_trash(service, email["message_id"])
        state["status"] = "moved_to_trash"

    elif category in ("Important", "Personal"):
        # 重要/个人路径：提取事件信息，校验后写入日历
        summary = summarize_email_content(email)
        state["summary"] = summary

        if _is_valid_event(summary):
            calendar_service = get_calendar_service(creds)
            if calendar_service:
                link = add_event_to_calendar(
                    calendar_service,
                    summary.get("Subject", email.get("subject", "")),
                    summary["KeyLocations"][0],
                    summary["StartTime"],
                    summary["EndTime"],
                )
                # 校验工具调用结果：拿到链接才算写入成功
                state["status"] = "event_created" if link else "calendar_failed"
            else:
                state["status"] = "calendar_unavailable"
        else:
            # 校验未通过（缺时间或地点），只保留摘要不写日历
            state["status"] = "summarized"

    # 其它类别（Promotions/Social/Other/Unknown）保持 "classified"，不触发副作用

    # 阶段 5：状态保存由调用方（GUI）负责持久化，这里返回结构化结果
    return state
